import threading

from PyQt6.QtCore import QEvent, QPoint, QPointF, Qt, QThreadPool
from PyQt6.QtGui import QKeyEvent, QMouseEvent, QWheelEvent
from PyQt6.QtWidgets import QApplication, QWidget

from client.infrastructure.idle_monitor import IdleMonitor
from client.infrastructure.workers import ejecutar


class Reloj:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t

    def avanzar(self, s):
        self.t += s


def crear(qapp, inact=100, aviso=30, reportar=None, **kw):
    r = Reloj()
    m = IdleMonitor(inact, aviso, reportar=reportar, reloj=r, tick_ms=10**7,
                    solo_espontaneos=kw.pop("solo_espontaneos", False), **kw)
    registro = {"aviso": [], "fin_aviso": 0, "expirada": 0, "resto": []}
    m.aviso.connect(registro["aviso"].append)
    m.aviso_terminado.connect(lambda: registro.__setitem__("fin_aviso", registro["fin_aviso"] + 1))
    m.expirada.connect(lambda: registro.__setitem__("expirada", registro["expirada"] + 1))
    m.segundos_restantes.connect(registro["resto"].append)
    m.iniciar(instalar_filtro=False)
    return m, r, registro


def vaciar_pool():
    QThreadPool.globalInstance().waitForDone()
    QApplication.processEvents()


def test_aviso_a_los_n_menos_30_y_expirada_a_n(qapp):
    m, r, reg = crear(qapp, 100, 30)
    r.avanzar(69)
    m.tick()
    assert reg["aviso"] == [] and reg["resto"][-1] == 31
    r.avanzar(1)
    m.tick()
    assert reg["aviso"] == [30]
    for _ in range(5):
        r.avanzar(1)
        m.tick()
    assert reg["aviso"] == [30, 29, 28, 27, 26, 25]
    r.avanzar(24)
    m.tick()
    assert reg["aviso"][-1] == 1 and reg["expirada"] == 0
    r.avanzar(1)
    m.tick()
    assert reg["expirada"] == 1 and reg["resto"][-1] == 0
    assert not m.activo
    r.avanzar(5)
    m.tick()
    assert reg["expirada"] == 1


def test_actividad_reinicia_y_cierra_aviso(qapp):
    m, r, reg = crear(qapp, 100, 30)
    r.avanzar(80)
    m.tick()
    assert reg["aviso"]
    m.marcar_actividad()
    assert reg["fin_aviso"] == 1 and m.restantes() == 100
    r.avanzar(60)
    m.tick()
    assert reg["expirada"] == 0
    r.avanzar(40)
    m.tick()
    assert reg["expirada"] == 1


def test_cambio_de_vista_cuenta_como_actividad(qapp):
    m, r, reg = crear(qapp, 100, 30)
    r.avanzar(90)
    m.marcar_actividad_vista()
    assert m.restantes() == 100


def test_actualizar_config_en_caliente(qapp):
    m, r, reg = crear(qapp, 100, 30)
    r.avanzar(50)
    m.tick()
    assert not reg["aviso"]
    m.actualizar_config(60, 30)             # ahora faltan 10 s: entra en aviso sin reiniciar
    assert reg["aviso"] == [10]
    m.actualizar_config(300, 30)            # amplia: sale del aviso
    assert reg["fin_aviso"] == 1 and m.restantes() == 250
    m.actualizar_config(40, 5)              # ya paso mas de lo permitido
    assert reg["expirada"] == 1


def test_reporte_con_throttle_y_flush_final(qapp):
    llamadas = []
    m, r, reg = crear(qapp, 300, 30, reportar=lambda: llamadas.append(threading.current_thread()))
    r.avanzar(1)
    m.marcar_actividad()                    # dentro del throttle (el login ya renovo)
    vaciar_pool()
    assert llamadas == []
    r.avanzar(10)
    m.tick()                                # vence el throttle: sale la actividad retenida
    vaciar_pool()
    assert len(llamadas) == 1
    assert llamadas[0] is not threading.main_thread()      # nunca en el hilo de la GUI
    r.avanzar(11)
    m.marcar_actividad()                    # fuera de throttle: inmediato
    vaciar_pool()
    assert len(llamadas) == 2
    m.marcar_actividad()
    m.marcar_actividad()
    vaciar_pool()
    assert len(llamadas) == 2
    m.marcar_actividad(forzar_reporte=True)
    vaciar_pool()
    assert len(llamadas) == 3
    r.avanzar(5)
    m.tick()
    vaciar_pool()
    assert len(llamadas) == 3               # sin actividad pendiente no hay reporte


