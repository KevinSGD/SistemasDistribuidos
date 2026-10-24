from datetime import datetime

import pytest

from server.application.config_service import ConfigService
from server.application.eventos import EventBus
from server.application.inventario_service import InventarioService
from server.application.riesgo_service import RiesgoService
from server.application.venta_service import VentaService
from server.domain.entities import ProductoDominio
from server.infrastructure.db.engine import (
    crear_engine, crear_esquema, crear_session_factory, sesion,
)
from server.infrastructure.db.repos import ProductoRepo, UsuarioRepo
from server.infrastructure.db.seed import sembrar_configuracion

AHORA = datetime(2026, 6, 1, 12, 0, 0)


@pytest.fixture
def engine(tmp_path):
    eng = crear_engine(tmp_path / "t.db")
    crear_esquema(eng)
    yield eng
    eng.dispose()


@pytest.fixture
def factory(engine):
    f = crear_session_factory(engine)
    with sesion(f) as s:
        sembrar_configuracion(s)
    return f


@pytest.fixture
def bus():
    return EventBus()


@pytest.fixture
def eventos(bus):
    recibidos = []
    bus.suscribir(recibidos.append)
    return recibidos


@pytest.fixture
def config(factory, bus):
    return ConfigService(factory, bus)


@pytest.fixture
def ventas(factory, config, bus):
    return VentaService(factory, config, bus, reloj=lambda: AHORA)


@pytest.fixture
def riesgo(factory, config, bus):
    return RiesgoService(factory, config, bus, reloj=lambda: AHORA)


@pytest.fixture
def inventario(factory, bus):
    return InventarioService(factory, bus)


@pytest.fixture
def usuarios(factory):
    with sesion(factory) as s:
        r = UsuarioRepo(s)
        a = r.crear("Admin", "admin", "x", "admin")
        c1 = r.crear("Comp 1", "c1", "x", "comprador")
        c2 = r.crear("Comp 2", "c2", "x", "comprador")
    return a.id, c1.id, c2.id


@pytest.fixture
def crear_producto(factory):
    def _crear(nombre="Leche", precio=10.0, stock=50, venc=None, stock_max=1000, activo=True):
        with sesion(factory) as s:
            return ProductoRepo(s).crear(ProductoDominio(
                None, nombre, "Lacteos", precio, stock, stock_max, venc, activo))
    return _crear
