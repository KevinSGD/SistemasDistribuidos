from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QFrame, QSpinBox,
    QComboBox, QMessageBox, QScrollArea,
    QFormLayout, QGroupBox
)
from PyQt6.QtCore import Qt
from config import CONFIG


class ConfigView(QWidget):

    def __init__(self):
        super().__init__()
        self._construir_ui()

    def _construir_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(20)

        titulo = QLabel("Configuración")
        titulo.setStyleSheet("font-size: 20px; font-weight: 700; color: #111827;")
        layout.addWidget(titulo)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("border: none; background-color: transparent;")
        contenedor = QWidget()
        contenedor.setStyleSheet("background-color: transparent;")
        cont_layout = QVBoxLayout(contenedor)
        cont_layout.setSpacing(20)

        cont_layout.addWidget(self._seccion_negocio())
        cont_layout.addWidget(self._seccion_descuentos())
        cont_layout.addWidget(self._seccion_umbrales())
        cont_layout.addWidget(self._seccion_automatizacion())
        cont_layout.addStretch()

        scroll.setWidget(contenedor)
        layout.addWidget(scroll)

        btn_guardar = QPushButton("Guardar configuración")
        btn_guardar.setFixedHeight(42)
        btn_guardar.setStyleSheet("""
            QPushButton {
                background-color: #2563EB;
                color: white;
                font-size: 13px;
                font-weight: 600;
                border-radius: 6px;
                border: none;
            }
            QPushButton:hover { background-color: #1D4ED8; }
        """)
        btn_guardar.clicked.connect(self._guardar)
        layout.addWidget(btn_guardar)

    def _seccion_negocio(self) -> QGroupBox:
        grupo = self._grupo("Datos del Negocio")
        form  = QFormLayout()
        form.setSpacing(12)

        self.nombre_negocio = self._input(CONFIG.get("nombre_negocio", "Mi Tienda"))
        self.nit            = self._input(CONFIG.get("nit", ""))
        self.direccion      = self._input(CONFIG.get("direccion", ""))
        self.moneda         = self._combo(["$", "€", "£", "USD", "COP", "MXN"],
                                          CONFIG.get("moneda", "$"))

        form.addRow("Nombre del negocio:", self.nombre_negocio)
        form.addRow("NIT / RUT:",          self.nit)
        form.addRow("Dirección:",          self.direccion)
        form.addRow("Moneda:",             self.moneda)
        grupo.setLayout(form)
        return grupo

    def _seccion_descuentos(self) -> QGroupBox:
        grupo = self._grupo("Reglas de Descuento")
        form  = QFormLayout()
        form.setSpacing(12)

        self.desc_critico    = self._spin(CONFIG["descuento_critico"])
        self.desc_alto       = self._spin(CONFIG["descuento_alto"])
        self.desc_medio      = self._spin(CONFIG["descuento_medio"])
        self.desc_sobrestock = self._spin(CONFIG["descuento_sobrestock"])

        form.addRow("Descuento crítico (%):",    self.desc_critico)
        form.addRow("Descuento alto (%):",       self.desc_alto)
        form.addRow("Descuento medio (%):",      self.desc_medio)
        form.addRow("Descuento sobrestock (%):", self.desc_sobrestock)
        grupo.setLayout(form)
        return grupo

    def _seccion_umbrales(self) -> QGroupBox:
        grupo = self._grupo("Umbrales de Alerta")
        form  = QFormLayout()
        form.setSpacing(12)

        self.dias_alerta  = self._spin(CONFIG["dias_alerta_vencimiento"])
        self.dias_critico = self._spin(CONFIG["dias_critico_vencimiento"])
        self.stock_bajo   = self._spin(CONFIG["umbral_stock_bajo"])
        self.pct_sobre    = self._spin(90)

        form.addRow("Días alerta vencimiento:", self.dias_alerta)
        form.addRow("Días nivel crítico:",      self.dias_critico)
        form.addRow("Stock bajo (unidades):",   self.stock_bajo)
        form.addRow("% sobrestock:",            self.pct_sobre)
        grupo.setLayout(form)
        return grupo

    def _seccion_automatizacion(self) -> QGroupBox:
        grupo = self._grupo("Automatización")
        form  = QFormLayout()
        form.setSpacing(12)

        self.intervalo = self._spin(60)
        self.intervalo.setRange(1, 1440)
        self.notificaciones = self._combo(["Activado", "Desactivado"], "Activado")
        self.sonido         = self._combo(["Activado", "Desactivado"], "Activado")

        form.addRow("Escaneo cada (minutos):", self.intervalo)
        form.addRow("Notificaciones:",         self.notificaciones)
        form.addRow("Sonido de alerta:",       self.sonido)
        grupo.setLayout(form)
        return grupo

    def _guardar(self):
        CONFIG["nombre_negocio"]           = self.nombre_negocio.text()
        CONFIG["nit"]                      = self.nit.text()
        CONFIG["direccion"]                = self.direccion.text()
        CONFIG["moneda"]                   = self.moneda.currentText()
        CONFIG["descuento_critico"]        = self.desc_critico.value()
        CONFIG["descuento_alto"]           = self.desc_alto.value()
        CONFIG["descuento_medio"]          = self.desc_medio.value()
        CONFIG["descuento_sobrestock"]     = self.desc_sobrestock.value()
        CONFIG["dias_alerta_vencimiento"]  = self.dias_alerta.value()
        CONFIG["dias_critico_vencimiento"] = self.dias_critico.value()
        CONFIG["umbral_stock_bajo"]        = self.stock_bajo.value()

        QMessageBox.information(self, "Guardado", "Configuración guardada correctamente.")

    def _grupo(self, titulo: str) -> QGroupBox:
        grupo = QGroupBox(titulo)
        grupo.setStyleSheet("""
            QGroupBox {
                color: #374151;
                font-size: 12px;
                font-weight: 700;
                border: 1px solid #E5E7EB;
                border-radius: 8px;
                margin-top: 10px;
                padding: 14px;
                background-color: #FFFFFF;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 12px;
                padding: 0 5px;
                background-color: #FFFFFF;
            }
            QLabel { color: #374151; font-size: 12px; }
        """)
        return grupo

    def _input(self, valor: str = "") -> QLineEdit:
        w = QLineEdit(valor)
        w.setStyleSheet("""
            QLineEdit {
                background-color: #F9FAFB;
                color: #111827;
                border: 1px solid #D1D5DB;
                border-radius: 6px;
                padding: 7px 10px;
                font-size: 13px;
            }
            QLineEdit:focus { border: 1px solid #2563EB; }
        """)
        return w

    def _spin(self, valor: int) -> QSpinBox:
        w = QSpinBox()
        w.setRange(0, 100)
        w.setValue(valor)
        w.setStyleSheet("""
            QSpinBox {
                background-color: #F9FAFB;
                color: #111827;
                border: 1px solid #D1D5DB;
                border-radius: 6px;
                padding: 6px;
                font-size: 13px;
            }
            QSpinBox:focus { border: 1px solid #2563EB; }
        """)
        return w

    def _combo(self, opciones: list, seleccionado: str = "") -> QComboBox:
        w = QComboBox()
        w.addItems(opciones)
        index = w.findText(seleccionado)
        if index >= 0:
            w.setCurrentIndex(index)
        w.setStyleSheet("""
            QComboBox {
                background-color: #F9FAFB;
                color: #111827;
                border: 1px solid #D1D5DB;
                border-radius: 6px;
                padding: 6px 10px;
                font-size: 13px;
            }
            QComboBox::drop-down { border: none; }
            QComboBox QAbstractItemView {
                background-color: #FFFFFF;
                color: #111827;
                selection-background-color: #DBEAFE;
                selection-color: #1D4ED8;
            }
        """)
        return w
