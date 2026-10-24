"""Galeria de widgets y tema.

Uso:  python -m client.presentation.widgets._galeria [--captura RUTA.png]
"""
from __future__ import annotations

import sys

from PyQt6.QtWidgets import (
    QApplication, QComboBox, QGridLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QScrollArea, QSpinBox, QVBoxLayout, QWidget,
)

from ..styles.theme import COLORES, aplicar_tema, fmt_moneda
from . import (
    BadgeNivel, Cargando, DialogoInactividad, DocumentoFactura, EstadoVacio, Esqueleto,
    IndicadorConexion, RelojSesion, TablaEstandar, TarjetaResumen, Toast,
)


def _grupo(titulo: str, lay) -> QGroupBox:
    g = QGroupBox(titulo)
    g.setStyleSheet(
        f"QGroupBox {{ background: {COLORES['superficie']}; border: 1px solid {COLORES['borde']};"
        " border-radius: 8px; margin-top: 12px; padding: 14px 12px 12px 12px; font-weight: 700; }"
        f"QGroupBox::title {{ subcontrol-origin: margin; left: 12px; color: {COLORES['texto_suave']}; }}"
    )
    g.setLayout(lay)
    return g


def datos_factura_demo() -> dict:
    """Esquema FacturaOut. IVA sobre el precio ya con descuento:
    base = 22800 - 3645 = 19155; iva = 3639; total = base + iva = 22794."""
    return {
        "numero": "FV-000124", "fecha": "2026-10-24 14:32",
        "negocio": {"nombre_negocio": "Minimercado La Esperanza", "nit": "900.123.456-7",
                    "direccion": "Cra 7 # 12-34", "telefono": "3000000000", "moneda": "$"},
        "cliente": {"nombre": "Carlos Pérez", "documento": "1020304050"},
        "resolucion": "Resolución DIAN simulada No. 18760000001 del 2026-01-01, rango 1 a 5000",
        "items": [
            {"nombre": "Leche entera 1L", "cantidad": 2, "precio_original": 4200,
             "descuento_pct": 30, "precio_final": 2940, "subtotal": 5880},
            {"nombre": "Yogur fresa 200g", "cantidad": 3, "precio_original": 2500,
             "descuento_pct": 15, "precio_final": 2125, "subtotal": 6375},
            {"nombre": "Pan tajado", "cantidad": 1, "precio_original": 6900,
             "descuento_pct": 0, "precio_final": 6900, "subtotal": 6900},
        ],
        "subtotal": 22800, "ahorro": 3645, "iva": 3639, "iva_pct": 19, "total": 22794,
        "metodo_pago": "efectivo", "efectivo_recibido": 25000, "cambio": 2206,
    }


