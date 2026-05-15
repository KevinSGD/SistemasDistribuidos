from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QFrame, QScrollArea
)
from PyQt6.QtCore import Qt


class DashboardView(QWidget):

    def __init__(self, engine):
        super().__init__()
        self.engine = engine
        self._construir_ui()

    def _construir_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(20)

        titulo = QLabel("Dashboard")
        titulo.setStyleSheet("font-size: 20px; font-weight: 700; color: #111827;")
        layout.addWidget(titulo)

        self.tarjetas_layout = QHBoxLayout()
        self.tarjetas_layout.setSpacing(12)
        layout.addLayout(self.tarjetas_layout)

        subtitulo = QLabel("Productos que requieren atención")
        subtitulo.setStyleSheet("font-size: 13px; font-weight: 600; color: #6B7280; padding-top: 4px;")
        layout.addWidget(subtitulo)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("border: none; background-color: transparent;")
        self.lista_widget = QWidget()
        self.lista_widget.setStyleSheet("background-color: transparent;")
        self.lista_layout = QVBoxLayout(self.lista_widget)
        self.lista_layout.setSpacing(8)
        scroll.setWidget(self.lista_widget)
        layout.addWidget(scroll)

    def actualizar(self, resultados: dict):
        while self.tarjetas_layout.count():
            item = self.tarjetas_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        criticos = len(resultados.get("critico", []))
        altos    = len(resultados.get("alto", []))
        medios   = len(resultados.get("medio", []))
        normales = len(resultados.get("normal", []))
        total    = criticos + altos + medios + normales

        tarjetas = [
            ("Total",         str(total),    "#374151"),
            ("Críticos",      str(criticos), "#DC2626"),
            ("Riesgo Alto",   str(altos),    "#D97706"),
            ("Riesgo Medio",  str(medios),   "#CA8A04"),
        ]
        for titulo, valor, color_val in tarjetas:
            self.tarjetas_layout.addWidget(self._crear_tarjeta(titulo, valor, color_val))

        while self.lista_layout.count():
            item = self.lista_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        niveles = {
            "critico": ("#FEE2E2", "#DC2626", "Crítico"),
            "alto":    ("#FEF3C7", "#D97706", "Alto"),
            "medio":   ("#FEF9C3", "#CA8A04", "Medio"),
        }

        hay_riesgo = False
        for nivel, (pastel, acento, etiqueta) in niveles.items():
            for item in resultados.get(nivel, []):
                self.lista_layout.addWidget(self._crear_fila(item, pastel, acento, etiqueta))
                hay_riesgo = True

        if not hay_riesgo:
            lbl = QLabel("Todo el inventario está en estado normal")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setStyleSheet("""
                color: #166534;
                font-size: 13px;
                padding: 28px;
                background-color: #F0FDF4;
                border-radius: 8px;
                border: 1px solid #BBF7D0;
            """)
            self.lista_layout.addWidget(lbl)

        self.lista_layout.addStretch()

    def _crear_tarjeta(self, titulo: str, valor: str, color_val: str) -> QFrame:
        tarjeta = QFrame()
        tarjeta.setFixedHeight(90)
        tarjeta.setStyleSheet("""
            QFrame {
                background-color: #FFFFFF;
                border-radius: 8px;
                border: 1px solid #E5E7EB;
            }
            QFrame:hover { background-color: #F9FAFB; }
        """)
        layout = QVBoxLayout(tarjeta)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(4)

        lbl_titulo = QLabel(titulo)
        lbl_titulo.setStyleSheet("color: #6B7280; font-size: 12px; font-weight: 600;")

        lbl_valor = QLabel(valor)
        lbl_valor.setStyleSheet(f"color: {color_val}; font-size: 30px; font-weight: 700;")

        layout.addWidget(lbl_titulo)
        layout.addWidget(lbl_valor)
        return tarjeta

    def _crear_fila(self, item: dict, pastel: str, acento: str, etiqueta: str) -> QFrame:
        fila = QFrame()
        fila.setStyleSheet("""
            QFrame {
                background-color: #FFFFFF;
                border-radius: 6px;
                border: 1px solid #E5E7EB;
            }
        """)
        layout = QHBoxLayout(fila)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(12)

        badge_nivel = QLabel(etiqueta)
        badge_nivel.setFixedWidth(52)
        badge_nivel.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge_nivel.setStyleSheet(f"""
            color: {acento};
            background-color: {pastel};
            font-size: 11px;
            font-weight: 700;
            padding: 3px 6px;
            border-radius: 4px;
        """)

        info = QVBoxLayout()
        info.setSpacing(2)
        nombre = QLabel(f"<b style='color:#111827; font-size:13px;'>{item['nombre']}</b>")
        motivo = QLabel(f"<span style='color:#9CA3AF; font-size:11px;'>{item['motivo']}</span>")
        info.addWidget(nombre)
        info.addWidget(motivo)

        badge_desc = QLabel(f"-{item['descuento_sugerido']}%")
        badge_desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge_desc.setStyleSheet("""
            color: #1D4ED8;
            background-color: #EFF6FF;
            font-size: 12px;
            font-weight: 700;
            padding: 4px 10px;
            border-radius: 4px;
        """)

        precio = QLabel(
            f"<span style='color:#9CA3AF; font-size:11px; "
            f"text-decoration:line-through;'>${item['precio_original']:,.0f}</span>"
            f"  <b style='color:#15803D; font-size:13px;'>${item['precio_sugerido']:,.0f}</b>"
        )
        precio.setTextFormat(Qt.TextFormat.RichText)
        precio.setAlignment(Qt.AlignmentFlag.AlignRight)

        layout.addWidget(badge_nivel)
        layout.addLayout(info)
        layout.addStretch()
        layout.addWidget(badge_desc)
        layout.addWidget(precio)
        return fila
