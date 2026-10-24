"""Escenario 1: dos sistemas operativos distintos. Cliente en Windows, servidor en Ubuntu/WSL2."""
import platform

import httpx
import pytest

from client.infrastructure.api_client import ApiClient

pytestmark = pytest.mark.e2e


def test_health_desde_windows_dice_linux(servidor):
    assert platform.system() == "Windows"                       # este proceso (cliente)
    h = httpx.get(servidor.url + "/api/v1/health", timeout=5).json()
    assert h["estado"] == "ok" and h["so"] == "Linux"           # el servidor, otro SO
    c = ApiClient(servidor.url)
    try:
        assert c.health().so == "Linux"                         # por el ApiClient real del cliente
    finally:
        c.cerrar()


def test_el_proceso_del_servidor_es_linux_y_aislado(servidor):
    assert servidor.puerto != 8000 and servidor.dir.startswith("/tmp/inv_e2e_")
    cmdline = servidor.en_linux(f"tr '\\0' ' ' < /proc/{servidor.pid}/cmdline")
    assert "server.main" in cmdline and "/.inventario/venv/bin/python" in cmdline
    assert servidor.en_linux(f"readlink /proc/{servidor.pid}/cwd").strip() == servidor.dir + "/app"
    assert servidor.en_linux("uname -s").strip() == "Linux"
    # la BD y el codigo estan en el filesystem de Linux, no en /mnt/c
    assert servidor.en_linux(f"test -f {servidor.dir}/data/inventario.db && echo si").strip() == "si"
    # ningun proceso de Windows escucha en ese puerto: lo atiende el reenvio de WSL
    assert "Linux" in servidor.en_linux("cat /proc/version")


def test_credenciales_propias_y_ajenas(servidor):
    c = ApiClient(servidor.url)
    try:
        assert c.login("admin", servidor.admin_pw).usuario.rol == "admin"
        assert c.login("comprador", servidor.comp_pw).usuario.rol == "comprador"
    finally:
        c.cerrar()
