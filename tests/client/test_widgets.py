"""Tests de widgets y tema del cliente (offscreen, sin servidor)."""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PyQt6.QtCore import Qt  # noqa: E402
from PyQt6.QtWidgets import QApplication, QPushButton, QWidget  # noqa: E402

from client.presentation.styles.theme import (  # noqa: E402
    COLOR_NIVEL, COLORES, FUENTE, aplicar_tema, fmt_moneda, hoja_estilo,
)
from client.presentation.widgets import (  # noqa: E402
    BadgeNivel, Cargando, DialogoInactividad, DocumentoFactura, EstadoVacio, Esqueleto,
    IndicadorConexion, RelojSesion, TablaEstandar, TarjetaResumen, Toast,
)
from client.presentation.widgets._galeria import construir_galeria, datos_factura_demo  # noqa: E402


@pytest.fixture(scope="session")
def app():
    a = QApplication.instance() or QApplication([])
    aplicar_tema(a)
    return a


@pytest.fixture
def ventana(app):
    w = QWidget()
    w.resize(800, 600)
    w.show()
    yield w
    w.close()


# ---------------------------------------------------------------- tema
def test_tema_paleta_y_fuente(app):
    for k in ("fondo", "superficie", "borde", "texto", "texto_suave", "primario", "primario_hover",
              "primario_press", "exito", "peligro", "aviso"):
        assert COLORES[k].startswith("#") and len(COLORES[k]) == 7
    assert COLORES["primario"] == "#2563EB" and COLORES["primario_hover"] == "#1D4ED8"
    assert COLORES["primario_press"] == "#1E40AF"
    assert FUENTE["familia"] == "Segoe UI" and "DejaVu Sans" in FUENTE["familias"]
    assert set(COLOR_NIVEL) == {"critico", "alto", "medio", "normal"}
    assert COLOR_NIVEL["critico"] == ("#DC2626", "#FEE2E2")
    assert COLOR_NIVEL["alto"] == ("#D97706", "#FEF3C7")
    assert COLOR_NIVEL["medio"] == ("#CA8A04", "#FEF9C3")


def test_hoja_estilo_resuelve_todo(app):
    qss = hoja_estilo()
    assert "$" not in qss
    for sel in ('QPushButton[variant="primary"]', 'QPushButton[variant="danger"]', "QLineEdit",
                "QTableWidget", "QComboBox", "QSpinBox", "QScrollBar", "QToolTip", "QMessageBox",
                ":disabled", ":focus", ":hover", ":pressed"):
        assert sel in qss
    assert app.styleSheet() == qss


def test_fmt_moneda():
    assert fmt_moneda(1234567) == "$1.234.567"
    assert fmt_moneda(1234.0) == "$1.234"
    assert fmt_moneda(1234.5) == "$1.234,50"
    assert fmt_moneda(1234.5, "COP") == "COP 1.234"
    assert fmt_moneda(0) == "$0"
    assert fmt_moneda(-500) == "-$500"


# ---------------------------------------------------------------- reloj
@pytest.mark.parametrize("n,nivel,color_,texto", [
    (125, "normal", "texto_suave", "Sesión: 02:05"),
    (31, "normal", "texto_suave", "Sesión: 00:31"),
    (30, "aviso", "aviso_texto", "Sesión: 00:30"),
    (11, "aviso", "aviso_texto", "Sesión: 00:11"),
    (10, "peligro", "peligro", "Sesión: 00:10"),
    (0, "peligro", "peligro", "Sesión: 00:00"),
    (-5, "peligro", "peligro", "Sesión: 00:00"),
])
def test_reloj_sesion_colores(app, n, nivel, color_, texto):
    r = RelojSesion()
    r.set_segundos(n)
    assert r.nivel == nivel
    assert r.texto == texto
    assert r.color_actual == COLORES[color_]
    assert COLORES[color_] in r._label.styleSheet()


# ---------------------------------------------------------------- conexion
def test_indicador_conexion(app):
    i = IndicadorConexion()
    i.set_estado(True, "Servidor en línea")
    assert i.conectado and i._texto.text() == "Servidor en línea"
    assert i._punto._color == COLORES["exito"]
    i.set_estado(False, "Servidor desconectado")
    assert not i.conectado and i._punto._color == COLORES["peligro"]


# ---------------------------------------------------------------- dialogo
def test_dialogo_inactividad_cuenta_regresiva(app):
    d = DialogoInactividad(30)
    assert d.isModal()
    assert d.texto_cuenta == "30"
    d.actualizar(9)
    assert d.texto_cuenta == "9"
    assert COLORES["peligro"] in d._cuenta.styleSheet()
    d.actualizar(25)
    assert COLORES["aviso_texto"] in d._cuenta.styleSheet()
    d.actualizar(1)
    assert d._sub.text() == "segundo restante"
    d.actualizar(-3)
    assert d.texto_cuenta == "0"


