"""Cliente Windows REAL en un PROCESO APARTE (su propio QApplication).

Por que existe: el IdleMonitor instala su filtro de eventos en el QApplication, que es uno por
proceso. Si varios usuarios simulados viven en el mismo proceso, el teclado/raton de uno cuenta como
actividad de todos. En produccion cada usuario es un proceso; para probar "actividad real" sin esa
contaminacion, el cliente que recibe teclado/raton corre aqui.

Protocolo: JSON por linea. stdout (worker -> test): {"t": <time.time()>, "ev": nombre, ...}.
stdin (test -> worker): una orden por linea: actividad | estado | salir.
Argumentos: url usuario ; la contrasena llega por la variable INV_E2E_PW."""
from __future__ import annotations

import json
import os
import sys
import threading
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from PyQt6.QtCore import QObject, QPoint, Qt, pyqtSignal   # noqa: E402
from PyQt6.QtTest import QTest                              # noqa: E402
from PyQt6.QtWidgets import QApplication                    # noqa: E402

from client.application.sesion import Aplicacion, OpcionesCliente   # noqa: E402
from client.presentation.styles.theme import aplicar_tema           # noqa: E402


def emit(ev: str, **kw) -> None:
    print(json.dumps({"t": time.time(), "ev": ev, **kw}, ensure_ascii=False), flush=True)


class Puente(QObject):
    orden = pyqtSignal(str)


def a_reloj_pared(monotonic: float) -> float:
    return time.time() - (time.monotonic() - monotonic)


def main() -> int:
    url, usuario = sys.argv[1], sys.argv[2]
    password = os.environ["INV_E2E_PW"]
    qapp = QApplication(["worker"])
    qapp.setStyle("Fusion")
    aplicar_tema(qapp)
    ctx = Aplicacion(url, OpcionesCliente(), timeout=8.0)
    ctx.iniciar()
    ctx.login.input_usuario.setText(usuario)
    ctx.login.input_password.setText(password)
    estado = {"conexiones": [], "eventos_id": None, "api_id": None}

    def al_iniciar(_s):
        i = ctx.idle
        estado["eventos_id"], estado["api_id"] = id(ctx.eventos), id(ctx.api)
        i.aviso.connect(lambda r: emit("aviso", restantes=r,
                                       dialogo=ctx._dialogo.texto_cuenta if ctx._dialogo else None))
        i.aviso_terminado.connect(lambda: emit("aviso_terminado"))
        ctx.conexion_cambiada.connect(lambda v: estado["conexiones"].append([time.time(), v]))
        emit("listo", ref=a_reloj_pared(i._ultima), token=ctx.sesion.token, inactividad=i.inactividad_segundos,
             aviso=i.aviso_segundos, reloj=ctx.ventana.barra.reloj.segundos)
    ctx.sesion_iniciada.connect(al_iniciar)
    ctx.sesion_terminada.connect(lambda m: emit("terminada", mensaje=m))

    puente = Puente()

    def orden(txt: str) -> None:
        if txt == "actividad":
            d = ctx._dialogo
            objetivo = d if d is not None else ctx.ventana
            antes = ctx.idle.restantes() if ctx.idle else None
            # teclado y raton REALES de Qt sobre la ventana (eventos espontaneos, como los del usuario)
            QTest.keyClick(objetivo, Qt.Key.Key_Shift)
            QTest.mouseClick(objetivo, Qt.MouseButton.LeftButton, pos=QPoint(4, 4))
            emit("actividad_hecha", dialogo_visible_antes=d is not None, restantes_antes=antes,
                 restantes_despues=ctx.idle.restantes(), reloj=ctx.ventana.barra.reloj.segundos,
                 dialogo_cerrado=ctx._dialogo is None, ref=a_reloj_pared(ctx.idle._ultima))
        elif txt == "estado":
            i = ctx.idle
            emit("estado", inactividad=i.inactividad_segundos, aviso=i.aviso_segundos,
                 sesion_inactividad=ctx.sesion.inactividad_segundos,
                 mismo_ws=id(ctx.eventos) == estado["eventos_id"],
                 mismo_api=id(ctx.api) == estado["api_id"], conexiones=estado["conexiones"],
                 ws=ctx.eventos.esta_conectado,
                 restantes=i.restantes(), reloj=ctx.ventana.barra.reloj.segundos)
        elif txt == "reset":
            estado["conexiones"].clear()
            emit("reset_ok", ws=ctx.eventos.esta_conectado)
        elif txt == "login":
            emit("login", visible=ctx.login.isVisible(), aviso=ctx.login.lbl_aviso.text(),
                 aviso_visible=ctx.login.lbl_aviso.isVisible())
        elif txt == "salir":
            qapp.quit()
    puente.orden.connect(orden)

    def leer_stdin() -> None:
        for linea in sys.stdin:
            puente.orden.emit(linea.strip())
        puente.orden.emit("salir")
    threading.Thread(target=leer_stdin, daemon=True).start()

    ctx.login.btn_login.click()
    qapp.exec()
    return 0


if __name__ == "__main__":
    sys.exit(main())
