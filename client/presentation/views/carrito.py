"""Panel del carrito (derecha de la ventana del comprador). La logica vive en `Carrito`."""
from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

from ..styles.theme import COLORES, fmt_moneda
from .carrito_modelo import Carrito, LineaCarrito


def _sep() -> QFrame:
    s = QFrame()
    s.setFixedHeight(1)
    s.setStyleSheet(f"background: {COLORES['borde']}; border: none;")
    return s


class FilaCarrito(QFrame):
    """Una linea: nombre, x, -/cantidad/+, subtotal. Resaltada si hay aviso."""

    mas = pyqtSignal(int)
    menos = pyqtSignal(int)
    quitar = pyqtSignal(int)

    def __init__(self, linea: LineaCarrito, moneda: str, parent=None):
        super().__init__(parent)
        pid = linea.producto_id
        self.producto_id = pid
        self.setObjectName("filaCarrito")
        if not linea.disponible:
            borde, fondo = COLORES["peligro"], COLORES["peligro_fondo"]
        elif linea.con_aviso:
            borde, fondo = COLORES["aviso"], COLORES["aviso_fondo"]
        else:
            borde, fondo = COLORES["borde"], COLORES["fondo"]
        self.resaltada = linea.con_aviso
        self.setStyleSheet(
            f"QFrame#filaCarrito {{ background: {fondo}; border: 1px solid {borde};"
            " border-radius: 6px; }")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(4)

        top = QHBoxLayout()
        nombre = QLabel(linea.nombre)
        nombre.setWordWrap(True)
        nombre.setStyleSheet(f"font-size: 13px; font-weight: 700; color: {COLORES['texto']};"
                             " border: none; background: transparent;")
        self.btn_quitar = QPushButton("×")
        self.btn_quitar.setObjectName("btnQuitarItem")
        self.btn_quitar.setFixedSize(24, 24)
        self.btn_quitar.setToolTip("Quitar del carrito")
        self.btn_quitar.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_quitar.setAccessibleName(f"Quitar {linea.nombre}")
        self.btn_quitar.setStyleSheet(
            f"QPushButton {{ background: transparent; color: {COLORES['texto_suave']}; border: none;"
            " font-size: 17px; font-weight: 700; border-radius: 4px; padding: 0; min-height: 0; }"
            f"QPushButton:hover {{ color: {COLORES['peligro']};"
            f" background: {COLORES['hover_peligro_fondo']}; }}")
        self.btn_quitar.clicked.connect(lambda: self.quitar.emit(pid))
        top.addWidget(nombre, 1)
        top.addWidget(self.btn_quitar)
        lay.addLayout(top)

        pct = f" · -{linea.descuento:g}%" if linea.descuento else ""
        unit = QLabel(f"{fmt_moneda(linea.precio_final, moneda, linea.decimales)} c/u{pct}")
        unit.setStyleSheet(f"font-size: 11px; color: {COLORES['texto_suave']};"
                           " border: none; background: transparent;")
        lay.addWidget(unit)

        bot = QHBoxLayout()
        bot.setSpacing(6)
        estilo_qty = (
            f"QPushButton {{ background: {COLORES['superficie']}; color: {COLORES['texto_secundario']};"
            f" border: 1px solid {COLORES['borde_input']}; border-radius: 4px; font-size: 15px;"
            " font-weight: 700; padding: 0; min-height: 0; }"
            f"QPushButton:hover {{ background: {COLORES['superficie_alt']}; }}"
            f"QPushButton:disabled {{ background: {COLORES['deshabilitado_fondo']};"
            f" color: {COLORES['deshabilitado_texto']}; }}")
        self.btn_menos = QPushButton("−")
        self.btn_menos.setFixedSize(28, 28)
        self.btn_menos.setStyleSheet(estilo_qty)
        self.btn_menos.setAccessibleName(f"Quitar una unidad de {linea.nombre}")
        self.btn_menos.clicked.connect(lambda: self.menos.emit(pid))
        self.lbl_cantidad = QLabel(str(linea.cantidad))
        self.lbl_cantidad.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_cantidad.setFixedWidth(32)
        self.lbl_cantidad.setStyleSheet(f"font-size: 13px; font-weight: 700; border: none;"
                                        f" color: {COLORES['texto']}; background: transparent;")
        self.btn_mas = QPushButton("+")
        self.btn_mas.setFixedSize(28, 28)
        self.btn_mas.setStyleSheet(estilo_qty)
        self.btn_mas.setAccessibleName(f"Agregar una unidad de {linea.nombre}")
        self.btn_mas.clicked.connect(lambda: self.mas.emit(pid))
        if not linea.disponible:
            self.btn_mas.setEnabled(False)
            self.btn_menos.setEnabled(False)
        self.lbl_subtotal = QLabel(fmt_moneda(linea.subtotal_final, moneda, linea.decimales))
        self.lbl_subtotal.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.lbl_subtotal.setStyleSheet(f"font-size: 13px; font-weight: 700; border: none;"
                                        f" color: {COLORES['texto']}; background: transparent;")
        bot.addWidget(self.btn_menos)
        bot.addWidget(self.lbl_cantidad)
        bot.addWidget(self.btn_mas)
        bot.addStretch(1)
        bot.addWidget(self.lbl_subtotal)
        lay.addLayout(bot)

        self.lbl_aviso: QLabel | None = None
        if linea.con_aviso:
            color = COLORES["peligro"] if not linea.disponible else COLORES["aviso_texto"]
            self.lbl_aviso = QLabel(linea.texto_aviso)
            self.lbl_aviso.setWordWrap(True)
            self.lbl_aviso.setStyleSheet(f"font-size: 11px; font-weight: 600; color: {color};"
                                         " border: none; background: transparent;")
            lay.addWidget(self.lbl_aviso)