def construir_galeria() -> QWidget:
    raiz = QWidget()
    raiz.setWindowTitle("Galería de widgets")
    raiz.setStyleSheet(f"QWidget#raiz {{ background: {COLORES['fondo']}; }}")
    raiz.setObjectName("raiz")
    col = QVBoxLayout(raiz)
    col.setContentsMargins(20, 16, 20, 16)

    # Barra superior
    barra = QHBoxLayout()
    t = QLabel("Inventario App")
    t.setStyleSheet(f"color: {COLORES['primario_texto']}; font-size: 15px; font-weight: 700;")
    barra.addWidget(t)
    barra.addStretch(1)
    ind = IndicadorConexion()
    ind.set_estado(True, "Servidor en línea")
    ind2 = IndicadorConexion()
    ind2.set_estado(False, "Servidor desconectado")
    barra.addWidget(ind)
    barra.addWidget(ind2)
    for n in (240, 25, 8):
        r = RelojSesion()
        r.set_segundos(n)
        barra.addWidget(r)
    col.addLayout(barra)

    # Tarjetas + badges
    fila = QHBoxLayout()
    for titulo, val, c in (("Total", 42, "nivel_normal"), ("Críticos", 5, "nivel_critico"),
                           ("Riesgo Alto", 9, "nivel_alto"), ("Riesgo Medio", 12, "nivel_medio")):
        fila.addWidget(TarjetaResumen(titulo, val, c))
    col.addLayout(fila)
    b = QHBoxLayout()
    for n in ("critico", "alto", "medio", "normal"):
        b.addWidget(BadgeNivel(n))
    b.addStretch(1)
    b.addWidget(QLabel("Moneda:  " + fmt_moneda(1234567) + "   " + fmt_moneda(1234.5) + "   "
                       + fmt_moneda(1234567, "COP")))
    col.addLayout(b)

    # Botones y entradas
    ctr = QGridLayout()
    for i, (txt, var, dis) in enumerate((("Primario", "primary", False), ("Secundario", None, False),
                                         ("Peligro", "danger", False), ("Deshabilitado", "primary", True))):
        btn = QPushButton(txt)
        if var:
            btn.setProperty("variant", var)
        btn.setEnabled(not dis)
        ctr.addWidget(btn, 0, i)
    le = QLineEdit()
    le.setPlaceholderText("Usuario")
    cb = QComboBox()
    cb.addItems(["Todos", "Crítico", "Alto"])
    sp = QSpinBox()
    sp.setValue(3)
    ctr.addWidget(le, 1, 0)
    ctr.addWidget(cb, 1, 1)
    ctr.addWidget(sp, 1, 2)
    col.addWidget(_grupo("Controles", ctr))

    # Tabla
    tabla = TablaEstandar(["Producto", "Nivel", "Stock", "Precio"])
    tabla.set_filas([["Leche entera", "Crítico", 4, 4200], ["Yogur", "Alto", 12, 2500],
                     ["Pan tajado", "Medio", 30, 6900]], formateadores={3: fmt_moneda})
    tabla.setFixedHeight(190)
    lt = QVBoxLayout()
    lt.addWidget(tabla)
    col.addWidget(_grupo("TablaEstandar", lt))

    # Estados
    est = QHBoxLayout()
    est.addWidget(EstadoVacio("✓", "Sin alertas", "Todos los productos están en buen estado."))
    est.addWidget(EstadoVacio.error_conexion())
    sk = QVBoxLayout()
    sk.addWidget(Esqueleto(3))
    est.addLayout(sk, 1)
    cont = QWidget()
    cont.setMinimumSize(180, 130)
    cg = QVBoxLayout(cont)
    cg.addWidget(QLabel("Contenido bajo overlay"))
    cargando = Cargando(cont, "Cargando…")
    cargando.iniciar()
    est.addWidget(cont)
    col.addWidget(_grupo("Estados: vacío, error de conexión, esqueleto, cargando", est))

    # Interactivos
    inter = QHBoxLayout()
    for tipo in ("info", "exito", "aviso", "error"):
        bt = QPushButton(f"Toast {tipo}")
        bt.clicked.connect(lambda _=False, t_=tipo: Toast.mostrar(raiz, f"Mensaje de tipo {t_}", t_))
        inter.addWidget(bt)
    bd = QPushButton("Diálogo de inactividad")

    def abrir():
        d = DialogoInactividad(30, raiz)
        d.open()
    bd.clicked.connect(abrir)
    inter.addWidget(bd)
    col.addWidget(_grupo("Interactivos", inter))

    fac = DocumentoFactura(datos_factura_demo())
    lf = QVBoxLayout()
    lf.addWidget(fac)
    col.addWidget(_grupo("Factura", lf))
    raiz._cargando = cargando  # evitar GC
    return raiz


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    app = QApplication.instance() or QApplication(sys.argv)
    aplicar_tema(app)
    cont = construir_galeria()
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setWidget(cont)
    scroll.resize(1000, 900)
    if "--captura" in argv:
        ruta = argv[argv.index("--captura") + 1]
        cont.resize(980, cont.sizeHint().height())
        Toast.mostrar(cont, "Guardado correctamente", "exito", duracion_ms=60000)
        Toast.mostrar(cont, "Stock bajo en 3 productos", "aviso", duracion_ms=60000)
        Toast.mostrar(cont, "No se pudo contactar al servidor", "error", duracion_ms=60000)
        cont.grab().save(ruta)
        return 0
    scroll.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
