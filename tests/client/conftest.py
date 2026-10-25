"""Fixtures del cliente: servidor REAL como subproceso (BD temporal, puerto libre) y QApplication."""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

RAIZ = Path(__file__).resolve().parents[2]
ADMIN_PW = "admin-clave-123"
COMP_PW = "comprador-clave-123"


def puerto_libre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Servidor:
    def __init__(self, directorio: Path, puerto: int | None = None):
        self.dir = directorio
        self.puerto = puerto or puerto_libre()
        self.url = f"http://127.0.0.1:{self.puerto}"
        self.proc: subprocess.Popen | None = None

    def iniciar(self) -> "Servidor":
        self.dir.mkdir(parents=True, exist_ok=True)
        env = dict(os.environ)
        env.update({
            "INVENTARIO_HOST": "127.0.0.1", "INVENTARIO_PORT": str(self.puerto),
            "INVENTARIO_DB": str(self.dir / "test.db"),
            "INVENTARIO_DATA_DIR": str(self.dir / "datos"),
            "INVENTARIO_LOG_DIR": str(self.dir / "logs"),
            "INVENTARIO_JWT_SECRET": "secreto-cliente-de-prueba-" + "x" * 32,
            "INVENTARIO_ADMIN_PASSWORD": ADMIN_PW,
            "INVENTARIO_COMPRADOR_PASSWORD": COMP_PW,
            "PYTHONUNBUFFERED": "1",
        })
        self._log = open(self.dir / "server.out", "ab")
        self.proc = subprocess.Popen([sys.executable, "-m", "server.main"], cwd=RAIZ, env=env,
                                     stdout=self._log, stderr=subprocess.STDOUT)
        limite = time.time() + 30
        while time.time() < limite:
            if self.proc.poll() is not None:
                raise RuntimeError("El servidor de prueba terminó:\n"
                                   + (self.dir / "server.out").read_text(errors="replace"))
            try:
                if httpx.get(self.url + "/api/v1/health", timeout=1).status_code == 200:
                    return self
            except httpx.HTTPError:
                time.sleep(0.2)
        self.detener()
        raise RuntimeError("El servidor de prueba no arrancó a tiempo")

    def detener(self) -> None:
        if self.proc and self.proc.poll() is None:
            if sys.platform == "win32":
                # El python del venv es un launcher: terminate() solo mata al launcher y deja
                # huerfano al servidor real. /T mata el arbol completo.
                subprocess.run(["taskkill", "/PID", str(self.proc.pid), "/T", "/F"],
                               capture_output=True, check=False)
            else:
                self.proc.terminate()
            try:
                self.proc.wait(10)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait()
        self.proc = None
        if getattr(self, "_log", None):
            self._log.close()


@pytest.fixture(scope="session")
def servidor(tmp_path_factory):
    s = Servidor(tmp_path_factory.mktemp("srv")).iniciar()
    yield s
    s.detener()


@pytest.fixture
def servidor_propio(tmp_path):
    """Servidor desechable que el test puede apagar y volver a levantar."""
    s = Servidor(tmp_path / "srv").iniciar()
    yield s
    s.detener()


@pytest.fixture(autouse=True)
def _entorno_cliente(monkeypatch, tmp_path):
    monkeypatch.setenv("INVENTARIO_CLIENT_DIR", str(tmp_path / "cfg"))
    monkeypatch.delenv("INVENTARIO_URL", raising=False)


@pytest.fixture(scope="session")
def qapp():
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication(["tests"])
    app.setStyle("Fusion")
    from client.presentation.styles.theme import aplicar_tema
    aplicar_tema(app)
    return app


def esperar(condicion, timeout: float = 8.0, paso: float = 0.01) -> bool:
    """Procesa eventos Qt hasta que `condicion()` sea verdadera."""
    from PyQt6.QtWidgets import QApplication
    limite = time.monotonic() + timeout
    while time.monotonic() < limite:
        QApplication.processEvents()
        if condicion():
            return True
        time.sleep(paso)
    QApplication.processEvents()
    return bool(condicion())


@pytest.fixture
def espera():
    return esperar


@pytest.fixture
def api_admin(servidor):
    from client.infrastructure.api_client import ApiClient
    c = ApiClient(servidor.url)
    c.login("admin", ADMIN_PW)
    yield c
    c.cerrar()


@pytest.fixture
def api_comprador(servidor):
    from client.infrastructure.api_client import ApiClient
    c = ApiClient(servidor.url)
    c.login("comprador", COMP_PW)
    yield c
    c.cerrar()


@pytest.fixture(autouse=True)
def _limpieza_qt():
    """Tras cada prueba: entrega borrados diferidos y recolecta en un punto seguro
    (ver tests/qt_limpieza.py: evita el cierre nativo intermitente por el GC)."""
    yield
    from tests.qt_limpieza import vaciar_qt
    vaciar_qt()