class PanelCarrito(QFrame):
    ir_al_pago = pyqtSignal()
    vaciar_pedido = pyqtSignal()          # el padre confirma y llama a modelo.vaciar()
    aumentar = pyqtSignal(int)
    disminuir = pyqtSignal(int)
    quitar = pyqtSignal(int)

    def __init__(self, modelo: Carrito, parent=None):
        super().__init__(parent)
        self.modelo = modelo
        self.moneda = "$"
        self.iva_pct = 0.0
        self.decimales = 0
        self.setObjectName("panelCarrito")
        self.setStyleSheet(f"QFrame#panelCarrito {{ background: {COLORES['superficie']};"
                           f" border-left: 1px solid {COLORES['borde']}; }}")
        self.setMinimumWidth(330)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 22, 20, 20)
        lay.setSpacing(0)

        cab = QHBoxLayout()
        titulo = QLabel("Carrito")
        titulo.setStyleSheet(f"font-size: 16px; font-weight: 700; color: {COLORES['texto']};")
        self.lbl_items = QLabel("0 items")
        self.lbl_items.setStyleSheet(f"font-size: 12px; color: {COLORES['texto_suave']};")
        cab.addWidget(titulo)
        cab.addStretch(1)
        cab.addWidget(self.lbl_items)
        lay.addLayout(cab)
        lay.addSpacing(12)
        lay.addWidget(_sep())
        lay.addSpacing(10)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setMinimumHeight(180)
        self.scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        self._contenedor = QWidget()
        self._contenedor.setObjectName("contenedorCarrito")
        self._contenedor.setStyleSheet("QWidget#contenedorCarrito { background: transparent; }")
        self._filas = QVBoxLayout(self._contenedor)
        self._filas.setContentsMargins(0, 0, 4, 0)
        self._filas.setSpacing(8)
        self.scroll.setWidget(self._contenedor)
        lay.addWidget(self.scroll, 1)
        lay.addSpacing(12)
        lay.addWidget(_sep())
        lay.addSpacing(12)

        self.val_subtotal = self._fila_resumen(lay, "Subtotal sin descuento", "texto_secundario",
                                               12, 600)
        self.val_ahorro = self._fila_resumen(lay, "Ahorro", "exito", 12, 700)
        lay.addSpacing(6)
        lay.addWidget(_sep())
        lay.addSpacing(6)
        self.val_total = self._fila_resumen(lay, "Total", "primario_texto", 17, 700, 14)
        self.lbl_nota_iva = QLabel("")
        self.lbl_nota_iva.setWordWrap(True)
        self.lbl_nota_iva.setStyleSheet(f"font-size: 11px; color: {COLORES['texto_suave']};")
        lay.addWidget(self.lbl_nota_iva)
        lay.addSpacing(14)

        self.btn_pagar = QPushButton("Ir al pago")
        self.btn_pagar.setProperty("variant", "primary")
        self.btn_pagar.setMinimumHeight(44)
        self.btn_pagar.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_pagar.clicked.connect(self.ir_al_pago)
        self.btn_vaciar = QPushButton("Vaciar carrito")
        self.btn_vaciar.setMinimumHeight(36)
        self.btn_vaciar.clicked.connect(self.vaciar_pedido)
        lay.addWidget(self.btn_pagar)
        lay.addSpacing(6)
        lay.addWidget(self.btn_vaciar)
        self.refrescar()

    @staticmethod
    def _fila_resumen(lay: QVBoxLayout, texto: str, color: str, px: int, peso: int,
                      px_label: int | None = None) -> QLabel:
        fila = QHBoxLayout()
        fila.setContentsMargins(0, 2, 0, 2)
        l = QLabel(texto)
        l.setStyleSheet(f"font-size: {px_label or 12}px; color: "
                        f"{COLORES['texto'] if px_label else COLORES['texto_suave']};"
                        f" font-weight: {700 if px_label else 400};")
        v = QLabel("—")
        v.setStyleSheet(f"font-size: {px}px; color: {COLORES[color]}; font-weight: {peso};")
        v.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        fila.addWidget(l)
        fila.addStretch(1)
        fila.addWidget(v)
        lay.addLayout(fila)
        return v

    def configurar(self, moneda: str, iva_pct: float, decimales: int = 0) -> None:
        self.moneda, self.iva_pct = moneda or "$", float(iva_pct or 0)
        self.decimales = int(decimales or 0)
        self.modelo.decimales = self.decimales
        self.refrescar()

    def filas(self) -> list[FilaCarrito]:
        out = []
        for i in range(self._filas.count()):
            w = self._filas.itemAt(i).widget()
            if isinstance(w, FilaCarrito):
                out.append(w)
        return out

    def refrescar(self) -> None:
        pos = self.scroll.verticalScrollBar().value()
        while self._filas.count():
            it = self._filas.takeAt(0)
            w = it.widget()
            if w is not None:
                w.hide()
                w.deleteLater()
        m = self.modelo
        if not len(m):
            vacio = QLabel("El carrito está vacío.\nAgrega productos en oferta.")
            vacio.setAlignment(Qt.AlignmentFlag.AlignCenter)
            vacio.setStyleSheet(f"font-size: 12px; color: {COLORES['texto_suave']}; padding: 28px;")
            self._filas.addWidget(vacio)
        else:
            for l in m.lineas:
                f = FilaCarrito(l, self.moneda)
                f.mas.connect(self.aumentar)
                f.menos.connect(self.disminuir)
                f.quitar.connect(self.quitar)
                self._filas.addWidget(f)
        self._filas.addStretch(1)
        n = m.cantidad_total
        self.lbl_items.setText(f"{n} item{'s' if n != 1 else ''}")
        hay = len(m) > 0
        self.val_subtotal.setText(fmt_moneda(m.subtotal, self.moneda, self.decimales) if hay else "—")
        self.val_ahorro.setText(("-" + fmt_moneda(m.ahorro, self.moneda, self.decimales)) if hay and m.ahorro else "—")
        self.val_total.setText(fmt_moneda(m.total, self.moneda, self.decimales) if hay else "—")
        self.lbl_nota_iva.setText(
            f"IVA ({self.iva_pct:g}%) se suma al confirmar el pago." if hay and self.iva_pct else "")
        self.btn_pagar.setEnabled(hay)
        self.btn_vaciar.setEnabled(hay)
        self.btn_pagar.setToolTip("" if hay else "Agrega productos al carrito")
        self.scroll.verticalScrollBar().setValue(pos)
