"""Contenedor de servicios (composicion) y adaptador EventBus -> Protocol Bus de seguridad."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Callable

from server.application.config_service import ConfigService
from server.application.eventos import EventBus, evento
from server.application.inventario_service import InventarioService
from server.application.riesgo_service import RiesgoService, Scheduler
from server.application.usuario_service import UsuarioService
from server.application.venta_service import VentaService
from server.security.hashing import hashear
from server.security.sesiones import AuthService


class BusSeguridad:
    """Implementa `server.security.sesiones.Bus`: traduce `publicar(tipo, payload, usuario_id)`
    a un evento del EventBus. Con usuario_id el evento va solo a ese usuario."""

    def __init__(self, bus: EventBus):
        self._bus = bus

    def publicar(self, tipo: str, payload: dict, usuario_id: int | None = None) -> None:
        para = {"usuario_id": usuario_id} if usuario_id is not None else "todos"
        self._bus.publicar(evento(tipo, payload, para))


@dataclass
class Servicios:
    factory: object
    bus: EventBus
    auth: AuthService
    config: ConfigService
    inventario: InventarioService
    ventas: VentaService
    riesgo: RiesgoService
    usuarios: UsuarioService
    scheduler: Scheduler
    ws_chequeo_segundos: float = 5.0


def construir_servicios(factory, reloj: Callable[[], datetime] | None = None,
                        ws_chequeo_segundos: float = 5.0) -> Servicios:
    bus = EventBus()
    auth_kwargs = {"reloj": reloj} if reloj is not None else {}
    auth = AuthService(factory, BusSeguridad(bus), **auth_kwargs)
    config = ConfigService(factory, bus)
    riesgo = RiesgoService(factory, config, bus)
    return Servicios(
        factory=factory, bus=bus, auth=auth, config=config,
        inventario=InventarioService(factory, bus),
        ventas=VentaService(factory, config, bus), riesgo=riesgo,
        usuarios=UsuarioService(factory, hashear, auth.cerrar_sesiones_de),
        scheduler=Scheduler.para(riesgo, config),
        ws_chequeo_segundos=ws_chequeo_segundos,
    )
