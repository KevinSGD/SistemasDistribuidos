import os
import sys
import subprocess
import platform
from datetime import datetime

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QScrollArea, QFrame,
    QMessageBox, QDialog, QTableWidget, QTableWidgetItem,
    QHeaderView, QLineEdit, QTextBrowser
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QColor, QDoubleValidator

from risk_engine import RiskEngine
from database import get_session
from models import Venta, Producto
from config import CONFIG


# ══════════════════════════════════════════════════════════════════════════════
#  VENTANA PRINCIPAL DEL COMPRADOR
# ══════════════════════════════════════════════════════════════════════════════
class BuyerWindow(QMainWindow):

    def __init__(self, usuario):
        super().__init__()
        self.usuario  = usuario
        self.engine   = RiskEngine()
        self.session  = get_session()
        self.carrito: dict[int, dict] = {}   # {pid: {"item": dict, "cantidad": int}}
        self._resultados: dict = {}

        self.setWindowTitle("Tienda — Productos en oferta")
        self.setMinimumSize(1060, 680)

        central = QWidget()
        self.setCentralWidget(central)
        self._construir_ui(central)
        self._aplicar_estilos()

        self.timer = QTimer()
        self.timer.timeout.connect(self._actualizar_productos)
        self.timer.start(60000)
        self._actualizar_productos()

    # ── Construcción UI ───────────────────────────────────────────────────────
    def _construir_ui(self, central):
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._crear_barra())

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        body.addWidget(self._crear_panel_productos(), stretch=6)
        body.addWidget(self._crear_panel_carrito(),   stretch=3)

        wrapper = QWidget()
        wrapper.setObjectName("body_wrapper")
        wrapper.setLayout(body)
        root.addWidget(wrapper)

    # ── Barra superior ────────────────────────────────────────────────────────
    def _crear_barra(self) -> QFrame:
        barra = QFrame()
        barra.setObjectName("barra")
        barra.setFixedHeight(56)
        lay = QHBoxLayout(barra)
        lay.setContentsMargins(24, 0, 24, 0)

        app_lbl = QLabel("Inventario App")
        app_lbl.setObjectName("titulo_barra")

        user_lbl = QLabel(f"Hola, {self.usuario.nombre}")
        user_lbl.setObjectName("lbl_user_barra")

        btn = QPushButton("Cerrar sesión")
        btn.setObjectName("btn_cerrar_barra")
        btn.setFixedHeight(32)
        btn.clicked.connect(self._cerrar_sesion)

        lay.addWidget(app_lbl)
        lay.addStretch()
        lay.addWidget(user_lbl)
        lay.addSpacing(16)
        lay.addWidget(btn)
        return barra

    # ── Panel izquierdo: productos ────────────────────────────────────────────
    def _crear_panel_productos(self) -> QWidget:
        panel = QWidget()
        panel.setObjectName("panel_productos")
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(28, 24, 16, 24)
        lay.setSpacing(14)

        cab = QHBoxLayout()
        lbl = QLabel("Productos en oferta")
        lbl.setObjectName("titulo_seccion")
        self.lbl_conteo = QLabel("")
        self.lbl_conteo.setObjectName("lbl_conteo")
        cab.addWidget(lbl)
        cab.addStretch()
        cab.addWidget(self.lbl_conteo)
        lay.addLayout(cab)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setObjectName("scroll_productos")
        self._lista_widget = QWidget()
        self._lista_widget.setObjectName("lista_widget")
        self._lista_layout = QVBoxLayout(self._lista_widget)
        self._lista_layout.setSpacing(10)
        self._lista_layout.setContentsMargins(0, 0, 8, 0)
        scroll.setWidget(self._lista_widget)
        lay.addWidget(scroll)
        return panel

    # ── Panel derecho: carrito ────────────────────────────────────────────────
    def _crear_panel_carrito(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("panel_carrito")
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(16, 24, 24, 24)
        lay.setSpacing(0)

        # Cabecera
        cab = QHBoxLayout()
        self.lbl_titulo_carrito = QLabel("Carrito")
        self.lbl_titulo_carrito.setObjectName("titulo_carrito")
        self.lbl_items_count = QLabel("0 items")
        self.lbl_items_count.setObjectName("lbl_items_count")
        cab.addWidget(self.lbl_titulo_carrito)
        cab.addStretch()
        cab.addWidget(self.lbl_items_count)
        lay.addLayout(cab)
        lay.addSpacing(12)

        lay.addWidget(self._sep())
        lay.addSpacing(10)

        # Items
        scroll_c = QScrollArea()
        scroll_c.setWidgetResizable(True)
        scroll_c.setObjectName("scroll_carrito")
        scroll_c.setMinimumHeight(180)
        self._carrito_widget = QWidget()
        self._carrito_widget.setObjectName("carrito_items_widget")
        self._carrito_layout = QVBoxLayout(self._carrito_widget)
        self._carrito_layout.setSpacing(8)
        self._carrito_layout.setContentsMargins(0, 0, 0, 0)
        scroll_c.setWidget(self._carrito_widget)
        lay.addWidget(scroll_c, stretch=1)
        lay.addSpacing(12)
        lay.addWidget(self._sep())
        lay.addSpacing(12)

        # Resumen
        resumen = QWidget()
        resumen.setObjectName("resumen_widget")
        res_lay = QVBoxLayout(resumen)
        res_lay.setSpacing(6)
        res_lay.setContentsMargins(0, 0, 0, 0)
        self.lbl_subtotal = self._fila_precio("Subtotal:",  "", "resumen_label", "resumen_valor")
        self.lbl_ahorro   = self._fila_precio("Ahorro:",    "", "resumen_label", "ahorro_valor")
        self.lbl_total    = self._fila_precio("Total:",     "", "total_label",   "total_valor")
        res_lay.addLayout(self.lbl_subtotal)
        res_lay.addLayout(self.lbl_ahorro)
        res_lay.addSpacing(4)
        res_lay.addWidget(self._sep())
        res_lay.addSpacing(4)
        res_lay.addLayout(self.lbl_total)
        lay.addWidget(resumen)
        lay.addSpacing(16)

        # Botones
        self.btn_comprar = QPushButton("Ir al pago")
        self.btn_comprar.setObjectName("btn_comprar")
        self.btn_comprar.setFixedHeight(44)
        self.btn_comprar.clicked.connect(self._abrir_checkout)

        self.btn_vaciar = QPushButton("Vaciar carrito")
        self.btn_vaciar.setObjectName("btn_vaciar")
        self.btn_vaciar.setFixedHeight(36)
        self.btn_vaciar.clicked.connect(self._vaciar_carrito)

        lay.addWidget(self.btn_comprar)
        lay.addSpacing(6)
        lay.addWidget(self.btn_vaciar)
        return panel

    def _sep(self) -> QFrame:
        s = QFrame()
        s.setFrameShape(QFrame.Shape.HLine)
        s.setObjectName("sep_carrito")
        return s

    def _fila_precio(self, texto, valor, obj_lbl, obj_val):
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        lbl_t = QLabel(texto); lbl_t.setObjectName(obj_lbl)
        lbl_v = QLabel(valor); lbl_v.setObjectName(obj_val)
        row.addWidget(lbl_t)
        row.addStretch()
        row.addWidget(lbl_v)
        row._lbl_v = lbl_v
        return row

    # ── Lista de productos ────────────────────────────────────────────────────
    def _actualizar_productos(self):
        self._resultados = self.engine.escanear_inventario()

        while self._lista_layout.count():
            it = self._lista_layout.takeAt(0)
            if it.widget():
                it.widget().deleteLater()

        oferta = [
            (nivel, p)
            for nivel in ["critico", "alto", "medio"]
            for p in self._resultados.get(nivel, [])
            if p.get("descuento_sugerido", 0) > 0
        ]

        self.lbl_conteo.setText(f"{len(oferta)} producto{'s' if len(oferta) != 1 else ''}")

        if not oferta:
            aviso = QLabel("No hay productos en oferta en este momento.")
            aviso.setAlignment(Qt.AlignmentFlag.AlignCenter)
            aviso.setObjectName("aviso_vacio")
            self._lista_layout.addWidget(aviso)
        else:
            for nivel, item in oferta:
                self._lista_layout.addWidget(self._crear_tarjeta(nivel, item))

        self._lista_layout.addStretch()

    def _crear_tarjeta(self, nivel: str, item: dict) -> QFrame:
        colores = {
            "critico": ("#FEE2E2", "#DC2626"),
            "alto":    ("#FEF3C7", "#D97706"),
            "medio":   ("#FEF9C3", "#CA8A04"),
        }
        fondo, acento = colores.get(nivel, ("#F3F4F6", "#6B7280"))

        tarjeta = QFrame()
        tarjeta.setObjectName("tarjeta_prod")
        tarjeta.setStyleSheet(f"""
            QFrame#tarjeta_prod {{
                background-color: #FFFFFF;
                border: 1px solid #E5E7EB;
                border-left: 3px solid {acento};
                border-radius: 8px;
            }}
        """)
        lay = QHBoxLayout(tarjeta)
        lay.setContentsMargins(16, 12, 16, 12)
        lay.setSpacing(14)

        info = QVBoxLayout()
        info.setSpacing(3)
        nombre_lbl = QLabel(item["nombre"]); nombre_lbl.setObjectName("prod_nombre")
        detalle    = QLabel(
            f"{item.get('categoria', '')}  ·  Stock: <b>{item['stock']}</b> unidades"
        )
        detalle.setObjectName("prod_detalle")
        detalle.setTextFormat(Qt.TextFormat.RichText)
        motivo_lbl = QLabel(item["motivo"]); motivo_lbl.setObjectName("prod_motivo")
        info.addWidget(nombre_lbl)
        info.addWidget(detalle)
        info.addWidget(motivo_lbl)

        col_der = QVBoxLayout()
        col_der.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        col_der.setSpacing(6)

        badge = QLabel(f"  -{item['descuento_sugerido']:.0f}%  ")
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge.setStyleSheet(f"""
            color: white; background-color: {acento};
            font-size: 11px; font-weight: 700;
            padding: 2px 8px; border-radius: 4px;
        """)
        p_orig = QLabel(f"${item['precio_original']:,.0f}")
        p_orig.setObjectName("precio_orig")
        p_orig.setAlignment(Qt.AlignmentFlag.AlignRight)
        p_desc = QLabel(f"${item['precio_sugerido']:,.2f}")
        p_desc.setObjectName("precio_desc")
        p_desc.setAlignment(Qt.AlignmentFlag.AlignRight)

        btn_agregar = QPushButton("Agregar al carrito")
        btn_agregar.setObjectName("btn_agregar")
        btn_agregar.setFixedHeight(34)
        btn_agregar.clicked.connect(lambda _, i=item: self._agregar_al_carrito(i))
        if item["stock"] == 0:
            btn_agregar.setText("Sin stock")
            btn_agregar.setEnabled(False)

        col_der.addWidget(badge, alignment=Qt.AlignmentFlag.AlignRight)
        col_der.addWidget(p_orig)
        col_der.addWidget(p_desc)
        col_der.addWidget(btn_agregar)

        lay.addLayout(info,    stretch=3)
        lay.addLayout(col_der, stretch=2)
        return tarjeta

    # ── Lógica del carrito ────────────────────────────────────────────────────
    def _agregar_al_carrito(self, item: dict):
        pid = item["producto_id"]
        en_carrito = self.carrito.get(pid, {}).get("cantidad", 0)
        if en_carrito >= item["stock"]:
            QMessageBox.warning(self, "Stock insuficiente",
                f"Solo hay {item['stock']} unidades disponibles de {item['nombre']}.")
            return
        if pid in self.carrito:
            self.carrito[pid]["cantidad"] += 1
        else:
            self.carrito[pid] = {"item": item, "cantidad": 1}
        self._refrescar_carrito()

    def _cambiar_cantidad(self, pid: int, delta: int):
        if pid not in self.carrito:
            return
        entrada = self.carrito[pid]
        nueva   = entrada["cantidad"] + delta
        stock   = entrada["item"]["stock"]
        if nueva <= 0:
            self._eliminar_del_carrito(pid)
        elif nueva > stock:
            QMessageBox.warning(self, "Stock insuficiente",
                f"Solo hay {stock} unidades disponibles.")
        else:
            self.carrito[pid]["cantidad"] = nueva
            self._refrescar_carrito()

    def _eliminar_del_carrito(self, pid: int):
        self.carrito.pop(pid, None)
        self._refrescar_carrito()

    def _vaciar_carrito(self):
        if not self.carrito:
            return
        if QMessageBox.question(self, "Vaciar carrito",
            "¿Eliminar todos los productos del carrito?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        ) == QMessageBox.StandardButton.Yes:
            self.carrito.clear()
            self._refrescar_carrito()

    def _refrescar_carrito(self):
        while self._carrito_layout.count():
            it = self._carrito_layout.takeAt(0)
            if it.widget():
                it.widget().deleteLater()

        if not self.carrito:
            vacio = QLabel("El carrito está vacío")
            vacio.setAlignment(Qt.AlignmentFlag.AlignCenter)
            vacio.setObjectName("carrito_vacio")
            self._carrito_layout.addWidget(vacio)
            self._carrito_layout.addStretch()
            self._set_totales(0, 0, 0)
            self.btn_comprar.setEnabled(False)
            self.btn_vaciar.setEnabled(False)
            self.lbl_items_count.setText("0 items")
            return

        total_items = subtotal_orig = subtotal_desc = 0.0
        for pid, entrada in self.carrito.items():
            item     = entrada["item"]
            cantidad = entrada["cantidad"]
            total_items  += cantidad
            subtotal_orig += item["precio_original"] * cantidad
            subtotal_desc += item["precio_sugerido"]  * cantidad
            self._carrito_layout.addWidget(
                self._crear_fila_carrito(pid, item, cantidad)
            )

        self._carrito_layout.addStretch()
        n = int(total_items)
        self.lbl_items_count.setText(f"{n} item{'s' if n != 1 else ''}")
        self._set_totales(subtotal_orig, subtotal_desc, subtotal_orig - subtotal_desc)
        self.btn_comprar.setEnabled(True)
        self.btn_vaciar.setEnabled(True)

    def _crear_fila_carrito(self, pid: int, item: dict, cantidad: int) -> QFrame:
        fila = QFrame()
        fila.setObjectName("carrito_fila")
        lay = QVBoxLayout(fila)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(4)

        top = QHBoxLayout()
        nombre = QLabel(item["nombre"])
        nombre.setObjectName("carrito_nombre")
        nombre.setWordWrap(True)
        btn_del = QPushButton("×")
        btn_del.setObjectName("btn_del_item")
        btn_del.setFixedSize(22, 22)
        btn_del.clicked.connect(lambda _, p=pid: self._eliminar_del_carrito(p))
        top.addWidget(nombre, stretch=1)
        top.addWidget(btn_del)
        lay.addLayout(top)

        bot = QHBoxLayout()
        bot.setSpacing(6)
        btn_m = QPushButton("−"); btn_m.setObjectName("btn_qty"); btn_m.setFixedSize(26, 26)
        btn_m.clicked.connect(lambda _, p=pid: self._cambiar_cantidad(p, -1))
        lbl_q = QLabel(str(cantidad)); lbl_q.setObjectName("lbl_qty")
        lbl_q.setAlignment(Qt.AlignmentFlag.AlignCenter); lbl_q.setFixedWidth(30)
        btn_p = QPushButton("+"); btn_p.setObjectName("btn_qty"); btn_p.setFixedSize(26, 26)
        btn_p.clicked.connect(lambda _, p=pid: self._cambiar_cantidad(p, +1))
        lbl_sub = QLabel(f"${item['precio_sugerido'] * cantidad:,.2f}")
        lbl_sub.setObjectName("carrito_subtotal")
        lbl_sub.setAlignment(Qt.AlignmentFlag.AlignRight)
        bot.addWidget(btn_m); bot.addWidget(lbl_q); bot.addWidget(btn_p)
        bot.addStretch(); bot.addWidget(lbl_sub)
        lay.addLayout(bot)
        return fila

    def _set_totales(self, orig: float, desc: float, ahorro: float):
        m = CONFIG.get("moneda", "$")
        self.lbl_subtotal._lbl_v.setText(f"{m}{orig:,.2f}" if orig else "—")
        self.lbl_ahorro._lbl_v.setText(  f"- {m}{ahorro:,.2f}" if ahorro else "—")
        self.lbl_total._lbl_v.setText(   f"{m}{desc:,.2f}" if desc else "—")

    # ── Checkout ──────────────────────────────────────────────────────────────
    def _abrir_checkout(self):
        if not self.carrito:
            return
        dlg = CheckoutDialog(self.carrito, self.usuario, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._procesar_compra(
                dlg.monto_recibido,
                dlg.cambio
            )

    def _procesar_compra(self, monto_recibido: float, cambio: float):
        ahora  = datetime.now()
        numero = f"FACT-{ahora.strftime('%Y%m%d-%H%M%S')}"

        subtotal_orig = sum(
            e["item"]["precio_original"] * e["cantidad"]
            for e in self.carrito.values()
        )
        total_desc = sum(
            e["item"]["precio_sugerido"] * e["cantidad"]
            for e in self.carrito.values()
        )
        ahorro = subtotal_orig - total_desc

        try:
            for pid, entrada in self.carrito.items():
                item     = entrada["item"]
                cantidad = entrada["cantidad"]
                self.session.add(Venta(
                    producto_id        = pid,
                    cantidad           = cantidad,
                    precio_unitario    = item["precio_original"],
                    precio_final       = item["precio_sugerido"] * cantidad,
                    descuento_aplicado = item["descuento_sugerido"],
                ))
                prod = self.session.get(Producto, pid)
                if prod:
                    prod.stock = max(0, prod.stock - cantidad)
            self.session.commit()

        except Exception as e:
            self.session.rollback()
            QMessageBox.critical(self, "Error",
                f"No se pudo registrar la compra:\n{e}")
            return

        # Datos para la factura
        datos_factura = {
            "numero"         : numero,
            "fecha"          : ahora,
            "usuario"        : self.usuario,
            "carrito"        : dict(self.carrito),   # copia antes de limpiar
            "monto_recibido" : monto_recibido,
            "cambio"         : cambio,
            "subtotal_orig"  : subtotal_orig,
            "total_desc"     : total_desc,
            "ahorro"         : ahorro,
        }

        # Limpiar carrito y refrescar stock
        self.carrito.clear()
        self._refrescar_carrito()
        self._actualizar_productos()

        # Mostrar factura en la app
        dlg = InvoicePreviewDialog(datos_factura, self)
        dlg.exec()

    # ── Sesión ────────────────────────────────────────────────────────────────
    def _cerrar_sesion(self):
        if QMessageBox.question(self, "Cerrar sesión", "¿Deseas cerrar sesión?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        ) == QMessageBox.StandardButton.Yes:
            self.timer.stop()
            self.close()
            from ui.login import LoginWindow
            self._login = LoginWindow()
            self._login.login_exitoso.connect(self._reabrir)
            self._login.show()

    def _reabrir(self, usuario):
        import main as _main
        _main.abrir_ventana(usuario)

    # ── Estilos ───────────────────────────────────────────────────────────────
    def _aplicar_estilos(self):
        self.setStyleSheet("""
            QMainWindow, QWidget {
                background-color: #F9FAFB; font-family: Segoe UI; color: #111827;
            }
            #barra { background-color: #FFFFFF; border-bottom: 1px solid #E5E7EB; }
            #titulo_barra   { font-size: 15px; font-weight: 700; color: #1E40AF; }
            #lbl_user_barra { font-size: 12px; color: #6B7280; }
            #btn_cerrar_barra {
                background-color: #F3F4F6; color: #374151;
                font-size: 12px; font-weight: 600;
                border: 1px solid #D1D5DB; border-radius: 5px; padding: 0 14px;
            }
            #btn_cerrar_barra:hover { background-color: #E5E7EB; }

            #body_wrapper    { background-color: #F9FAFB; }
            #panel_productos { background-color: #F9FAFB; }
            #panel_carrito   { background-color: #FFFFFF; border-left: 1px solid #E5E7EB; }

            #titulo_seccion  { font-size: 17px; font-weight: 700; color: #111827; }
            #lbl_conteo      { font-size: 12px; color: #6B7280; }
            #titulo_carrito  { font-size: 15px; font-weight: 700; color: #111827; }
            #lbl_items_count { font-size: 12px; color: #6B7280; }

            #scroll_productos, #scroll_carrito { border: none; background-color: transparent; }
            #lista_widget, #carrito_items_widget { background-color: transparent; }

            #prod_nombre  { font-size: 14px; font-weight: 700; color: #111827; }
            #prod_detalle { font-size: 12px; color: #6B7280; }
            #prod_motivo  { font-size: 11px; color: #9CA3AF; }
            #precio_orig  { font-size: 11px; color: #9CA3AF; text-decoration: line-through; }
            #precio_desc  { font-size: 14px; font-weight: 700; color: #15803D; }
            #btn_agregar  {
                background-color: #2563EB; color: white; border: none;
                border-radius: 6px; font-size: 12px; font-weight: 600; padding: 0 12px;
            }
            #btn_agregar:hover    { background-color: #1D4ED8; }
            #btn_agregar:disabled { background-color: #D1D5DB; color: #9CA3AF; }
            #aviso_vacio {
                font-size: 13px; color: #6B7280; padding: 36px;
                background-color: #FFFFFF; border: 1px solid #E5E7EB; border-radius: 8px;
            }

            #carrito_fila    { background-color: #F9FAFB; border: 1px solid #E5E7EB; border-radius: 6px; }
            #carrito_nombre  { font-size: 12px; font-weight: 600; color: #111827; }
            #carrito_subtotal { font-size: 12px; font-weight: 700; color: #111827; }
            #carrito_vacio   { font-size: 12px; color: #9CA3AF; padding: 20px; }
            #lbl_qty         { font-size: 13px; font-weight: 600; color: #111827; }
            #btn_qty {
                background-color: #FFFFFF; color: #374151;
                border: 1px solid #D1D5DB; border-radius: 4px;
                font-size: 14px; font-weight: 700;
            }
            #btn_qty:hover { background-color: #F3F4F6; }
            #btn_del_item {
                background-color: transparent; color: #9CA3AF;
                border: none; font-size: 16px; font-weight: 700; border-radius: 4px;
            }
            #btn_del_item:hover { color: #DC2626; background-color: #FEF2F2; }

            #resumen_widget { background-color: transparent; }
            #sep_carrito    { color: #E5E7EB; background-color: #E5E7EB; max-height: 1px; }
            #resumen_label  { font-size: 12px; color: #6B7280; }
            #resumen_valor  { font-size: 12px; color: #374151; font-weight: 600; }
            #ahorro_valor   { font-size: 12px; color: #16A34A; font-weight: 700; }
            #total_label    { font-size: 14px; font-weight: 700; color: #111827; }
            #total_valor    { font-size: 16px; font-weight: 700; color: #1E40AF; }

            #btn_comprar {
                background-color: #2563EB; color: white; border: none;
                border-radius: 7px; font-size: 14px; font-weight: 700;
            }
            #btn_comprar:hover    { background-color: #1D4ED8; }
            #btn_comprar:disabled { background-color: #D1D5DB; color: #9CA3AF; }
            #btn_vaciar {
                background-color: #FFFFFF; color: #6B7280;
                border: 1px solid #D1D5DB; border-radius: 6px;
                font-size: 12px; font-weight: 600;
            }
            #btn_vaciar:hover { background-color: #F9FAFB; color: #374151; }

            QScrollBar:vertical { background-color: #F3F4F6; width: 5px; border-radius: 3px; }
            QScrollBar::handle:vertical { background-color: #D1D5DB; border-radius: 3px; }
        """)
        self.btn_comprar.setEnabled(False)
        self.btn_vaciar.setEnabled(False)
        self._refrescar_carrito()


# ══════════════════════════════════════════════════════════════════════════════
#  DIÁLOGO DE PAGO (checkout)
# ══════════════════════════════════════════════════════════════════════════════
class CheckoutDialog(QDialog):

    def __init__(self, carrito: dict, usuario, parent=None):
        super().__init__(parent)
        self.carrito = carrito
        self.usuario = usuario
        self.monto_recibido = 0.0
        self.cambio         = 0.0

        # Calcular total
        self._total = sum(
            e["item"]["precio_sugerido"] * e["cantidad"]
            for e in carrito.values()
        )

        self.setWindowTitle("Proceso de pago")
        self.setMinimumWidth(640)
        self.setMinimumHeight(520)
        self._construir_ui()
        self._aplicar_estilos()

    def _construir_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(28, 24, 28, 24)
        lay.setSpacing(14)

        # Título
        titulo = QLabel("Resumen y pago")
        titulo.setObjectName("checkout_titulo")
        lay.addWidget(titulo)

        # Info cliente
        info_box = QFrame()
        info_box.setObjectName("info_box")
        ib_lay = QHBoxLayout(info_box)
        ib_lay.setContentsMargins(14, 10, 14, 10)
        lbl_cli = QLabel(
            f"<b>Cliente:</b>  {self.usuario.nombre}"
            f"&nbsp;&nbsp;<span style='color:#D1D5DB'>|</span>&nbsp;&nbsp;"
            f"<b>Usuario:</b>  {self.usuario.usuario}"
        )
        lbl_cli.setObjectName("checkout_info")
        lbl_cli.setTextFormat(Qt.TextFormat.RichText)
        ib_lay.addWidget(lbl_cli)
        lay.addWidget(info_box)

        # Tabla de productos
        self.tabla = QTableWidget()
        self.tabla.setColumnCount(6)
        self.tabla.setHorizontalHeaderLabels([
            "Producto", "Cant.", "Precio unit.", "Descuento", "P. c/desc.", "Subtotal"
        ])
        self.tabla.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.tabla.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tabla.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.tabla.verticalHeader().setVisible(False)
        self.tabla.setShowGrid(False)
        self.tabla.setAlternatingRowColors(True)
        self.tabla.setMaximumHeight(180)

        subtotal_orig = subtotal_desc = 0.0
        self.tabla.setRowCount(len(self.carrito))
        for fila, (pid, entrada) in enumerate(self.carrito.items()):
            item     = entrada["item"]
            cantidad = entrada["cantidad"]
            sub_desc = item["precio_sugerido"] * cantidad
            subtotal_orig += item["precio_original"] * cantidad
            subtotal_desc += sub_desc

            vals = [
                item["nombre"], str(cantidad),
                f"${item['precio_original']:,.0f}",
                f"-{item['descuento_sugerido']:.0f}%",
                f"${item['precio_sugerido']:,.2f}",
                f"${sub_desc:,.2f}",
            ]
            for col, txt in enumerate(vals):
                cell = QTableWidgetItem(txt)
                cell.setTextAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignCenter)
                if col == 3: cell.setForeground(QColor("#DC2626"))
                if col == 5: cell.setForeground(QColor("#15803D"))
                self.tabla.setItem(fila, col, cell)
        lay.addWidget(self.tabla)

        ahorro = subtotal_orig - subtotal_desc

        # Resumen totales
        totales = QFrame()
        totales.setObjectName("totales_frame")
        t_lay = QVBoxLayout(totales)
        t_lay.setContentsMargins(0, 0, 0, 0)
        t_lay.setSpacing(4)

        def fila_t(txt, val, obj):
            row = QHBoxLayout()
            l = QLabel(txt); l.setObjectName(obj + "_lbl")
            v = QLabel(val); v.setObjectName(obj + "_val")
            row.addStretch(); row.addWidget(l); row.addSpacing(16); row.addWidget(v)
            return row

        t_lay.addLayout(fila_t("Subtotal sin descuento:", f"${subtotal_orig:,.2f}", "t_sub"))
        t_lay.addLayout(fila_t("Ahorro:", f"- ${ahorro:,.2f}", "t_ahorro"))
        sep = QFrame(); sep.setFrameShape(QFrame.Shape.HLine); sep.setObjectName("sep_totales")
        t_lay.addWidget(sep)
        t_lay.addLayout(fila_t("TOTAL A PAGAR:", f"${self._total:,.2f}", "t_total"))
        lay.addWidget(totales)

        # ── Sección de pago ───────────────────────────────────────────────────
        pago_frame = QFrame()
        pago_frame.setObjectName("pago_frame")
        p_lay = QVBoxLayout(pago_frame)
        p_lay.setContentsMargins(16, 14, 16, 14)
        p_lay.setSpacing(10)

        lbl_pago_titulo = QLabel("Pago en efectivo")
        lbl_pago_titulo.setObjectName("pago_titulo")
        p_lay.addWidget(lbl_pago_titulo)

        # Fila: monto recibido
        fila_monto = QHBoxLayout()
        lbl_monto = QLabel("Monto recibido:")
        lbl_monto.setObjectName("pago_label")
        lbl_monto.setFixedWidth(140)

        self.input_monto = QLineEdit()
        self.input_monto.setObjectName("input_monto")
        self.input_monto.setPlaceholderText("0.00")
        self.input_monto.setFixedHeight(38)
        validator = QDoubleValidator(0.0, 99_999_999.0, 2)
        validator.setNotation(QDoubleValidator.Notation.StandardNotation)
        self.input_monto.setValidator(validator)
        self.input_monto.textChanged.connect(self._calcular_cambio)

        fila_monto.addWidget(lbl_monto)
        fila_monto.addWidget(self.input_monto)
        p_lay.addLayout(fila_monto)

        # Fila: cambio
        fila_cambio = QHBoxLayout()
        lbl_cambio_txt = QLabel("Cambio:")
        lbl_cambio_txt.setObjectName("pago_label")
        lbl_cambio_txt.setFixedWidth(140)
        self.lbl_cambio = QLabel("—")
        self.lbl_cambio.setObjectName("lbl_cambio")
        fila_cambio.addWidget(lbl_cambio_txt)
        fila_cambio.addWidget(self.lbl_cambio)
        fila_cambio.addStretch()
        p_lay.addLayout(fila_cambio)

        # Aviso pago insuficiente
        self.lbl_pago_aviso = QLabel("")
        self.lbl_pago_aviso.setObjectName("lbl_pago_aviso")
        p_lay.addWidget(self.lbl_pago_aviso)

        lay.addWidget(pago_frame)

        # Botones
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        btn_cancelar = QPushButton("Cancelar")
        btn_cancelar.setObjectName("btn_cancelar_checkout")
        btn_cancelar.setFixedHeight(40)
        btn_cancelar.clicked.connect(self.reject)

        self.btn_confirmar = QPushButton("Confirmar pago")
        self.btn_confirmar.setObjectName("btn_confirmar_checkout")
        self.btn_confirmar.setFixedHeight(40)
        self.btn_confirmar.setEnabled(False)
        self.btn_confirmar.clicked.connect(self._confirmar)

        btn_row.addWidget(btn_cancelar)
        btn_row.addStretch()
        btn_row.addWidget(self.btn_confirmar)
        lay.addLayout(btn_row)

    def _calcular_cambio(self):
        txt = self.input_monto.text().replace(",", ".")
        try:
            monto  = float(txt) if txt else 0.0
            cambio = monto - self._total
            m = CONFIG.get("moneda", "$")
            if cambio >= 0:
                self.lbl_cambio.setText(f"<b style='color:#16A34A;'>{m}{cambio:,.2f}</b>")
                self.lbl_cambio.setTextFormat(Qt.TextFormat.RichText)
                self.lbl_pago_aviso.setText("")
                self.btn_confirmar.setEnabled(True)
                self.monto_recibido = monto
                self.cambio         = cambio
            else:
                self.lbl_cambio.setText("—")
                falta = abs(cambio)
                self.lbl_pago_aviso.setText(
                    f"Faltan {m}{falta:,.2f} para completar el pago"
                )
                self.btn_confirmar.setEnabled(False)
        except ValueError:
            self.btn_confirmar.setEnabled(False)

    def _confirmar(self):
        self.accept()

    def _aplicar_estilos(self):
        self.setStyleSheet("""
            QDialog { background-color: #FFFFFF; font-family: Segoe UI; }
            #checkout_titulo { font-size: 18px; font-weight: 700; color: #111827; }
            #info_box { background-color: #F9FAFB; border: 1px solid #E5E7EB; border-radius: 6px; }
            #checkout_info { font-size: 13px; color: #374151; }
            QTableWidget {
                background-color: #FFFFFF; border: 1px solid #E5E7EB;
                border-radius: 6px; font-size: 13px;
            }
            QTableWidget::item         { padding: 7px 6px; }
            QTableWidget::item:alternate { background-color: #F9FAFB; }
            QHeaderView::section {
                background-color: #F3F4F6; color: #6B7280;
                font-size: 12px; font-weight: 600;
                padding: 8px; border: none; border-bottom: 1px solid #E5E7EB;
            }
            #totales_frame { background-color: transparent; }
            #sep_totales   { color: #E5E7EB; background-color: #E5E7EB; max-height: 1px; }
            #t_sub_lbl, #t_sub_val       { font-size: 12px; color: #6B7280; }
            #t_ahorro_lbl, #t_ahorro_val { font-size: 12px; color: #16A34A; font-weight: 700; }
            #t_total_lbl { font-size: 14px; font-weight: 700; color: #111827; }
            #t_total_val { font-size: 16px; font-weight: 700; color: #1E40AF; }

            /* Sección pago */
            #pago_frame {
                background-color: #F0FDF4;
                border: 1px solid #BBF7D0;
                border-radius: 8px;
            }
            #pago_titulo  { font-size: 13px; font-weight: 700; color: #166534; }
            #pago_label   { font-size: 13px; color: #374151; }
            #input_monto {
                background-color: #FFFFFF; color: #111827;
                border: 1px solid #A7F3D0; border-radius: 6px;
                padding: 6px 12px; font-size: 14px; font-weight: 600;
            }
            #input_monto:focus { border: 1.5px solid #16A34A; }
            #lbl_cambio   { font-size: 14px; font-weight: 700; color: #111827; }
            #lbl_pago_aviso { font-size: 12px; color: #DC2626; }

            /* Botones */
            #btn_cancelar_checkout {
                background-color: #FFFFFF; color: #6B7280;
                border: 1px solid #D1D5DB; border-radius: 6px;
                font-size: 13px; font-weight: 600; padding: 0 20px;
            }
            #btn_cancelar_checkout:hover { background-color: #F9FAFB; }
            #btn_confirmar_checkout {
                background-color: #16A34A; color: white; border: none;
                border-radius: 6px; font-size: 13px; font-weight: 700; padding: 0 24px;
            }
            #btn_confirmar_checkout:hover    { background-color: #15803D; }
            #btn_confirmar_checkout:disabled { background-color: #D1D5DB; color: #9CA3AF; }
        """)


# ══════════════════════════════════════════════════════════════════════════════
#  VISTA PREVIA DE FACTURA (dentro de la app)
# ══════════════════════════════════════════════════════════════════════════════
class InvoicePreviewDialog(QDialog):

    def __init__(self, datos: dict, parent=None):
        super().__init__(parent)
        self.datos = datos
        self.setWindowTitle(f"Factura — {datos['numero']}")
        self.setMinimumSize(720, 740)
        self._construir_ui()
        self._aplicar_estilos()

    def _construir_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # ── Barra de herramientas ─────────────────────────────────────────
        toolbar = QFrame()
        toolbar.setObjectName("invoice_toolbar")
        toolbar.setFixedHeight(52)
        tb_lay = QHBoxLayout(toolbar)
        tb_lay.setContentsMargins(20, 0, 20, 0)

        lbl_titulo = QLabel(f"Factura  {self.datos['numero']}")
        lbl_titulo.setObjectName("invoice_toolbar_titulo")

        self.btn_imprimir = QPushButton("Guardar / Imprimir PDF")
        self.btn_imprimir.setObjectName("btn_imprimir")
        self.btn_imprimir.setFixedHeight(34)
        self.btn_imprimir.clicked.connect(self._guardar_pdf)

        btn_cerrar = QPushButton("Cerrar")
        btn_cerrar.setObjectName("btn_cerrar_invoice")
        btn_cerrar.setFixedHeight(34)
        btn_cerrar.clicked.connect(self.accept)

        tb_lay.addWidget(lbl_titulo)
        tb_lay.addStretch()
        tb_lay.addWidget(self.btn_imprimir)
        tb_lay.addSpacing(8)
        tb_lay.addWidget(btn_cerrar)
        lay.addWidget(toolbar)

        # ── Visor HTML ───────────────────────────────────────────────────
        self.browser = QTextBrowser()
        self.browser.setObjectName("invoice_browser")
        self.browser.setOpenLinks(False)
        self.browser.setHtml(self._html())
        lay.addWidget(self.browser)

    def _html(self) -> str:
        d       = self.datos
        m       = CONFIG.get("moneda", "$")
        negocio = CONFIG.get("nombre_negocio", "Inventario App")
        nit     = CONFIG.get("nit", "N/A")
        dir_neg = CONFIG.get("direccion", "")

        # Filas de productos
        filas = ""
        for i, (pid, entrada) in enumerate(d["carrito"].items()):
            item     = entrada["item"]
            cantidad = entrada["cantidad"]
            sub      = item["precio_sugerido"] * cantidad
            bg = "#FFFFFF" if i % 2 == 0 else "#F9FAFB"
            filas += f"""
            <tr style="background-color:{bg};">
              <td style="padding:9px 10px;">{item['nombre']}</td>
              <td style="padding:9px 10px; text-align:center;">{cantidad}</td>
              <td style="padding:9px 10px; text-align:right;">{m}{item['precio_original']:,.0f}</td>
              <td style="padding:9px 10px; text-align:center; color:#DC2626; font-weight:bold;">
                -{item['descuento_sugerido']:.0f}%
              </td>
              <td style="padding:9px 10px; text-align:right;">{m}{item['precio_sugerido']:,.2f}</td>
              <td style="padding:9px 10px; text-align:right; font-weight:bold;">{m}{sub:,.2f}</td>
            </tr>"""

        return f"""
<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family:'Segoe UI',Arial,sans-serif; background:#F9FAFB; margin:0; padding:24px;">
<div style="max-width:660px; margin:0 auto; background:#FFFFFF; padding:36px;
            border-radius:8px; border:1px solid #E5E7EB;">

  <!-- Encabezado -->
  <div style="border-bottom:3px solid #1E40AF; padding-bottom:14px; margin-bottom:20px;">
    <div style="font-size:22px; font-weight:bold; color:#1E40AF;">{negocio}</div>
    <div style="font-size:13px; color:#6B7280; margin-top:4px;">Factura de Venta</div>
  </div>

  <!-- Info factura + cliente -->
  <table width="100%" style="margin-bottom:20px; font-size:12px;">
    <tr>
      <td width="50%" style="vertical-align:top;">
        <table>
          <tr>
            <td style="color:#6B7280; padding:3px 12px 3px 0;">No. Factura</td>
            <td style="font-weight:bold;">{d['numero']}</td>
          </tr>
          <tr>
            <td style="color:#6B7280; padding:3px 12px 3px 0;">Fecha</td>
            <td>{d['fecha'].strftime('%d/%m/%Y')}</td>
          </tr>
          <tr>
            <td style="color:#6B7280; padding:3px 12px 3px 0;">Hora</td>
            <td>{d['fecha'].strftime('%H:%M:%S')}</td>
          </tr>
        </table>
      </td>
      <td width="50%" style="vertical-align:top;">
        <table>
          <tr>
            <td style="color:#6B7280; padding:3px 12px 3px 0;">Cliente</td>
            <td style="font-weight:bold;">{d['usuario'].nombre}</td>
          </tr>
          <tr>
            <td style="color:#6B7280; padding:3px 12px 3px 0;">Usuario</td>
            <td>{d['usuario'].usuario}</td>
          </tr>
        </table>
      </td>
    </tr>
  </table>

  <hr style="border:none; border-top:1px solid #E5E7EB; margin-bottom:16px;">

  <!-- Tabla de productos -->
  <table width="100%" cellspacing="0"
         style="border-collapse:collapse; margin-bottom:20px; font-size:13px;">
    <thead>
      <tr style="background-color:#1E40AF; color:white;">
        <th style="padding:10px; text-align:left;">Producto</th>
        <th style="padding:10px; text-align:center;">Cant.</th>
        <th style="padding:10px; text-align:right;">Precio unit.</th>
        <th style="padding:10px; text-align:center;">Descuento</th>
        <th style="padding:10px; text-align:right;">P. c/desc.</th>
        <th style="padding:10px; text-align:right;">Subtotal</th>
      </tr>
    </thead>
    <tbody>
      {filas}
    </tbody>
  </table>

  <!-- Totales -->
  <table width="100%" style="margin-bottom:10px; font-size:13px;">
    <tr>
      <td style="text-align:right; color:#6B7280; padding:3px 0;">
        Subtotal sin descuento:
      </td>
      <td width="160" style="text-align:right; color:#6B7280; padding:3px 10px;">
        {m}{d['subtotal_orig']:,.2f}
      </td>
    </tr>
    <tr>
      <td style="text-align:right; color:#16A34A; padding:3px 0;">Ahorro total:</td>
      <td style="text-align:right; color:#16A34A; font-weight:bold; padding:3px 10px;">
        - {m}{d['ahorro']:,.2f}
      </td>
    </tr>
  </table>
  <hr style="border:none; border-top:2px solid #1E40AF; margin-bottom:8px;">
  <table width="100%" style="margin-bottom:20px;">
    <tr>
      <td style="text-align:right; font-size:15px; font-weight:bold; color:#111827;">
        TOTAL A PAGAR:
      </td>
      <td width="160" style="text-align:right; font-size:18px; font-weight:bold;
                              color:#1E40AF; padding:0 10px;">
        {m}{d['total_desc']:,.2f}
      </td>
    </tr>
  </table>

  <!-- Pago recibido -->
  <div style="background-color:#F0FDF4; border-radius:6px; padding:14px;
              margin-bottom:24px; border:1px solid #BBF7D0;">
    <div style="font-size:11px; font-weight:bold; color:#166534;
                letter-spacing:1px; margin-bottom:10px;">PAGO RECIBIDO</div>
    <table width="100%" style="font-size:13px;">
      <tr>
        <td style="color:#374151; padding:3px 0;">Efectivo recibido:</td>
        <td style="text-align:right; font-weight:bold;">
          {m}{d['monto_recibido']:,.2f}
        </td>
      </tr>
      <tr>
        <td style="color:#374151; padding:3px 0;">Cambio:</td>
        <td style="text-align:right; font-weight:bold; color:#16A34A;">
          {m}{d['cambio']:,.2f}
        </td>
      </tr>
    </table>
  </div>

  <hr style="border:none; border-top:1px solid #E5E7EB; margin-bottom:14px;">

  <!-- Pie -->
  <div style="text-align:center; color:#9CA3AF; font-size:11px;">
    <div style="font-size:14px; color:#374151; font-weight:bold; margin-bottom:6px;">
      Gracias por su compra
    </div>
    <div>{negocio} &nbsp;·&nbsp; {dir_neg} &nbsp;·&nbsp; NIT: {nit}</div>
    <div style="margin-top:4px;">
      Documento generado el {d['fecha'].strftime('%d/%m/%Y a las %H:%M:%S')}
    </div>
  </div>

</div>
</body>
</html>"""

    def _guardar_pdf(self):
        from ui.invoice import generar_factura
        try:
            ruta = generar_factura(self.datos)
            QMessageBox.information(
                self, "PDF guardado",
                f"Factura guardada correctamente en:\n{ruta}"
            )
            # Abrir el PDF con el visor del sistema
            self._abrir_archivo(ruta)
        except Exception as e:
            QMessageBox.critical(self, "Error al generar PDF", str(e))

    @staticmethod
    def _abrir_archivo(ruta):
        try:
            if platform.system() == "Windows":
                os.startfile(str(ruta))
            elif platform.system() == "Darwin":
                subprocess.run(["open", str(ruta)])
            else:
                subprocess.run(["xdg-open", str(ruta)])
        except Exception:
            pass   # Si no se puede abrir no es crítico

    def _aplicar_estilos(self):
        self.setStyleSheet("""
            QDialog { background-color: #F9FAFB; font-family: Segoe UI; }
            #invoice_toolbar {
                background-color: #FFFFFF;
                border-bottom: 1px solid #E5E7EB;
            }
            #invoice_toolbar_titulo {
                font-size: 14px; font-weight: 700; color: #1E40AF;
            }
            #btn_imprimir {
                background-color: #2563EB; color: white; border: none;
                border-radius: 6px; font-size: 12px; font-weight: 700;
                padding: 0 16px;
            }
            #btn_imprimir:hover { background-color: #1D4ED8; }
            #btn_cerrar_invoice {
                background-color: #FFFFFF; color: #374151;
                border: 1px solid #D1D5DB; border-radius: 6px;
                font-size: 12px; font-weight: 600; padding: 0 16px;
            }
            #btn_cerrar_invoice:hover { background-color: #F9FAFB; }
            #invoice_browser {
                background-color: #F9FAFB;
                border: none;
            }
            QScrollBar:vertical { background-color: #F3F4F6; width: 6px; border-radius: 3px; }
            QScrollBar::handle:vertical { background-color: #D1D5DB; border-radius: 3px; }
        """)