def test_dialogo_inactividad_boton_emite_y_cierra(app):
    d = DialogoInactividad(20)
    cuenta = []
    d.continuar.connect(lambda: cuenta.append(1))
    d.open()
    assert d.isVisible()
    boton = d.findChild(QPushButton)
    assert boton.text() == "Seguir conectado" and boton.hasFocus() or boton.isDefault()
    boton.click()
    assert cuenta == [1]
    assert not d.isVisible()


def test_dialogo_inactividad_cerrar_aviso_no_emite(app):
    d = DialogoInactividad(20)
    cuenta = []
    d.continuar.connect(lambda: cuenta.append(1))
    d.open()
    d.cerrar_aviso()
    assert not d.isVisible()
    assert cuenta == []


def test_dialogo_inactividad_escape_cuenta_como_continuar(app):
    d = DialogoInactividad(20)
    cuenta = []
    d.continuar.connect(lambda: cuenta.append(1))
    d.open()
    d.reject()
    assert cuenta == [1]
    assert not d.isVisible()


# ---------------------------------------------------------------- toast
def test_toast_apila_y_no_es_modal(ventana):
    t1 = Toast.mostrar(ventana, "Uno", "info", duracion_ms=60000)
    t2 = Toast.mostrar(ventana, "Dos", "exito", duracion_ms=60000)
    t3 = Toast.mostrar(ventana, "Tres", "error", duracion_ms=60000)
    assert Toast.activos(ventana) == [t1, t2, t3]
    assert t1.parent() is ventana and not t1.isWindow()
    # esquina inferior derecha, el mas reciente abajo
    assert t3.geometry().right() < ventana.width() and t3.geometry().bottom() < ventana.height()
    assert t3.y() > t2.y() > t1.y()
    assert t1.x() == t2.x() == t3.x() == ventana.width() - 16 - t1.width()
    assert t2.geometry().bottom() < t3.y()  # sin solaparse
    # al cerrar uno, los demas se reacomodan
    y3 = t3.y()
    t3.cerrar()
    assert Toast.activos(ventana) == [t1, t2]
    assert t2.y() >= y3  # t2 bajo a ocupar el lugar libre
    assert t2.geometry().bottom() == ventana.height() - 16 - 1
    t1.cerrar()
    t2.cerrar()
    assert Toast.activos(ventana) == []


def test_toast_altura_real_y_sin_solape(ventana):
    corto = Toast.mostrar(ventana, "Corto", "info", duracion_ms=60000)
    largo = Toast.mostrar(
        ventana, "No se pudo contactar al servidor. Revisa tu red e intenta de nuevo en unos segundos "
                 "porque la conexion se perdio durante la operacion.", "error", duracion_ms=60000)
    ultimo = Toast.mostrar(ventana, "Ultimo", "exito", duracion_ms=60000)
    tl = largo.fontMetrics().boundingRect(0, 0, 326, 100000, int(Qt.TextFlag.TextWordWrap), largo.text())
    assert largo.height() >= tl.height() + 22  # cabe todo el texto
    assert tl.height() > corto.fontMetrics().height() * 1.5  # realmente es multilinea
    assert largo.height() > corto.height()
    ts = Toast.activos(ventana)
    for arriba, abajo in zip(ts, ts[1:]):
        assert arriba.geometry().bottom() < abajo.geometry().top()  # no se solapan
    assert ultimo.geometry().bottom() == ventana.height() - 16 - 1
    for t in ts:
        t.cerrar()


def test_toast_se_cierra_solo(ventana):
    t = Toast.mostrar(ventana, "Efimero", "aviso", duracion_ms=0)
    t._anim.setDuration(1)
    t._anim.stop()
    t._timer.stop()
    t._anim.start()
    for _ in range(200):
        QApplication.processEvents()
        if not Toast.activos(ventana):
            break
        import time
        time.sleep(0.005)
    assert Toast.activos(ventana) == []


def test_toast_tipo_desconocido_cae_a_info(ventana):
    t = Toast.mostrar(ventana, "x", "inexistente", duracion_ms=60000)
    assert t.tipo == "info"
    t.cerrar()


def test_toast_reposiciona_al_redimensionar(ventana):
    t = Toast.mostrar(ventana, "x", "info", duracion_ms=60000)
    ventana.resize(1000, 700)
    QApplication.processEvents()
    assert t.x() == 1000 - 16 - t.width()
    assert t.geometry().bottom() == 700 - 16 - 1
    t.cerrar()


# ---------------------------------------------------------------- resto
@pytest.mark.parametrize("entrada,nivel", [("crítico", "critico"), ("Crítico", "critico"), ("critico", "critico"),
                                           ("alto", "alto"), ("medio", "medio"), ("normal", "normal"),
                                           ("loquesea", "normal")])
def test_badge_nivel(app, entrada, nivel):
    b = BadgeNivel(entrada)
    assert b.nivel == nivel
    texto, fondo = COLOR_NIVEL[nivel]
    assert texto in b.styleSheet() and fondo in b.styleSheet()
    assert b.text() == {"critico": "Crítico", "alto": "Alto", "medio": "Medio", "normal": "Normal"}[nivel]


