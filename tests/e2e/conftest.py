"""Fixtures E2E: servidor REAL en Ubuntu/WSL2 (instancia aislada) + clientes PyQt6 en Windows.

Ejecutar:  .venv\\Scripts\\python.exe -m pytest tests/e2e -m e2e -p no:cacheprovider -s
La suite normal NO ejecuta estos tests (pytest.ini: addopts = -m "not e2e")."""
from __future__ import annotations

import atexit
import os
import platform
import shutil
import tempfile

import sys

import pytest

for _f in (sys.stdout, sys.stderr):      # los mensajes llevan tildes y ✓
    if hasattr(_f, "reconfigure"):
        _f.reconfigure(encoding="utf-8", errors="replace")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
# Los ajustes del cliente (URL guardada, PDFs) van a un directorio temporal: nunca al perfil real.
_CFG = tempfile.mkdtemp(prefix="inv_e2e_cfg_")
os.environ["INVENTARIO_CLIENT_DIR"] = _CFG
atexit.register(shutil.rmtree, _CFG, ignore_errors=True)

from tests.e2e.wsl import WslServidor, wsl, wsl_disponible  # noqa: E402


# -- servidores ------------------------------------------------------------------------------
@pytest.fixture(scope="session")
def wsl_ok():
    if platform.system() != "Windows":
        pytest.skip("Las pruebas E2E requieren el cliente en Windows")
    if not wsl_disponible():
        pytest.skip("WSL/Ubuntu no disponible")
    return True


@pytest.fixture(scope="session")
def demo_intacta(wsl_ok):
    """Huella de la BD de demo antes y despues: la suite E2E no debe tocarla."""
    cmd = "stat -c '%Y %s' ~/.inventario/data/inventario.db 2>/dev/null || echo ausente"
    antes = wsl(cmd).stdout.strip()
    yield antes
    despues = wsl(cmd).stdout.strip()
    assert antes == despues, f"La BD de demo cambio durante las pruebas: {antes} -> {despues}"


@pytest.fixture(scope="session")
def servidor(wsl_ok, demo_intacta):
    """Instancia principal aislada (puerto desde 8010, BD en /tmp/inv_e2e_*)."""
    s = WslServidor("main").iniciar()
    yield s
    s.limpiar()


@pytest.fixture
def servidor_propio(wsl_ok):
    """Fabrica de instancias desechables (para detenerlas/reiniciarlas o cambiar su config)."""
    creadas: list[WslServidor] = []

    def _crear(nombre: str = "tmp") -> WslServidor:
        s = WslServidor(nombre).iniciar()
        creadas.append(s)
        return s
    yield _crear
    for s in creadas:
        s.limpiar()


# -- API de Windows ----------------------------------------------------------------------------
@pytest.fixture
def api_admin(servidor):
    from client.infrastructure.api_client import ApiClient
    c = ApiClient(servidor.url)
    c.login("admin", servidor.admin_pw)
    yield c
    c.cerrar()


@pytest.fixture
def api_comprador(servidor):
    from client.infrastructure.api_client import ApiClient
    c = ApiClient(servidor.url)
    c.login("comprador", servidor.comp_pw)
    yield c
    c.cerrar()


# -- Qt ------------------------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def _entorno_cliente(monkeypatch, tmp_path):
    monkeypatch.setenv("INVENTARIO_CLIENT_DIR", str(tmp_path / "cfg"))
    monkeypatch.delenv("INVENTARIO_URL", raising=False)


@pytest.fixture(scope="session")
def qapp():
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication(["e2e"])
    app.setStyle("Fusion")
    from client.presentation.styles.theme import aplicar_tema
    aplicar_tema(app)
    return app


@pytest.fixture
def espera(qapp):
    from tests.e2e.helpers import esperar
    return esperar


@pytest.fixture
def crear_app(qapp):
    """Fabrica de `Aplicacion` (la raiz real del cliente). Cierra todo al terminar."""
    from PyQt6.QtWidgets import QApplication
    from tests.e2e.helpers import cerrar_app, nueva_app
    creadas = []

    def _crear(servidor, opciones=None, **kw):
        a = nueva_app(servidor.url if hasattr(servidor, "url") else servidor, opciones, **kw)
        creadas.append(a)
        return a
    yield _crear
    for a in creadas:
        cerrar_app(a)
    QApplication.processEvents()


@pytest.fixture
def sin_visor(monkeypatch):
    """Evita abrir el visor de PDF del sistema; registra las rutas."""
    abiertos = []
    monkeypatch.setattr("client.presentation.views.factura_view.abrir_archivo",
                        lambda ruta: abiertos.append(ruta) or True)
    return abiertos


@pytest.fixture(autouse=True)
def _limpieza_qt():
    """Tras cada prueba: entrega borrados diferidos y recolecta en un punto seguro
    (ver tests/qt_limpieza.py: evita el cierre nativo intermitente por el GC)."""
    yield
    from tests.qt_limpieza import vaciar_qt
    vaciar_qt()
