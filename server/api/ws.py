"""WebSocket /ws?token=<JWT>. Nunca renueva la actividad: solo valida (AuthService.validar_token)."""
from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Query, WebSocket
from starlette.concurrency import run_in_threadpool

from server.application.errores import ROL_ADMIN
from server.application.eventos import SESION_CERRADA
from server.domain.errors import ErrorDominio
from server.security.errores import SesionCerrada, SesionInactiva
from server.security.sesiones import Contexto

log = logging.getLogger(__name__)
router = APIRouter()
CIERRE_NO_AUTORIZADO = 4401


def _es_destinatario(para, ctx: Contexto) -> bool:
    if para == "todos":
        return True
    if para == "admin":
        return ctx.rol == ROL_ADMIN
    if isinstance(para, dict):
        return para.get("usuario_id") == ctx.usuario_id
    return False


def _motivo(exc: ErrorDominio) -> str:
    if isinstance(exc, SesionInactiva):
        return "inactividad"
    if isinstance(exc, SesionCerrada):
        return str(exc.detalle.get("motivo") or "cerrada")
    return "token_invalido"


async def _cerrar(ws: WebSocket, code: int = CIERRE_NO_AUTORIZADO) -> None:
    try:
        await ws.close(code=code)
    except Exception:  # noqa: BLE001  (ya cerrado / desconectado)
        pass


@router.websocket("/ws")
async def eventos(websocket: WebSocket, token: str | None = Query(default=None)):
    srv = websocket.app.state.servicios
    try:
        ctx = await run_in_threadpool(srv.auth.validar_token, token or "")
    except ErrorDominio:
        await websocket.accept()          # aceptar para que el cliente reciba el codigo 4401
        await _cerrar(websocket)
        return

    cola: asyncio.Queue = asyncio.Queue(maxsize=1000)

    def al_evento(ev: dict) -> None:       # corre en el loop (EventBus.vincular_loop)
        if _es_destinatario(ev.get("para"), ctx):
            try:
                cola.put_nowait(ev)
            except asyncio.QueueFull:
                log.warning("Cola WS llena para usuario %s; evento descartado", ctx.usuario_id)

    baja = srv.bus.suscribir(al_evento)    # antes de accept: no se pierden eventos tras conectar
    try:
        await websocket.accept()
        emisor = asyncio.create_task(_emisor(websocket, srv, token, cola))
        receptor = asyncio.create_task(_receptor(websocket))
        _, pendientes = await asyncio.wait({emisor, receptor},
                                           return_when=asyncio.FIRST_COMPLETED)
        for t in pendientes:
            t.cancel()
        await asyncio.gather(*pendientes, return_exceptions=True)
    except Exception:  # noqa: BLE001
        log.debug("WebSocket terminado con error", exc_info=True)
    finally:
        baja()
        await _cerrar(websocket, 1000)


async def _receptor(ws: WebSocket) -> None:
    """Descarta lo que envie el cliente (no cuenta como actividad); detecta la desconexion."""
    while True:
        msg = await ws.receive()
        if msg["type"] == "websocket.disconnect":
            return


async def _revalidar(srv, token: str) -> ErrorDominio | None:
    """Valida la sesion (por jti) sin renovar actividad (incluye la expiracion del JWT); devuelve el error o None si sigue viva."""
    try:
        await run_in_threadpool(srv.auth.validar_token, token)
    except ErrorDominio as e:
        return e
    return None


async def _emisor(ws: WebSocket, srv, token: str, cola: asyncio.Queue) -> None:
    loop = asyncio.get_running_loop()
    intervalo = srv.ws_chequeo_segundos
    proximo = loop.time() + intervalo
    while True:
        try:
            ev = await asyncio.wait_for(cola.get(), timeout=max(0.01, proximo - loop.time()))
        except asyncio.TimeoutError:
            ev = None
        if loop.time() >= proximo:
            proximo = loop.time() + intervalo
            err = await _revalidar(srv, token)
            if err is not None:
                await _enviar_cierre(ws, _motivo(err))
                return
        if ev is None:
            continue
        if ev["tipo"] == SESION_CERRADA:
            # el evento es por usuario; solo cierra si ESTA sesion ya no es valida
            err = await _revalidar(srv, token)
            if err is not None:
                await _enviar_cierre(ws, ev["payload"].get("motivo") or _motivo(err))
                return
            continue
        await ws.send_json({"evento": ev["tipo"], "payload": ev["payload"]})


async def _enviar_cierre(ws: WebSocket, motivo: str) -> None:
    try:
        await ws.send_json({"evento": SESION_CERRADA, "payload": {"motivo": motivo}})
    except Exception:  # noqa: BLE001
        pass
    await _cerrar(ws)