def test_sin_actividad_no_se_reporta(qapp):
    llamadas = []
    m, r, reg = crear(qapp, 300, 30, reportar=lambda: llamadas.append(1))
    for _ in range(5):
        r.avanzar(20)
        m.tick()                            # solo temporizador/refresco: no es actividad
    vaciar_pool()
    assert llamadas == []


def test_fallo_del_reporte_no_rompe(qapp):
    def mal():
        raise RuntimeError("red caida")
    m, r, reg = crear(qapp, 300, 30, reportar=mal)
    r.avanzar(11)
    m.marcar_actividad()
    vaciar_pool()
    r.avanzar(11)
    m.marcar_actividad()
    vaciar_pool()
    assert m.activo


def test_filtro_de_eventos_teclado_raton_rueda(qapp):
    m, r, reg = crear(qapp, 100, 30, umbral_movimiento=8.0)
    w = QWidget()
    w.show()
    qapp.installEventFilter(m)
    try:
        def probar(evento, esperado):
            r.avanzar(10)
            antes = m.restantes()
            qapp.sendEvent(w, evento)
            assert (m.restantes() > antes) is esperado, evento.type()

        probar(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_A, Qt.KeyboardModifier.NoModifier, "a"), True)
        probar(QMouseEvent(QEvent.Type.MouseButtonPress, QPointF(5, 5), QPointF(5, 5),
                           Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
                           Qt.KeyboardModifier.NoModifier), True)
        probar(QWheelEvent(QPointF(5, 5), QPointF(5, 5), QPoint(0, 0), QPoint(0, 120),
                           Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
                           Qt.ScrollPhase.NoScrollPhase, False), True)

        def mover(x):
            return QMouseEvent(QEvent.Type.MouseMove, QPointF(x, 0), QPointF(x, 0),
                               Qt.MouseButton.NoButton, Qt.MouseButton.NoButton,
                               Qt.KeyboardModifier.NoModifier)
        qapp.sendEvent(w, mover(100))       # primera posicion: referencia
        probar(mover(103), False)           # bajo el umbral
        probar(mover(120), True)            # sobre el umbral
        # eventos de otro tipo (pintado, foco, temporizador) no cuentan
        probar(QEvent(QEvent.Type.Paint), False)
    finally:
        qapp.removeEventFilter(m)
        w.close()
        m.detener()


def test_eventos_sinteticos_ignorados_por_defecto(qapp):
    m, r, reg = crear(qapp, 100, 30, solo_espontaneos=True)
    w = QWidget()
    qapp.installEventFilter(m)
    try:
        r.avanzar(10)
        qapp.sendEvent(w, QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_A,
                                    Qt.KeyboardModifier.NoModifier, "a"))
        assert m.restantes() == 90          # sendEvent no es espontaneo
    finally:
        qapp.removeEventFilter(m)
        m.detener()


def test_workers_devuelven_al_hilo_gui(qapp, espera):
    res = {}

    def trabajo():
        res["hilo_trabajo"] = threading.current_thread()
        return 42
    ejecutar(trabajo, lambda v: res.update(v=v, hilo_cb=threading.current_thread()),
             lambda e: res.update(err=e))
    assert espera(lambda: "v" in res)
    assert res["v"] == 42
    assert res["hilo_trabajo"] is not threading.main_thread()
    assert res["hilo_cb"] is threading.main_thread()

    ejecutar(lambda: 1 / 0, None, lambda e: res.update(err=e))
    assert espera(lambda: "err" in res) and isinstance(res["err"], ZeroDivisionError)
