from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel,
    QScrollArea, QFrame, QHBoxLayout
)
from PyQt6.QtCore import Qt


class AlertsView(QWidget):

    def __init__(self, engine):
        super().__init__()
        self.engine = engine
        self._construir_ui()

    def _construir_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(16)

        titulo = QLabel("Alertas de Inventario")
        titulo.setStyleSheet("font-size: 20px; font-weight: 700; color: #111827;")
        layout.addWidget(titulo)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("border: none; background-color: transparent;")
        self.contenedor = QWidget()
        self.contenedor.setStyleSheet("background-color: transparent;")
        self.contenedor_layout = QVBoxLayout(self.contenedor)
        self.contenedor_layout.setSpacing(10)
        scroll.setWidget(self.contenedor)
        layout.addWidget(scroll)

    def actualizar(self, resultados: dict):
        while self.contenedor_layout.count():
            item = self.contenedor_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        niveles = {
            "critico": ("Crítico",  "#DC2626", "#FEE2E2"),
            "alto":    ("Alto",     "#D97706", "#FEF3C7"),
            "medio":   ("Medio",    "#CA8A04", "#FEF9C3"),
        }

        hay_alertas = False
        for nivel, (etiqueta, color, fondo) in niveles.items():
            items = resultados.get(nivel, [])
            if not items:
                continue

            hay_alertas = True

            encabezado = QLabel(f"{etiqueta.upper()}  —  {len(items)} producto(s)")
            encabezado.setStyleSheet(f"""
                color: {color};
                font-size: 12px;
                font-weight: 700;
                padding: 4px 0px;
                letter-spacing: 0.5px;
            """)
            self.contenedor_layout.addWidget(encabezado)

            for item in items:
                self.contenedor_layout.addWidget(
                    self._crear_tarjeta(item, color, fondo)
                )

        if not hay_alertas:
            lbl = QLabel("Sin alertas activas. El inventario está en orden.")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setStyleSheet("""
                color: #16A34A;
                font-size: 13px;
                padding: 36px;
                background-color: #F0FDF4;
                border-radius: 8px;
                border: 1px solid #BBF7D0;
            """)
            self.contenedor_layout.addWidget(lbl)

        self.contenedor_layout.addStretch()

    def _crear_tarjeta(self, item: dict, color: str, fondo: str) -> QFrame:
        tarjeta = QFrame()
        tarjeta.setStyleSheet(f"""
            QFrame {{
                background-color: {fondo};
                border-radius: 6px;
                border: 1px solid #E5E7EB;
                border-left: 3px solid {color};
            }}
        """)
        layout = QHBoxLayout(tarjeta)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(16)

        info = QVBoxLayout()
        info.setSpacing(3)
        nombre = QLabel(f"<b style='font-size:13px; color:#111827;'>{item['nombre']}</b>")
        motivo = QLabel(item['motivo'])
        motivo.setStyleSheet("color: #6B7280; font-size: 12px;")
        stock  = QLabel(f"Stock: {item['stock']} unidades")
        stock.setStyleSheet("color: #6B7280; font-size: 12px;")
        info.addWidget(nombre)
        info.addWidget(motivo)
        info.addWidget(stock)

        precios = QVBoxLayout()
        precios.setAlignment(Qt.AlignmentFlag.AlignRight)
        precios.setSpacing(4)

        badge = QLabel(f"-{item['descuento_sugerido']}% OFF")
        badge.setStyleSheet(f"""
            color: white;
            background-color: {color};
            font-weight: 700;
            font-size: 12px;
            padding: 3px 10px;
            border-radius: 4px;
        """)
        badge.setAlignment(Qt.AlignmentFlag.AlignRight)

        precio_orig = QLabel(f"Antes: ${item['precio_original']:,.0f}")
        precio_orig.setStyleSheet("color: #9CA3AF; text-decoration: line-through; font-size: 12px;")
        precio_orig.setAlignment(Qt.AlignmentFlag.AlignRight)

        precio_nuevo = QLabel(f"Ahora: ${item['precio_sugerido']:,.0f}")
        precio_nuevo.setStyleSheet("color: #16A34A; font-weight: 700; font-size: 13px;")
        precio_nuevo.setAlignment(Qt.AlignmentFlag.AlignRight)

        precios.addWidget(badge)
        precios.addWidget(precio_orig)
        precios.addWidget(precio_nuevo)

        layout.addLayout(info)
        layout.addStretch()
        layout.addLayout(precios)
        return tarjeta
