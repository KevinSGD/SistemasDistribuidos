from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from server.api.app import crear_app

ADMIN_PW = "admin-clave-123"
COMP_PW = "comprador-clave-123"


class Reloj:
    def __init__(self):
        self.t = datetime.now()

    def __call__(self):
        return self.t

    def avanzar(self, segundos):
        self.t += timedelta(seconds=segundos)


@pytest.fixture(autouse=True)
def entorno(monkeypatch, tmp_path):
    monkeypatch.setenv("INVENTARIO_JWT_SECRET", "secreto-api-de-prueba-" + "x" * 32)
    monkeypatch.setenv("INVENTARIO_DATA_DIR", str(tmp_path / "datos"))
    monkeypatch.setenv("INVENTARIO_ADMIN_PASSWORD", ADMIN_PW)
    monkeypatch.setenv("INVENTARIO_COMPRADOR_PASSWORD", COMP_PW)


@pytest.fixture
def reloj():
    return Reloj()


@pytest.fixture
def client(tmp_path, reloj):
    app = crear_app(tmp_path / "api.db", iniciar_scheduler=False, reloj=reloj,
                    ws_chequeo_segundos=0.2)
    with TestClient(app) as c:      # `with` ejecuta el lifespan (esquema, usuarios, loop del bus)
        yield c


def login(client, usuario="admin", password=ADMIN_PW):
    r = client.post("/api/v1/auth/login", json={"usuario": usuario, "password": password})
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture
def admin(client):
    d = login(client)
    return {"Authorization": f"Bearer {d['token']}"}, d


@pytest.fixture
def comprador(client):
    d = login(client, "comprador", COMP_PW)
    return {"Authorization": f"Bearer {d['token']}"}, d


@pytest.fixture
def crear_producto(client, admin):
    def _crear(**kw):
        datos = {"nombre": "Leche", "categoria": "Lacteos", "precio_base": 10.0,
                 "stock": 20, "stock_maximo": 1000}
        datos.update(kw)
        r = client.post("/api/v1/productos", json=datos, headers=admin[0])
        assert r.status_code == 201, r.text
        return r.json()
    return _crear
