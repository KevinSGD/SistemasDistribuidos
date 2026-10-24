"""Cliente WebSocket de eventos del servidor (/ws?token=).

Senales:
  evento(nombre, payload)  evento valido del servidor (nunca cuenta como actividad del usuario)
  conectado(bool)          cambia el estado del socket
  sondeo()                 respaldo de polling: cada `sondeo_ms` (60 s) mientras este desconectado
                           y una vez al reconectar (por si se perdieron eventos)
  sesion_invalida()        el servidor cerro con 4401 (token/sesion no valida): NO se reintenta

Reconexion con backoff creciente. Un keepalive (ping) detecta sockets muertos sin cierre limpio."""
from __future__ import annotations

import json
import logging
from typing import Sequence
from urllib.parse import quote

from PyQt6.QtCore import QObject, QTimer, QUrl, pyqtSignal
from PyQt6.QtNetwork import QAbstractSocket
from PyQt6.QtWebSockets import QWebSocket

from shared.schemas import EventoWS

log = logging.getLogger(__name__)
CIERRE_NO_AUTORIZADO = 4401
BACKOFF_POR_DEFECTO = (1.0, 2.0, 4.0, 8.0, 15.0, 30.0)


class EventClient(QObject):
    evento = pyqtSignal(str, dict)
    conectado = pyqtSignal(bool)
    sondeo = pyqtSignal()
    sesion_invalida = pyqtSignal()

    def __init__(self, url_ws: str, token: str, *, backoff: Sequence[float] = BACKOFF_POR_DEFECTO,
                 sondeo_ms: int = 60_000, ping_ms: int = 15_000, parent: QObject | None = None):
        """`url_ws`: p. ej. ws://host:8000/ws (ApiClient.url_websocket())."""
        super().__init__(parent)
        self._url = QUrl(f"{url_ws}?token={quote(token, safe='')}")
        self._backoff = tuple(backoff) or (1.0,)
        self._intento = 0
        self._detenido = True
        self._conectado = False
        self._con_exito_alguna_vez = False
        self._pong_pendiente = False

        self._ws = QWebSocket(parent=self)
        self._ws.connected.connect(self._al_conectar)
        self._ws.disconnected.connect(self._al_desconectar)
        self._ws.textMessageReceived.connect(self._al_mensaje)
        self._ws.pong.connect(self._al_pong)
        self._ws.errorOccurred.connect(self._al_error)

        self._t_reintento = QTimer(self)
        self._t_reintento.setSingleShot(True)
        self._t_reintento.timeout.connect(self._abrir)
        self._t_sondeo = QTimer(self)
        self._t_sondeo.setInterval(sondeo_ms)
        self._t_sondeo.timeout.connect(self.sondeo)
        self._t_ping = QTimer(self)
        self._t_ping.setInterval(ping_ms)
        self._t_ping.timeout.connect(self._keepalive)

    # -- API ------------------------------------------------------------------------------
    @property
    def esta_conectado(self) -> bool:
        return self._conectado

    def iniciar(self) -> None:
        self._detenido = False
        self._intento = 0
        self._t_sondeo.start()           # activo mientras no haya socket
        self._abrir()

    def detener(self) -> None:
        self._detenido = True
        self._t_reintento.stop()
        self._t_sondeo.stop()
        self._t_ping.stop()
        if self._ws.state() != QAbstractSocket.SocketState.UnconnectedState:
            self._ws.close()
        self._marcar(False)

    # -- internos -------------------------------------------------------------------------
    def _marcar(self, estado: bool) -> None:
        if estado != self._conectado:
            self._conectado = estado
            self.conectado.emit(estado)

    def _abrir(self) -> None:
        if self._detenido:
            return
        if self._ws.state() != QAbstractSocket.SocketState.UnconnectedState:
            self._ws.abort()
        self._ws.open(self._url)

    def _al_conectar(self) -> None:
        reconexion = self._con_exito_alguna_vez
        self._con_exito_alguna_vez = True
        self._intento = 0
        self._pong_pendiente = False
        self._t_sondeo.stop()
        self._t_ping.start()
        self._marcar(True)
        if reconexion:
            self.sondeo.emit()           # resincroniza lo que pudo perderse

    def _al_error(self, *_args) -> None:
        # Fallo al abrir (servidor caido): QWebSocket no siempre emite disconnected.
        if self._ws.state() == QAbstractSocket.SocketState.UnconnectedState:
            self._perdido(0)

    def _al_desconectar(self) -> None:
        try:
            codigo = int(self._ws.closeCode().value)
        except (ValueError, TypeError, AttributeError):
            codigo = 0
        self._perdido(codigo)

    def _perdido(self, codigo: int) -> None:
        self._t_ping.stop()
        self._marcar(False)
        if self._detenido:
            return
        if codigo == CIERRE_NO_AUTORIZADO:
            self._detenido = True
            self._t_sondeo.stop()
            self._t_reintento.stop()
            self.sesion_invalida.emit()
            return
        if self._t_reintento.isActive():
            return                               # error + disconnected del mismo fallo
        if not self._t_sondeo.isActive():
            self._t_sondeo.start()
        espera = self._backoff[min(self._intento, len(self._backoff) - 1)]
        self._intento += 1
        self._t_reintento.start(int(espera * 1000))

    def _keepalive(self) -> None:
        if self._pong_pendiente:                 # el ping anterior no obtuvo respuesta
            log.info("WebSocket sin respuesta; reconectando")
            self._ws.abort()                     # dispara disconnected -> reintento
            return
        self._pong_pendiente = True
        self._ws.ping()

    def _al_pong(self, *_args) -> None:
        self._pong_pendiente = False

    def _al_mensaje(self, texto: str) -> None:
        self._pong_pendiente = False
        try:
            ev = EventoWS.model_validate(json.loads(texto))
        except (ValueError, TypeError):          # JSON roto o esquema invalido (ValidationError es ValueError)
            log.debug("Mensaje WS ignorado: %.80r", texto)
            return
        self.evento.emit(ev.evento, ev.payload)
