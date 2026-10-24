"""Hallazgos del E2E (ya corregidos: H-2 JWT en logs, H-3 localhost lento) y mediciones del entorno."""
import socket
import statistics
import time
from urllib.parse import urlsplit

import httpx
import pytest
from PyQt6.QtCore import QEvent, QPoint, Qt
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from client.infrastructure.api_client import ApiClient
from tests.e2e.helpers import entrar, esperar
import websockets.sync.client as wsc

pytestmark = pytest.mark.e2e


def _conexion_nueva(url: str, n: int = 4) -> list[float]:
    out = []
    for _ in range(n):
        t = time.perf_counter()
        with httpx.Client(timeout=10) as c:
            c.get(url + "/api/v1/health")
        out.append(time.perf_counter() - t)
    return out


def test_conexion_nueva_con_la_url_por_defecto_tarda_menos_de_1s(servidor):
    """H-3 resuelto: el cliente usa 127.0.0.1 por defecto (localhost cuesta ~2,2 s por conexion en WSL2)."""
    from client.infrastructure.config import URL_POR_DEFECTO
    assert urlsplit(URL_POR_DEFECTO).hostname == "127.0.0.1"
    por_defecto = f"{URL_POR_DEFECTO.rsplit(':', 1)[0]}:{servidor.puerto}"
    lh = _conexion_nueva(servidor.url_localhost)
    ip = _conexion_nueva(por_defecto)
    try:
        t = time.perf_counter()
        socket.create_connection(("::1", servidor.puerto), timeout=5).close()
        v6 = f"conecta en {time.perf_counter() - t:.2f} s"
    except OSError as e:
        v6 = f"falla en {time.perf_counter() - t:.2f} s ({type(e).__name__})"
    print(f"\n[9a] conexion nueva: localhost mediana {statistics.median(lh) * 1000:.0f} ms "
          f"(max {max(lh) * 1000:.0f}); 127.0.0.1 mediana {statistics.median(ip) * 1000:.0f} ms "
          f"(max {max(ip) * 1000:.0f}); ::1 {v6}")
    assert statistics.median(ip) < 1.0


def test_el_jwt_no_debe_aparecer_en_los_logs_del_servidor(servidor, api_comprador):
    with wsc.connect(f"ws://127.0.0.1:{servidor.puerto}/ws?token={api_comprador.token}"):
        time.sleep(0.5)
    log = servidor.en_linux(f"cat {servidor.dir}/logs/stdout.log")
    en_stdout = api_comprador.token in log
    en_servidor_log = api_comprador.token in servidor.en_linux(f"cat {servidor.dir}/logs/servidor.log")
    print(f"\n[9b] JWT visible en stdout.log: {en_stdout}; en servidor.log: {en_servidor_log}")
    assert not en_stdout and not en_servidor_log


def test_filtro_de_actividad_solo_cuenta_teclado_y_raton_reales(servidor, crear_app, espera):
    """El IdleMonitor de produccion (solo_espontaneos=True): teclado/clic/rueda/movimiento amplio cuentan;
    eventos sinteticos (sendEvent) y movimientos minimos, no."""
    a = crear_app(servidor)
    entrar(a, "comprador", servidor.comp_pw)
    i, w = a.idle, a.ventana
    assert i._solo_espontaneos is True
    base = i._ultima
    espera(lambda: False, 0.3)
    # sintetico: no cuenta
    QApplication.sendEvent(w, QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_A, Qt.KeyboardModifier.NoModifier, "a"))
    assert i._ultima == base
    # movimiento minimo: no cuenta; amplio: si
    QTest.mouseMove(w, QPoint(10, 10))
    QTest.mouseMove(w, QPoint(12, 11))
    assert i._ultima == base
    QTest.mouseMove(w, QPoint(80, 90))
    assert i._ultima > base
    ultima = i._ultima
    espera(lambda: False, 0.2)
    QTest.keyClick(w, Qt.Key.Key_Shift)
    assert i._ultima > ultima
    ultima = i._ultima
    espera(lambda: False, 0.2)
    QTest.mouseClick(w, Qt.MouseButton.LeftButton, pos=QPoint(5, 5))
    assert i._ultima > ultima
    # el refresco (health/eventos/sondeo) no mueve la marca
    ultima = i._ultima
    a.sondeo.emit()
    a.evento_ws.emit("stock_actualizado", {"producto_id": 1, "stock": 1, "activo": True})
    espera(lambda: False, 1.2)
    assert i._ultima == ultima
    print("\n[9c] sendEvent sintetico y movimiento <8 px no renuevan; teclado, clic y movimiento amplio si; "
          "sondeo/evento WS/health no")
