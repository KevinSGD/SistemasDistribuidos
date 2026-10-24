"""Estado de sesion y controlador raiz del cliente (`Aplicacion`).

Flujo: login -> ApiClient + IdleMonitor + EventClient -> ventana segun rol. Cualquier cierre
(inactividad local, 401 de sesion, WebSocket 4401, evento sesion_cerrada valido, logout manual)
termina en `_cerrar_sesion_local`: se destruyen monitor/WS/ventana y vuelve el login con mensaje.

Contrato para las ventanas finales (MainWindow/BuyerWindow reciben `app_ctx = Aplicacion`):
  app_ctx.api, app_ctx.sesion, app_ctx.idle, app_ctx.ejecutar(fn, ok, err, parent)
  senales: evento_ws(str, dict), sondeo(), conexion_cambiada(bool), estado_servidor(bool, str)
  metodos: marcar_actividad_vista(), cerrar_sesion()
"""
from __future__ import annotations

import importlib
import logging
from dataclasses import dataclass
from typing import Any, Callable

from PyQt6.QtCore import QEvent, QObject, QTimer, pyqtSignal
from PyQt6.QtWidgets import QApplication, QWidget

from client.application.mensajes import MENSAJE_INACTIVIDAD, motivo_cierre, texto_error
from client.infrastructure import config as cfg
from client.infrastructure.api_client import ApiClient, ApiError, ErrorConexion
from client.infrastructure.event_client import EventClient
from client.infrastructure.idle_monitor import IdleMonitor
from client.infrastructure.workers import ejecutar
from shared.schemas import LoginOut

log = logging.getLogger(__name__)


@dataclass
class SesionUsuario:
    usuario_id: int
    nombre: str
    rol: str
    token: str
    inactividad_segundos: int
    aviso_segundos: int


@dataclass
class OpcionesCliente:
    """Tiempos ajustables (los tests los acortan)."""
    throttle_actividad: float = 10.0
    tick_ms: int = 1000
    health_ms: int = 10_000
    sondeo_ms: int = 60_000
    ping_ms: int = 15_000
    backoff: tuple = (1.0, 2.0, 4.0, 8.0, 15.0, 30.0)
    solo_espontaneos: bool = True
    cierre_logout_ms: int = 2000


_VENTANAS = {"admin": ("client.presentation.views.main_window", "MainWindow"),
             "comprador": ("client.presentation.views.buyer_window", "BuyerWindow")}


def _cargar_clase_ventana(rol: str):
    """Importa la ventana final del rol; None si aun no existe (se usa la provisional)."""
    modulo, clase = _VENTANAS[rol]
    try:
        return getattr(importlib.import_module(modulo), clase)
    except ModuleNotFoundError as exc:
        if exc.name == modulo:
            return None
        raise
    except AttributeError:
        return None


