"""Instancia AISLADA del servidor en Ubuntu/WSL2 para las pruebas E2E.

No toca el servidor de demo (puerto 8000, ~/.inventario/data): cada instancia usa
/tmp/inv_e2e_<id> (datos, logs, copia del codigo) y un puerto propio (desde 8010).
El script que hace el trabajo en Linux es tests/e2e/wsl_server.sh."""
from __future__ import annotations

import atexit
import os
import secrets
import socket
import subprocess
import time
import uuid
from pathlib import Path

import httpx

RAIZ = Path(__file__).resolve().parents[2]
DISTRO = os.environ.get("INVENTARIO_WSL_DISTRO", "Ubuntu")
PUERTO_BASE = int(os.environ.get("INVENTARIO_E2E_PUERTO", "8010"))


def a_ruta_wsl(ruta: Path) -> str:
    """C:\a\b -> /mnt/c/a/b"""
    s = str(ruta).replace("\\", "/")
    if len(s) > 1 and s[1] == ":":
        return f"/mnt/{s[0].lower()}{s[2:]}"
    return s


SCRIPT_WSL = a_ruta_wsl(RAIZ / "tests" / "e2e" / "wsl_server.sh")
REPO_WSL = a_ruta_wsl(RAIZ)


def wsl_disponible() -> bool:
    try:
        r = subprocess.run(["wsl.exe", "-d", DISTRO, "--", "true"], capture_output=True, timeout=60)
        return r.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def wsl(cmd: str, timeout: float = 120, entrada: str | None = None) -> subprocess.CompletedProcess:
    """Ejecuta `cmd` en bash dentro de la distro. Devuelve CompletedProcess con texto utf-8."""
    return subprocess.run(["wsl.exe", "-d", DISTRO, "--", "bash", "-lc", cmd],
                          capture_output=True, text=True, encoding="utf-8", errors="replace",
                          timeout=timeout, input=entrada)


def _puerto_libre_windows(p: int) -> bool:
    with socket.socket() as s:
        try:
            s.bind(("127.0.0.1", p))
            return True
        except OSError:
            return False


_vivas: list["WslServidor"] = []


@atexit.register
def _limpiar_al_salir() -> None:      # red de seguridad: nunca dejar procesos propios vivos
    for s in list(_vivas):
        try:
            s.limpiar()
        except Exception:  # noqa: BLE001
            pass


class WslServidor:
    """Servidor FastAPI real en Linux, accesible desde Windows por http://localhost:<puerto>."""

    def __init__(self, nombre: str = "e2e", admin_pw: str | None = None, comp_pw: str | None = None,
                 puerto: int | None = None):
        self.id = f"{nombre}_{uuid.uuid4().hex[:6]}"
        self.admin_pw = admin_pw or secrets.token_urlsafe(14)
        self.comp_pw = comp_pw or secrets.token_urlsafe(14)
        self.puerto = puerto
        self.pid: int | None = None
        self.arranques = 0
        self.dir = f"/tmp/inv_e2e_{self.id}"

    # -- URLs ---------------------------------------------------------------------------
    @property
    def url(self) -> str:
        # 127.0.0.1 y no "localhost": en Windows 11 + WSL2, "localhost" tarda ~2,2 s por CONEXION NUEVA
        # (intenta IPv6 antes). Hallazgo documentado en docs/INFORME_PRUEBAS.md (test_09_latencia).
        return f"http://127.0.0.1:{self.puerto}"

    @property
    def url_localhost(self) -> str:
        return f"http://localhost:{self.puerto}"

    def health(self, timeout: float = 3.0) -> dict:
        return httpx.get(self.url + "/api/v1/health", timeout=timeout).json()

    def _script(self, accion: str, *args: str, env: str = "", timeout: float = 120):
        return wsl(f"{env} bash {SCRIPT_WSL} {accion} {self.id} " + " ".join(args), timeout=timeout)

    # -- ciclo de vida ------------------------------------------------------------------
    def iniciar(self) -> "WslServidor":
        env = (f"INVENTARIO_ADMIN_PASSWORD='{self.admin_pw}' "
               f"INVENTARIO_COMPRADOR_PASSWORD='{self.comp_pw}'")
        candidatos = [self.puerto] if self.puerto else range(PUERTO_BASE, PUERTO_BASE + 60)
        ultimo = None
        for p in candidatos:
            if not _puerto_libre_windows(p) and self.arranques == 0:
                continue
            r = self._script("start", str(p), REPO_WSL, env=env)
            if r.returncode == 2:                  # ocupado en Linux: probar el siguiente
                continue
            ultimo = r
            if r.returncode != 0:
                raise RuntimeError(f"No arranco la instancia WSL ({r.returncode}): {r.stdout}{r.stderr}")
            self.puerto = p
            self.pid = int(r.stdout.split("PID=")[1].split()[0])
            break
        else:
            raise RuntimeError(f"Sin puerto libre desde {PUERTO_BASE}: {ultimo}")
        self.arranques += 1
        if self not in _vivas:
            _vivas.append(self)
        limite = time.time() + 20                  # visible desde Windows (localhost forwarding)
        while time.time() < limite:
            try:
                self.health(1.5)
                return self
            except (httpx.HTTPError, ValueError):
                time.sleep(0.2)
        raise RuntimeError(f"La instancia responde en WSL pero no desde Windows: {self.url}")

    def detener(self) -> str:
        r = self._script("stop")
        self.pid = None
        return (r.stdout + r.stderr).strip()

    def reiniciar(self) -> "WslServidor":
        self.detener()
        return self.iniciar()

    def limpiar(self) -> None:
        """Detiene SOLO el proceso propio (por PID registrado) y borra los temporales."""
        self.detener()
        self._script("clean")
        if self in _vivas:
            _vivas.remove(self)

    # -- inspeccion en Linux ---------------------------------------------------------------
    def en_linux(self, cmd: str, timeout: float = 60) -> str:
        r = wsl(cmd, timeout=timeout)
        if r.returncode != 0:
            raise RuntimeError(f"Fallo en WSL ({r.returncode}): {r.stderr or r.stdout}")
        return r.stdout

    def python_en_linux(self, codigo: str, timeout: float = 60) -> str:
        """Ejecuta `codigo` con el python del venv de Linux, cwd = copia del codigo de la instancia."""
        r = wsl(f"cd {self.dir}/app && INVENTARIO_DB={self.dir}/data/inventario.db "
                f"INVENTARIO_DATA_DIR={self.dir}/data PYTHONDONTWRITEBYTECODE=1 "
                f"$HOME/.inventario/venv/bin/python -", timeout=timeout, entrada=codigo)
        if r.returncode != 0:
            raise RuntimeError(f"Fallo python en WSL ({r.returncode}): {r.stderr}")
        return r.stdout
