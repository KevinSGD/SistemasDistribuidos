"""Fabrica de la aplicacion FastAPI."""
from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Callable

from fastapi import FastAPI
from sqlalchemy import Engine
from starlette.concurrency import run_in_threadpool

from server.infrastructure.db.engine import (
    crear_engine, crear_esquema, crear_session_factory, sesion,
)
from server.infrastructure.db.seed import sembrar_configuracion
from server.security.bootstrap import asegurar_usuarios_iniciales
from server.security.rutas import ENV_DATA_DIR

from . import ws
from .errores import registrar_manejadores
from .routers import auth, config, health, productos, riesgo, usuarios, ventas
from .routers.health import VERSION
from .servicios import construir_servicios

PREFIJO = "/api/v1"


def _directorio_credenciales(engine: Engine) -> Path | None:
    """Donde escribir credenciales iniciales: INVENTARIO_DATA_DIR manda; si no, junto a la BD."""
    if os.environ.get(ENV_DATA_DIR):
        return None
    ruta = engine.url.database
    return Path(ruta).parent if ruta else None


def crear_app(engine_o_ruta: Engine | str | Path | None = None, iniciar_scheduler: bool = True,
              *, reloj: Callable[[], datetime] | None = None,
              ws_chequeo_segundos: float = 5.0) -> FastAPI:
    """Crea la app. `engine_o_ruta`: Engine, ruta a un .db o None (INVENTARIO_DB / por defecto).

    `reloj` (solo tests): reloj inyectado en AuthService para simular inactividad.
    `ws_chequeo_segundos`: periodo del chequeo de caducidad de los sockets abiertos."""
    propio = not isinstance(engine_o_ruta, Engine)
    engine = engine_o_ruta if isinstance(engine_o_ruta, Engine) else crear_engine(engine_o_ruta)
    factory = crear_session_factory(engine)
    srv = construir_servicios(factory, reloj, ws_chequeo_segundos)

    def preparar_bd() -> None:
        crear_esquema(engine)
        with sesion(factory) as s:
            sembrar_configuracion(s)
            asegurar_usuarios_iniciales(s, _directorio_credenciales(engine))

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        srv.bus.vincular_loop(asyncio.get_running_loop())
        await run_in_threadpool(preparar_bd)
        if iniciar_scheduler:
            srv.scheduler.iniciar()
        try:
            yield
        finally:
            await run_in_threadpool(srv.scheduler.detener)
            srv.bus.vincular_loop(None)
            if propio:
                engine.dispose()

    app = FastAPI(title="InventarioApp API", version=VERSION, lifespan=lifespan)
    app.state.servicios = srv
    registrar_manejadores(app)
    for r in (auth, productos, riesgo, ventas, config, usuarios, health):
        app.include_router(r.router, prefix=PREFIJO)
    app.include_router(ws.router)
    app.include_router(ws.router, prefix=PREFIJO)   # alias /api/v1/ws
    return app
