"""Escenario 3: el servidor Linux se cae con el comprador conectado.

El indicador pasa a "desconectado" y, sin actividad, el cliente cierra la sesion LOCALMENTE al
cumplirse el tiempo configurado (el temporizador es del cliente, no depende del servidor), sin
congelarse: un QTimer de 50 ms en el hilo GUI mide que el bucle de eventos nunca se bloquea."""
import time
from concurrent.futures import ThreadPoolExecutor

import pytest
from PyQt6.QtCore import QTimer

from client.application.mensajes import MENSAJE_INACTIVIDAD
from client.infrastructure.api_client import ApiClient
from client.presentation.views.buyer_window import BuyerWindow
from tests.e2e.helpers import entrar, esperar

pytestmark = pytest.mark.e2e

INACT, AVISO = 30, 10
LATIDO_MS = 50
UMBRAL_GUI = 0.5          # el hilo GUI no debe quedarse sin atender eventos mas de 0,5 s


def test_servidor_caido_indicador_y_cierre_local_sin_congelar(servidor_propio, crear_app):
    srv = servidor_propio("caido")
    adm = ApiClient(srv.url)
    adm.login("admin", srv.admin_pw)
    adm.actualizar_config({"inactividad_segundos": INACT, "aviso_segundos": AVISO})
    adm.cerrar()

    a = crear_app(srv)
    entrar(a, "comprador", srv.comp_pw)
    assert isinstance(a.ventana, BuyerWindow)
    assert (a.idle.inactividad_segundos, a.idle.aviso_segundos) == (INACT, AVISO)
    barra = a.ventana.barra
    assert esperar(lambda: barra.conexion.conectado and a.eventos.esta_conectado, 15)
    assert barra.conexion._texto.text() == "Servidor en línea · Linux"
    ref = a.idle._ultima

    # latido del hilo GUI: si algo bloquea el bucle de eventos, aparece como un hueco grande
    gaps, ultimo = [], [time.monotonic()]

    def latido():
        t = time.monotonic()
        gaps.append(t - ultimo[0])
        ultimo[0] = t
    timer = QTimer()
    timer.setInterval(LATIDO_MS)
    timer.timeout.connect(latido)
    timer.start()

    eventos: dict = {}
    a.conexion_cambiada.connect(lambda v: eventos.setdefault("ws_cae" if not v else "ws_vuelve", time.monotonic()))
    avisos = []
    a.idle.aviso.connect(lambda r: avisos.append((time.monotonic() - ref, r)))
    a.sesion_terminada.connect(lambda m: eventos.update(cierre=time.monotonic(), msg=m))

    # ---- se cae el servidor (en un hilo: el comando wsl.exe tarda ~1 s y no debe bloquear la GUI)
    with ThreadPoolExecutor(1) as pool:
        t_stop = time.monotonic()
        fut = pool.submit(srv.detener)
        assert esperar(lambda: not barra.conexion.conectado, 15), "el indicador sigue en linea"
        eventos["indicador_rojo"] = time.monotonic()
        # el health (cada 10 s) confirma el texto final
        assert esperar(lambda: barra.conexion._texto.text() == "Servidor desconectado", 15)
        eventos["texto_desconectado"] = time.monotonic()
        stop_msg = fut.result(timeout=30)

        # ---- sin actividad: aviso a ~20 s y cierre LOCAL a ~30 s de la ultima actividad
        assert esperar(lambda: a.sesion is None, 45), "la sesion no se cerro sola"
    timer.stop()
    cierre = eventos["cierre"] - ref
    assert 29.5 <= cierre <= 33.0, cierre
    assert avisos and 19.5 <= avisos[0][0] <= 22.5, avisos           # el aviso tambien funciona sin servidor
    assert a.login.isVisible() and a.login.lbl_aviso.text() == MENSAJE_INACTIVIDAD
    assert a.api is None and a.idle is None and a.eventos is None and a.ventana is None

    max_gap = max(gaps)
    assert max_gap < UMBRAL_GUI, f"el hilo GUI se bloqueo {max_gap:.3f} s"
    print(f"\n[3] kill del servidor: {stop_msg!r}; WS cae +{eventos['ws_cae'] - t_stop:.2f} s; "
          f"indicador rojo +{eventos['indicador_rojo'] - t_stop:.2f} s; texto 'Servidor desconectado' "
          f"+{eventos['texto_desconectado'] - t_stop:.2f} s; aviso a {avisos[0][0]:.2f} s; cierre local a "
          f"{cierre:.2f} s con mensaje '{a.login.lbl_aviso.text()}'; latido GUI: {len(gaps)} muestras, "
          f"hueco maximo {max_gap * 1000:.0f} ms (intervalo {LATIDO_MS} ms)")

    # ---- con el servidor aun caido, un intento de login falla con claridad y sin congelar
    gaps.clear()
    ultimo[0] = time.monotonic()
    timer.start()
    a.login.input_usuario.setText("comprador")
    a.login.input_password.setText(srv.comp_pw)
    a.login.btn_login.click()
    assert esperar(lambda: "No se pudo conectar" in a.login.lbl_error.text(), 20)
    assert a.login.btn_login.isEnabled()
    timer.stop()
    assert max(gaps) < UMBRAL_GUI
    print(f"[3] login con servidor caido: '{a.login.lbl_error.text()}'; hueco GUI maximo "
          f"{max(gaps) * 1000:.0f} ms")

    # ---- recuperacion: el servidor vuelve (misma BD) y el login funciona
    srv.iniciar()
    entrar(a, "comprador", srv.comp_pw)
    assert a.sesion is not None