def test_tarjeta_resumen(app):
    t = TarjetaResumen("Críticos", 5, "nivel_critico")
    assert t.titulo == "Críticos" and t.valor == "5"
    assert t.color_valor == COLORES["nivel_critico"]
    t.set_valor(7)
    assert t.valor == "7"
    assert TarjetaResumen("X", 1, "#123456").color_valor == "#123456"


def test_estado_vacio_y_error(app):
    e = EstadoVacio("✓", "Sin alertas", "Todo bien")
    assert e.boton is None
    err = EstadoVacio.error_conexion()
    disparos = []
    err.accion.connect(lambda: disparos.append(1))
    err.boton.click()
    assert disparos == [1]


def test_cargando_overlay(ventana):
    c = Cargando(ventana, "Cargando datos")
    assert not c.isVisible() and not c.activo
    c.iniciar()
    assert c.isVisible() and c.activo
    assert c.geometry() == ventana.rect()
    ventana.resize(500, 400)
    QApplication.processEvents()
    assert c.geometry() == ventana.rect()
    a0 = c._angulo
    c._girar()
    assert c._angulo != a0
    c.grab()  # pinta sin error
    c.detener()
    assert not c.isVisible() and not c.activo


def test_esqueleto(ventana):
    e = Esqueleto(3, ventana)
    e.show()
    e._tick()
    e.grab()
    assert e._timer.isActive()
    e.hide()
    assert not e._timer.isActive()


def test_tabla_estandar(app):
    t = TablaEstandar(["Producto", "Stock"])
    t.set_filas([["B", 12], ["A", 4], ["C", 30]])
    assert t.rowCount() == 3 and t.columnCount() == 2
    assert t.editTriggers() == t.EditTrigger.NoEditTriggers
    assert t.alternatingRowColors() and t.isSortingEnabled()
    assert t.selectionBehavior() == t.SelectionBehavior.SelectRows
    t.sortItems(1, Qt.SortOrder.AscendingOrder)
    assert [t.texto(r, 1) for r in range(3)] == ["4", "12", "30"]  # numerico, no lexicografico
    t.sortItems(0, Qt.SortOrder.AscendingOrder)
    assert [t.texto(r, 0) for r in range(3)] == ["A", "B", "C"]


def test_factura_documento(app):
    f = DocumentoFactura(datos_factura_demo())
    f.grab()
    from PyQt6.QtWidgets import QLabel
    textos = [lb.text() for lb in f.findChildren(QLabel)]
    for esperado in ("Minimercado La Esperanza", "NIT 900.123.456-7", "No. FV-000124", "TOTAL A PAGAR",
                     "IVA 19%", "Gracias por su compra"):
        assert esperado in textos
    assert any("Resolución" in t for t in textos)


def test_factura_muestra_valores_recibidos_sin_recalcular(app):
    from PyQt6.QtWidgets import QLabel
    d = datos_factura_demo()
    # IVA sobre el precio ya con descuento: total = (subtotal - ahorro) + iva
    base = d["subtotal"] - d["ahorro"]
    assert base + d["iva"] == d["total"]
    doc = DocumentoFactura(d)  # referencia viva: si no, Qt destruye los hijos
    textos = [lb.text() for lb in doc.findChildren(QLabel)]
    for esperado in (fmt_moneda(d["subtotal"]), "-" + fmt_moneda(d["ahorro"]), fmt_moneda(base),
                     fmt_moneda(d["iva"]), fmt_moneda(d["total"]), fmt_moneda(d["efectivo_recibido"]),
                     fmt_moneda(d["cambio"])):
        assert esperado in textos, esperado
    # valores arbitrarios (no coherentes) se muestran tal cual: el widget no recalcula
    d2 = dict(d, total=12345, iva=777)
    doc2 = DocumentoFactura(d2)
    t2 = [lb.text() for lb in doc2.findChildren(QLabel)]
    assert fmt_moneda(12345) in t2 and fmt_moneda(777) in t2


def test_tabla_alineacion_encabezado(app):
    t = TablaEstandar(["Producto", "Stock"])
    t.set_filas([["A", 4]])
    izq = Qt.AlignmentFlag.AlignLeft
    der = Qt.AlignmentFlag.AlignRight
    assert t.horizontalHeaderItem(0).textAlignment() & izq
    assert t.horizontalHeaderItem(1).textAlignment() & der
    assert t.item(0, 1).textAlignment() & der


def test_galeria_construye(app):
    g = construir_galeria()
    g.resize(980, 1400)
    g.grab()
    g.close()


def test_boton_deshabilitado_estilo(app):
    assert ":disabled" in app.styleSheet()
    b = QPushButton("x")
    b.setProperty("variant", "primary")
    b.setEnabled(False)
    assert not b.isEnabled()
