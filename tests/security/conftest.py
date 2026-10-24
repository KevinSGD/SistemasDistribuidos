from datetime import datetime, timedelta

import pytest

from server.infrastructure.db.engine import crear_engine, crear_esquema, crear_session_factory
from server.infrastructure.db.repos import ConfigRepo, UsuarioRepo
from server.infrastructure.db.seed import sembrar_configuracion
from server.security.hashing import hashear
from server.security.sesiones import AuthService


class Reloj:
    def __init__(self):
        self.t = datetime(2026, 1, 1, 12, 0, 0)

    def __call__(self):
        return self.t

    def avanzar(self, segundos):
        self.t += timedelta(seconds=segundos)


class BusFalso:
    def __init__(self):
        self.eventos = []

    def publicar(self, evento, payload, usuario_id=None):
        self.eventos.append((evento, payload, usuario_id))


@pytest.fixture(autouse=True)
def entorno(monkeypatch, tmp_path):
    monkeypatch.setenv("INVENTARIO_JWT_SECRET", "secreto-de-prueba-" + "x" * 32)
    monkeypatch.setenv("INVENTARIO_DATA_DIR", str(tmp_path / "datos"))
    for v in ("INVENTARIO_ADMIN_PASSWORD", "INVENTARIO_COMPRADOR_PASSWORD"):
        monkeypatch.delenv(v, raising=False)


@pytest.fixture
def factory(tmp_path):
    eng = crear_engine(tmp_path / "t.db")
    crear_esquema(eng)
    f = crear_session_factory(eng)
    with f() as s:
        sembrar_configuracion(s)
        repo = UsuarioRepo(s)
        repo.crear("Ana", "ana", hashear("clave-ana"), rol="admin")
        repo.crear("Beto", "beto", hashear("clave-beto"), rol="comprador")
        repo.crear("Inactivo", "inac", hashear("clave-inac"), rol="comprador", activo=False)
        s.commit()
    yield f
    eng.dispose()


@pytest.fixture
def reloj():
    return Reloj()


@pytest.fixture
def bus():
    return BusFalso()


@pytest.fixture
def auth(factory, reloj, bus):
    return AuthService(factory, bus, reloj)


def poner_config(factory, clave, valor):
    with factory() as s:
        ConfigRepo(s).set(clave, valor)
        s.commit()