class Aplicacion(QObject):
    evento_ws = pyqtSignal(str, dict)
    sondeo = pyqtSignal()
    conexion_cambiada = pyqtSignal(bool)
    estado_servidor = pyqtSignal(bool, str)
    sesion_iniciada = pyqtSignal(object)
    sesion_terminada = pyqtSignal(str)
    _sesion_invalida = pyqtSignal(str)          # cruce de hilos: lo emite el ApiClient

    def __init__(self, url: str | None = None, opciones: OpcionesCliente | None = None,
                 fabrica_ventana: Callable[["Aplicacion", str], QWidget] | None = None,
                 timeout: float | None = None, parent: QObject | None = None):
        super().__init__(parent)
        self.opciones = opciones or OpcionesCliente()
        self.url = cfg.normalizar_url(url) if url else cfg.cargar_url()
        self._timeout = timeout
        self._fabrica_ventana = fabrica_ventana
        self.api: ApiClient | None = None
        self.sesion: SesionUsuario | None = None
        self.idle: IdleMonitor | None = None
        self.eventos: EventClient | None = None
        self.ventana: QWidget | None = None
        self.login = None
        self._dialogo = None
        self._cerrando = False
        self._salud_en_curso = False
        self._ultimo_motivo_ws: str | None = None
        self._t_salud = QTimer(self)
        self._t_salud.timeout.connect(self._sondear_salud)
        self._sesion_invalida.connect(self._al_sesion_invalida)

    # -- login ----------------------------------------------------------------------------
    def iniciar(self, mensaje: str | None = None) -> None:
        from client.presentation.views.login import LoginView
        app = QApplication.instance()
        if app is not None:
            app.setQuitOnLastWindowClosed(False)
        if self.login is None:
            self.login = LoginView(self.url, url_editable=not cfg.url_fijada_por_entorno())
            self.login.login_solicitado.connect(self._al_solicitar_login)
            self.login.probar_solicitado.connect(self._al_probar_servidor)
            self.login.cerrada.connect(self._al_cerrar_login)
        self.login.restablecer(mensaje)
        self.login.show()
        self.login.raise_()
        self.login.activateWindow()

    def _nuevo_api(self, url: str) -> ApiClient:
        return ApiClient(url, timeout=self._timeout,
                         on_sesion_invalida=self._sesion_invalida.emit)

    def _al_solicitar_login(self, url: str, usuario: str, password: str) -> None:
        try:
            base = cfg.normalizar_url(url)
        except ValueError as exc:
            self.login.mostrar_error(str(exc))
            return
        api = self._nuevo_api(base)
        ejecutar(lambda: api.login(usuario, password),
                 lambda out: self._login_ok(api, base, out),
                 lambda exc: self._login_fallo(api, exc), self)

    def _login_fallo(self, api: ApiClient, exc: BaseException) -> None:
        api.cerrar()
        espera = exc.reintentar_en if isinstance(exc, ApiError) else None
        self.login.mostrar_error(texto_error(exc), bloquear_segundos=espera)

    def _al_probar_servidor(self, url: str) -> None:
        try:
            api = self._nuevo_api(cfg.normalizar_url(url))
        except ValueError as exc:
            self.login.mostrar_estado_servidor(False, str(exc))
            return

        def fin(res):
            api.cerrar()
            if isinstance(res, BaseException):
                self.login.mostrar_estado_servidor(False, texto_error(res))
            else:
                self.login.mostrar_estado_servidor(True, f"Servidor en línea ({res.so})")
        ejecutar(api.health, fin, fin, self)

    def _al_cerrar_login(self) -> None:
        if self.sesion is None:
            self._terminar()

    # -- sesion iniciada ------------------------------------------------------------------
    def _login_ok(self, api: ApiClient, url: str, out: LoginOut) -> None:
        self.url = url
        if not cfg.url_fijada_por_entorno():
            cfg.guardar_url(url)
        self._cerrando = False
        self._ultimo_motivo_ws = None
        self.api = api
        self.sesion = SesionUsuario(out.usuario.id, out.usuario.nombre, out.usuario.rol,
                                    out.token, out.sesion.inactividad_segundos,
                                    out.sesion.aviso_segundos)
        o = self.opciones
        self.idle = IdleMonitor(out.sesion.inactividad_segundos, out.sesion.aviso_segundos,
                                reportar=api.registrar_actividad,
                                throttle_segundos=o.throttle_actividad, tick_ms=o.tick_ms,
                                solo_espontaneos=o.solo_espontaneos, parent=self)
        self.idle.expirada.connect(self._al_expirar)
        self.idle.aviso.connect(self._al_aviso)
        self.idle.aviso_terminado.connect(self._cerrar_dialogo)
        self.eventos = EventClient(api.url_websocket(), out.token, backoff=o.backoff,
                                   sondeo_ms=o.sondeo_ms, ping_ms=o.ping_ms, parent=self)
        self.eventos.evento.connect(self._al_evento)
        self.eventos.conectado.connect(self.conexion_cambiada)
        self.eventos.sondeo.connect(self.sondeo)
        self.eventos.sesion_invalida.connect(self._al_ws_invalido)

        self.ventana = self._crear_ventana(out.usuario.rol)
        self.ventana.installEventFilter(self)
        self.login.hide()
        self.ventana.show()
        self.idle.iniciar()
        self.eventos.iniciar()
        self._t_salud.start(o.health_ms)
        self._sondear_salud()
        self.sesion_iniciada.emit(self.sesion)

    def _crear_ventana(self, rol: str) -> QWidget:
        if self._fabrica_ventana is not None:
            return self._fabrica_ventana(self, rol)
        clase = _cargar_clase_ventana(rol)
        if clase is None:
            from client.presentation.views.ventana_provisional import VentanaProvisional
            clase = VentanaProvisional
        return clase(self)

    # -- utilidades para las vistas -------------------------------------------------------
    def ejecutar(self, fn, on_ok=None, on_error=None, parent: QObject | None = None) -> None:
        ejecutar(fn, on_ok, on_error, parent or self)

    def marcar_actividad_vista(self) -> None:
        if self.idle is not None:
            self.idle.marcar_actividad_vista()

    # -- salud / eventos ------------------------------------------------------------------
    def _sondear_salud(self) -> None:
        api = self.api
        if api is None or self._salud_en_curso:
            return
        self._salud_en_curso = True

        def fin(res):
            self._salud_en_curso = False
            if self.api is not api:
                return
            if isinstance(res, BaseException):
                self.estado_servidor.emit(False, "Servidor desconectado")
            else:
                self.estado_servidor.emit(True, f"Servidor en línea · {res.so}")
        ejecutar(api.health, fin, fin, self)

    def _al_evento(self, nombre: str, payload: dict) -> None:
        if nombre == "sesion_cerrada":
            self._ultimo_motivo_ws = str(payload.get("motivo") or "")
            self._verificar_sesion()                 # solo cierra si ESTA sesion ya no es valida
        elif nombre == "config_cambiada":
            self._refrescar_parametros_sesion()
        self.evento_ws.emit(nombre, payload)

    def _verificar_sesion(self) -> None:
        api = self.api
        if api is not None:
            ejecutar(api.estado_sesion, None, self._error_verificacion, self)   # 401 => callback del ApiClient

    def _error_verificacion(self, exc: BaseException) -> None:
        """Un 401 ya lo gestiona el callback de sesion invalida del ApiClient (cierra la sesion);
        no es un error inesperado. Cualquier otro fallo si se registra."""
        if isinstance(exc, ApiError) and exc.http == 401:
            log.debug("Verificacion de sesion: %s (cierre gestionado)", exc.codigo)
        else:
            log.warning("Error al verificar la sesion: %r", exc)

    def _refrescar_parametros_sesion(self) -> None:
        api = self.api
        if api is None:
            return

        def ok(est):
            if self.api is api and self.idle is not None and self.sesion is not None:
                self.sesion.inactividad_segundos = est.inactividad_segundos
                self.sesion.aviso_segundos = est.aviso_segundos
                self.idle.actualizar_config(est.inactividad_segundos, est.aviso_segundos)
        ejecutar(api.estado_sesion, ok, lambda e: log.debug("estado_sesion: %r", e), self)

    # -- aviso de inactividad -------------------------------------------------------------
    def _al_aviso(self, restantes: int) -> None:
        if self._dialogo is None:
            from client.presentation.widgets import DialogoInactividad
            self._dialogo = DialogoInactividad(restantes, self.ventana)
            self._dialogo.continuar.connect(self._al_continuar)
            self._dialogo.open()
        else:
            self._dialogo.actualizar(restantes)

    def _al_continuar(self) -> None:
        if self.idle is not None:
            self.idle.marcar_actividad(forzar_reporte=True)

    def _cerrar_dialogo(self) -> None:
        d, self._dialogo = self._dialogo, None
        if d is not None:
            try:
                d.cerrar_aviso()
            finally:
                d.deleteLater()

    # -- cierres --------------------------------------------------------------------------
    def _al_expirar(self) -> None:
        self._cerrar_sesion_local(MENSAJE_INACTIVIDAD, avisar_servidor=True)

    def _al_sesion_invalida(self, codigo: str) -> None:
        self._cerrar_sesion_local(motivo_cierre(codigo, self._ultimo_motivo_ws),
                                  avisar_servidor=False)

    def _al_ws_invalido(self) -> None:
        # 4401: aclarar el motivo exacto con /auth/sesion (no renueva); si no responde, generico.
        api = self.api
        if api is None or self._cerrando:
            return
        ejecutar(api.estado_sesion,
                 lambda _: self._cerrar_sesion_local(motivo_cierre(None, self._ultimo_motivo_ws),
                                                     avisar_servidor=False),
                 lambda exc: (None if isinstance(exc, ApiError) and exc.http == 401 else
                              self._cerrar_sesion_local(motivo_cierre(None, self._ultimo_motivo_ws),
                                                        avisar_servidor=False)),
                 self)

    def cerrar_sesion(self) -> None:
        """Cierre manual: /auth/logout en segundo plano y vuelta inmediata al login."""
        self._cerrar_sesion_local("Sesión cerrada", avisar_servidor=True)

    def _cerrar_sesion_local(self, mensaje: str, avisar_servidor: bool) -> None:
        if self._cerrando or self.sesion is None:
            return
        self._cerrando = True
        api, ventana = self.api, self.ventana
        self._t_salud.stop()
        self._cerrar_dialogo()
        if self.idle is not None:
            self.idle.detener()
            self.idle.deleteLater()
        if self.eventos is not None:
            self.eventos.detener()
            self.eventos.deleteLater()
        self.idle = self.eventos = self.api = self.sesion = self.ventana = None
        if ventana is not None:
            ventana.removeEventFilter(self)
            ventana.close()
            ventana.deleteLater()
        if api is not None:
            def liberar(_=None):
                api.cerrar()
            if avisar_servidor:
                ejecutar(api.logout, liberar, liberar, self)    # mejor esfuerzo
            else:
                liberar()
        self.sesion_terminada.emit(mensaje)
        self.iniciar(mensaje)

    def eventFilter(self, obj, ev):  # noqa: N802
        """Cerrar la ventana principal con la X = salir de la aplicacion (con logout)."""
        if obj is self.ventana and ev.type() == QEvent.Type.Close and not self._cerrando:
            self.salir()
        return False

    def salir(self) -> None:
        api = self.api
        self._t_salud.stop()
        if self.idle is not None:
            self.idle.detener()
        if self.eventos is not None:
            self.eventos.detener()
        self._cerrando = True
        if api is None or self.sesion is None:
            self._terminar()
            return
        self.sesion = None
        QTimer.singleShot(self.opciones.cierre_logout_ms, self._terminar)
        ejecutar(api.logout, lambda _: self._terminar(), lambda _: self._terminar(), self)

    def _terminar(self) -> None:
        app = QApplication.instance()
        if app is not None:
            app.quit()
