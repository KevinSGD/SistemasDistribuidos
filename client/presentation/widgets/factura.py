"""Documento de factura con aspecto realista (todo pintado por codigo)."""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QFrame, QGridLayout, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from ..styles.theme import COLORES, fmt_moneda


def _lbl(texto, color, px, peso=400, align=None, tachado=False) -> QLabel:
    l = QLabel(str(texto))
    deco = " text-decoration: line-through;" if tachado else ""
    l.setStyleSheet(f"color: {color}; font-size: {px}px; font-weight: {peso}; border: none;{deco}")
    if align:
        l.setAlignment(align)
    return l


class DocumentoFactura(QFrame):
    """Muestra una factura con el esquema ``shared.schemas.FacturaOut``
    (``model_dump()`` o dict equivalente). NO recalcula montos: muestra lo recibido.

    numero, fecha (datetime o str), negocio {nombre_negocio, nit, moneda, ...},
    cliente {nombre, documento}, items [{nombre, cantidad, precio_original,
    descuento_pct, precio_final, subtotal}], subtotal (SIN descuento), ahorro,
    iva (monto; el servidor lo calcula sobre el precio ya con descuento),
    total (= subtotal - ahorro + iva), metodo_pago, efectivo_recibido, cambio.
    Opcionales de presentacion: ``resolucion`` (texto) e ``iva_pct`` (solo etiqueta).
    El subtotal de cada item es el de la linea ya con descuento.
    Si iva > 0 se muestra 'Base gravable' = subtotal - ahorro (resta de lo recibido).
    """

    def __init__(self, datos: dict, parent=None):
        super().__init__(parent)
        neg = datos.get("negocio") or {}
        if isinstance(neg, str):
            neg = {"nombre_negocio": neg}
        cli = datos.get("cliente") or {}
        if isinstance(cli, str):
            cli = {"nombre": cli}
        fecha = datos.get("fecha", "")
        if hasattr(fecha, "strftime"):
            fecha = fecha.strftime("%Y-%m-%d %H:%M")
        nombre_cli = cli.get("nombre", "")
        if cli.get("documento"):
            nombre_cli += f"  ({cli['documento']})"
        self.setObjectName("factura")
        self.setStyleSheet(
            f"QFrame#factura {{ background: {COLORES['superficie']};"
            f" border: 1px solid {COLORES['borde']}; border-radius: 4px; }}"
        )
        self.setMinimumWidth(520)
        m = neg.get("moneda") or datos.get("moneda", "$")
        R, L = Qt.AlignmentFlag.AlignRight, Qt.AlignmentFlag.AlignLeft
        root = QVBoxLayout(self)
        root.setContentsMargins(32, 28, 32, 24)
        root.setSpacing(6)

        # Encabezado: logo (monograma pintado) + negocio + NIT/resolucion
        cab = QHBoxLayout()
        inicial = (neg.get("nombre_negocio") or "?")[0].upper()
        logo = QLabel(inicial)
        logo.setFixedSize(52, 52)
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo.setStyleSheet(
            f"background: {COLORES['primario_texto']}; color: {COLORES['texto_sobre_primario']};"
            " border-radius: 10px; font-size: 26px; font-weight: 700;"
        )
        cab.addWidget(logo)
        col = QVBoxLayout()
        col.setSpacing(0)
        col.addWidget(_lbl(neg.get("nombre_negocio", ""), COLORES["primario_texto"], 22, 700))
        col.addWidget(_lbl(f"NIT {neg.get('nit', '')}", COLORES["texto_suave"], 12))
        cab.addLayout(col, 1)
        der = QVBoxLayout()
        der.setSpacing(0)
        der.addWidget(_lbl("Factura de Venta", COLORES["texto_suave"], 13, 400, R))
        der.addWidget(_lbl(f"No. {datos.get('numero', '')}", COLORES["primario_texto"], 14, 700, R))
        cab.addLayout(der)
        root.addLayout(cab)
        if datos.get("resolucion"):
            root.addWidget(_lbl(datos["resolucion"], COLORES["texto_suave"], 11))
        root.addWidget(self._linea())

        datos_g = QGridLayout()
        datos_g.setHorizontalSpacing(12)
        for i, (k, v) in enumerate([("Fecha", fecha), ("Cliente", nombre_cli)]):
            datos_g.addWidget(_lbl(k, COLORES["texto_suave"], 12), i, 0)
            datos_g.addWidget(_lbl(v, COLORES["texto"], 12, 700), i, 1)
        datos_g.setColumnStretch(1, 1)
        root.addLayout(datos_g)
        root.addSpacing(6)

        # Tabla de items
        g = QGridLayout()
        g.setHorizontalSpacing(14)
        g.setVerticalSpacing(0)
        heads = ["Producto", "Cant.", "Precio", "Desc.", "Subtotal"]
        for c, h in enumerate(heads):
            g.addWidget(_lbl(h, COLORES["primario_texto"], 13, 600, L if c == 0 else R), 0, c)
        for r, it in enumerate(datos.get("items", []), start=1):
            fila = QWidget()
            fila.setStyleSheet(f"background: {COLORES['fondo'] if r % 2 == 0 else COLORES['superficie']};")
            g.addWidget(fila, r, 0, 1, 5)
            pct = it.get("descuento_pct", 0)
            vals = [(it["nombre"], COLORES["texto_secundario"], 400, L),
                    (it["cantidad"], COLORES["texto_secundario"], 400, R),
                    (fmt_moneda(it.get("precio_original", it.get("precio", 0)), m),COLORES["texto_secundario"], 400, R),
                    (f"-{pct:g}%" if pct else "—", COLORES["peligro"] if pct else COLORES["texto_suave"],
                     700 if pct else 400, R),
                    (fmt_moneda(it["subtotal"], m), COLORES["texto_secundario"], 400, R)]
            for c, (t, col_, peso, al) in enumerate(vals):
                lb = _lbl(t, col_, 13, peso, al)
                lb.setStyleSheet(lb.styleSheet() + " background: transparent; padding: 7px 0;")
                g.addWidget(lb, r, c)
        g.setColumnStretch(0, 1)
        root.addLayout(g)
        root.addWidget(self._linea())

        # Totales
        tot = QGridLayout()
        tot.setColumnStretch(0, 1)
        subtotal = datos.get("subtotal", 0)
        ahorro = datos.get("ahorro", 0) or 0
        iva = datos.get("iva", 0) or 0
        filas = [("Subtotal sin descuento", fmt_moneda(subtotal, m), COLORES["texto_suave"], 400)]
        if ahorro:
            filas.append(("Ahorro total", "-" + fmt_moneda(ahorro, m), COLORES["exito_texto"], 700))
        if iva:
            pct = datos.get("iva_pct")
            filas.append(("Base gravable", fmt_moneda(subtotal - ahorro, m), COLORES["texto_suave"], 400))
            filas.append((f"IVA {pct:g}%" if pct else "IVA", fmt_moneda(iva, m), COLORES["texto_suave"], 400))
        for i, (k, v, c, p) in enumerate(filas):
            tot.addWidget(_lbl(k, COLORES["texto_suave"] if p == 400 else c, 13, p, R), i, 0)
            tot.addWidget(_lbl(v, c, 13, p, R), i, 1)
        n = len(filas)
        tot.addWidget(_lbl("TOTAL A PAGAR", COLORES["texto"], 15, 700, R), n, 0)
        tot.addWidget(_lbl(fmt_moneda(datos.get("total", 0), m), COLORES["primario_texto"], 18, 700, R), n, 1)
        root.addLayout(tot)

        if datos.get("efectivo_recibido") is not None:
            caja = QFrame()
            caja.setObjectName("cajaPago")
            caja.setStyleSheet(
                f"QFrame#cajaPago {{ background: {COLORES['exito_fondo']}; border: 1px solid {COLORES['exito_borde']};"
                " border-radius: 6px; }"
            )
            cl = QGridLayout(caja)
            cl.setContentsMargins(14, 10, 14, 10)
            cl.addWidget(_lbl("PAGO RECIBIDO", COLORES["exito_oscuro"], 11, 700), 0, 0, 1, 2)
            cl.addWidget(_lbl("Efectivo recibido", COLORES["texto_suave"], 12, 700), 1, 0)
            cl.addWidget(_lbl(fmt_moneda(datos["efectivo_recibido"], m), COLORES["texto"], 12, 700, R), 1, 1)
            cl.addWidget(_lbl("Cambio", COLORES["texto_suave"], 12, 700), 2, 0)
            cl.addWidget(_lbl(fmt_moneda(datos.get("cambio") or 0, m), COLORES["exito_texto"], 12, 700, R), 2, 1)
            root.addSpacing(8)
            root.addWidget(caja)

        root.addSpacing(10)
        root.addWidget(_lbl("Gracias por su compra", COLORES["texto_secundario"], 14, 700,
                            Qt.AlignmentFlag.AlignCenter))
        root.addWidget(_lbl("Documento generado por Inventario App. Resolución simulada, sin validez fiscal.",
                            COLORES["texto_suave"], 11, 400, Qt.AlignmentFlag.AlignCenter))

    @staticmethod
    def _linea() -> QFrame:
        f = QFrame()
        f.setFixedHeight(1)
        f.setStyleSheet(f"background: {COLORES['borde']}; border: none;")
        return f
