"""Herramienta MANUAL (no es parte de la suite): reproduce el cierre nativo intermitente.

Ciclo: sesion A (login + WebSocket + cambio de config por el admin + cierre local) seguida de una
sesion B (login) sin pausa, con la aplicacion movida a mano con processEvents().

    python -m tests.stress.stress_login_logout 80               # con limpieza (esperado: 0 caidas)
    python -m tests.stress.stress_login_logout 80 --sin-limpieza  # reproduce el fallo

Para medir la tasa de caida lance 4 procesos en paralelo (la carga la hace mas probable).
Sin limpieza, con PyQt6 6.7.0 / Python 3.13: 4 de 4 procesos caian en <= 80 ciclos (exit 139,
"access violation"). Con limpieza: 0 de 4. Ver docs/INFORME_PRUEBAS.md."""
from __future__ import annotations

import faulthandler
import os
import pathlib
import random
import sys
import tempfile
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
faulthandler.enable()

from PyQt6.QtWidgets import QApplication  # noqa: E402

from client.application.sesion import Aplicacion, OpcionesCliente  # noqa: E402
from client.infrastructure.api_client import ApiClient  # noqa: E402
from tests.client.conftest import ADMIN_PW, COMP_PW, Servidor  # noqa: E402
from tests.qt_limpieza import vaciar_qt  # noqa: E402

RAPIDO = OpcionesCliente(throttle_actividad=0.2, tick_ms=100, health_ms=300, sondeo_ms=500,
                         ping_ms=60000, backoff=(0.1, 0.2), solo_espontaneos=False,
                         cierre_logout_ms=200)


def main(ciclos: int, con_limpieza: bool) -> None:
    app = QApplication([])
    tmp = pathlib.Path(tempfile.mkdtemp())
    os.environ["INVENTARIO_CLIENT_DIR"] = str(tmp / "cfg")
    srv = Servidor(tmp / "srv").iniciar()
    admin = ApiClient(srv.url)
    admin.login("admin", ADMIN_PW)

    def pump(seg, cond=None):
        lim = time.monotonic() + seg
        while time.monotonic() < lim:
            app.processEvents()
            if cond and cond():
                return True
            time.sleep(0.01)
        return cond() if cond else False

    def cerrar(a):
        if a.sesion is not None:
            a._cerrando = False
            a._cerrar_sesion_local("fin", avisar_servidor=False)
        if a.login is not None:
            a.login.cerrada.disconnect()
            a.login.close()
            a.login.deleteLater()
        a.deleteLater()
        app.processEvents()
        if con_limpieza:
            vaciar_qt()

    def entrar(a):
        a.login.input_usuario.setText("comprador")
        a.login.input_password.setText(COMP_PW)
        a.login.btn_login.click()
        assert pump(8, lambda: a.sesion is not None)

    t0 = time.time()
    try:
        for i in range(ciclos):
            a = Aplicacion(srv.url, RAPIDO, timeout=2.0)
            a.iniciar()
            entrar(a)
            assert pump(8, lambda: a.eventos.esta_conectado)
            try:
                admin.actualizar_config({"inactividad_segundos": 600, "aviso_segundos": 20})
                pump(8, lambda: a.idle is not None and a.idle.inactividad_segundos == 600)
            finally:
                admin.actualizar_config({"inactividad_segundos": 900, "aviso_segundos": 30})
            cerrar(a)
            time.sleep(random.choice([0.0, 0.03, 0.08, 0.15]))
            app.processEvents()
            b = Aplicacion(srv.url, RAPIDO, timeout=2.0)
            b.iniciar()
            entrar(b)
            pump(0.3)
            cerrar(b)
            if i % 10 == 0:
                print(i, round(time.time() - t0, 1), flush=True)
    finally:
        srv.detener()
    print("OK", round(time.time() - t0, 1))


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 80,
         "--sin-limpieza" not in sys.argv)
