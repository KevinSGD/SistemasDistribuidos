"""Monitor de inactividad del usuario (RF-14 / ADR 4).

Solo cuentan como actividad: teclado, clic/doble clic/rueda, movimiento del raton por encima de un
umbral y el cambio de vista (`marcar_actividad_vista()`). El refresco automatico y los eventos WS
NO llaman a `marcar_actividad`.

Mantiene un temporizador LOCAL (no depende del servidor para cerrar):
  - `segundos_restantes(int)` cada tick (para el reloj de sesion);
  - `aviso(int)` cada tick cuando faltan <= aviso_segundos;
  - `aviso_terminado()` cuando una actividad (o un cambio de config) saca de la zona de aviso;
  - `expirada()` una sola vez al llegar a 0.
La actividad se reporta al servidor con throttle (por defecto 10 s) mediante `reportar`, que se
ejecuta en un worker. Si una actividad queda retenida por el throttle, se envia al vencer el
throttle (asi el servidor nunca caduca antes que el temporizador local)."""
from __future__ import annotations

import logging
import math
import time
from typing import Any, Callable

from PyQt6.QtCore import QEvent, QObject, QPointF, QTimer, pyqtSignal

from .workers import ejecutar

log = logging.getLogger(__name__)

_TIPOS_ACTIVIDAD = frozenset({
    QEvent.Type.KeyPress, QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonDblClick,
    QEvent.Type.Wheel,
})


class IdleMonitor(QObject):
    aviso = pyqtSignal(int)
    aviso_terminado = pyqtSignal()
    expirada = pyqtSignal()
    segundos_restantes = pyqtSignal(int)

    def __init__(self, inactividad_segundos: int, aviso_segundos: int, *,
                 reportar: Callable[[], Any] | None = None,
                 reloj: Callable[[], float] = time.monotonic,
                 throttle_segundos: float = 10.0, umbral_movimiento: float = 8.0,
                 tick_ms: int = 1000, solo_espontaneos: bool = True,
                 parent: QObject | None = None):
        """`reportar`: funcion bloqueante (p. ej. api.registrar_actividad) que se corre en un worker.
        `reloj`: fuente de tiempo monotono inyectable. `solo_espontaneos`: ignora eventos
        sinteticos de Qt (False en tests que usan QTest)."""
        super().__init__(parent)
        self._inact = max(1, int(inactividad_segundos))
        self._aviso = max(0, int(aviso_segundos))
        self._reportar = reportar
        self._reloj = reloj
        self._throttle = throttle_segundos
        self._umbral = umbral_movimiento
        self._solo_espontaneos = solo_espontaneos
        self._ultima = reloj()
        self._ultimo_reporte = float("-inf")
        self._pendiente = False
        self._reportando = False
        self._en_aviso = False
        self._activo = False
        self._pos: QPointF | None = None
        self._timer = QTimer(self)
        self._timer.setInterval(tick_ms)
        self._timer.timeout.connect(self.tick)

    # -- ciclo de vida --------------------------------------------------------------------
    def iniciar(self, instalar_filtro: bool = True) -> None:
        """Arranca el conteo desde ahora (la sesion acaba de renovarse con el login)."""
        from PyQt6.QtWidgets import QApplication
        self._ultima = self._reloj()
        self._ultimo_reporte = self._ultima      # el login ya renovo la actividad
        self._pendiente = False
        self._en_aviso = False
        self._activo = True
        app = QApplication.instance()
        if instalar_filtro and app is not None:
            app.installEventFilter(self)
        self._timer.start()
        self.segundos_restantes.emit(self.restantes())

    def detener(self) -> None:
        self._activo = False
        self._timer.stop()
        from PyQt6.QtWidgets import QApplication
        app = QApplication.instance()
        if app is not None:
            app.removeEventFilter(self)

    @property
    def activo(self) -> bool:
        return self._activo

    # -- estado ---------------------------------------------------------------------------
    def restantes(self) -> int:
        return max(0, math.ceil(self._inact - (self._reloj() - self._ultima)))

    @property
    def inactividad_segundos(self) -> int:
        return self._inact

    @property
    def aviso_segundos(self) -> int:
        return self._aviso

    def actualizar_config(self, inactividad_segundos: int, aviso_segundos: int) -> None:
        """Cambia los umbrales en caliente, sin reiniciar el tiempo ya transcurrido."""
        self._inact = max(1, int(inactividad_segundos))
        self._aviso = max(0, int(aviso_segundos))
        if self._activo:
            self.tick()

    # -- actividad ------------------------------------------------------------------------
    def marcar_actividad_vista(self) -> None:
        """Llamar al cambiar de vista/pestana por accion del usuario."""
        self.marcar_actividad()

    def marcar_actividad(self, forzar_reporte: bool = False) -> None:
        if not self._activo:
            return
        ahora = self._reloj()
        if ahora - self._ultima >= self._inact:
            return                                  # ya vencio: lo gestiona el tick
        self._ultima = ahora
        if self._en_aviso:
            self._en_aviso = False
            self.aviso_terminado.emit()
        self.segundos_restantes.emit(self.restantes())
        self._pendiente = True
        if forzar_reporte or ahora - self._ultimo_reporte >= self._throttle:
            self._enviar_reporte(ahora)

    def _enviar_reporte(self, ahora: float) -> None:
        if self._reportar is None:
            self._pendiente = False
            return
        if self._reportando:
            return                                  # reintenta en el siguiente tick
        self._pendiente = False
        self._ultimo_reporte = ahora
        self._reportando = True

        def listo(_=None):
            self._reportando = False
        ejecutar(self._reportar, listo, listo, self)

    def eventFilter(self, obj: QObject | None, ev: QEvent | None) -> bool:  # noqa: N802
        if not self._activo or ev is None:
            return False
        tipo = ev.type()
        if tipo in _TIPOS_ACTIVIDAD:
            if not self._solo_espontaneos or ev.spontaneous():
                self.marcar_actividad()
        elif tipo == QEvent.Type.MouseMove:
            if not self._solo_espontaneos or ev.spontaneous():
                try:
                    pos = ev.globalPosition()
                except AttributeError:
                    return False
                if self._pos is None:
                    self._pos = pos
                elif (pos - self._pos).manhattanLength() >= self._umbral:
                    self._pos = pos
                    self.marcar_actividad()
        return False

    # -- temporizador local ---------------------------------------------------------------
    def tick(self) -> None:
        if not self._activo:
            return
        ahora = self._reloj()
        resto = self.restantes()
        self.segundos_restantes.emit(resto)
        if resto <= 0:
            self.detener()
            self.expirada.emit()
            return
        if self._pendiente and ahora - self._ultimo_reporte >= self._throttle:
            self._enviar_reporte(ahora)
        if resto <= self._aviso:
            self._en_aviso = True
            self.aviso.emit(resto)
        elif self._en_aviso:
            self._en_aviso = False
            self.aviso_terminado.emit()
