"""Factura dentro de la app (datos de POST /compras) con descarga/impresion de PDF bajo demanda."""
from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog, QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

from client.application.mensajes import texto_error
from client.infrastructure.factura_pdf import METODOS, a_dict, abrir_archivo, generar_factura_pdf

from ..styles.theme import COLORES
from ..widgets import DocumentoFactura, Toast


class FacturaDialog(QDialog):
    pdf_generado = pyqtSignal(object)          # Path

    def __init__(self, app_ctx, factura, iva_pct: float = 0.0, parent: QWidget | None = None):
        super().__init__(parent)
        self._ctx = app_ctx
        self.factura = factura
        self.iva_pct = float(iva_pct or 0)
        self.datos = a_dict(factura)
        self.ruta_pdf: Path | None = None
        self.generando = False
        self.setWindowTitle(f"Factura — {self.datos.get('numero', '')}")
        self.setMinimumSize(700, 760)
        self.resize(760, 820)

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(0, 0, 0, 0)
        raiz.setSpacing(0)

        barra = QFrame()
        barra.setObjectName("barraFactura")
        barra.setStyleSheet(f"QFrame#barraFactura {{ background: {COLORES['superficie']};"
                            f" border-bottom: 1px solid {COLORES['borde']}; }}")
        bl = QHBoxLayout(barra)
        bl.setContentsMargins(20, 10, 20, 10)
        col = QVBoxLayout()
        col.setSpacing(0)
        titulo = QLabel(f"Factura  {self.datos.get('numero', '')}")
        titulo.setStyleSheet(f"font-size: 14px; font-weight: 700; color: {COLORES['primario_texto']};")
        metodo = METODOS.get(self.datos.get("metodo_pago", ""), "")
        if self.datos.get("metodo_pago") == "tarjeta_simulada":
            metodo += " · autorizada"
        self.lbl_estado = QLabel(f"Compra registrada · {metodo}")
        self.lbl_estado.setStyleSheet(f"font-size: 12px; color: {COLORES['exito_texto']}; font-weight: 600;")
        self.lbl_estado.setWordWrap(True)
        col.addWidget(titulo)
        col.addWidget(self.lbl_estado)
        bl.addLayout(col, 1)
        self.btn_pdf = QPushButton("Guardar / Imprimir PDF")
        self.btn_pdf.setProperty("variant", "primary")
        self.btn_pdf.setMinimumHeight(34)
        self.btn_pdf.clicked.connect(self.guardar_pdf)
        self.btn_cerrar = QPushButton("Cerrar")
        self.btn_cerrar.setMinimumHeight(34)
        self.btn_cerrar.clicked.connect(self.accept)
        bl.addWidget(self.btn_pdf)
        bl.addSpacing(6)
        bl.addWidget(self.btn_cerrar)
        raiz.addWidget(barra)

        datos_widget = dict(self.datos)
        if self.iva_pct:
            datos_widget["iva_pct"] = self.iva_pct
        self.documento = DocumentoFactura(datos_widget)
        zona = QScrollArea()
        zona.setWidgetResizable(True)
        zona.setFrameShape(QFrame.Shape.NoFrame)
        zona.setStyleSheet(f"QScrollArea {{ background: {COLORES['fondo']}; }}")
        cont = QWidget()
        cont.setObjectName("contenedorFactura")
        cont.setStyleSheet(f"QWidget#contenedorFactura {{ background: {COLORES['fondo']}; }}")
        cl = QVBoxLayout(cont)
        cl.setContentsMargins(24, 24, 24, 24)
        cl.addWidget(self.documento, 0, Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
        cl.addStretch(1)
        zona.setWidget(cont)
        raiz.addWidget(zona, 1)

    def guardar_pdf(self) -> None:
        """Genera el PDF (fuera del hilo de la GUI) y lo abre con el visor del sistema."""
        if self.generando:
            return
        self.generando = True
        self.btn_pdf.setEnabled(False)
        self.btn_pdf.setText("Generando PDF…")
        datos, iva = self.datos, self.iva_pct or None
        self._ctx.ejecutar(lambda: generar_factura_pdf(datos, iva_pct=iva),
                           self._pdf_ok, self._pdf_error, self)

    def _fin_pdf(self) -> None:
        self.generando = False
        self.btn_pdf.setEnabled(True)
        self.btn_pdf.setText("Guardar / Imprimir PDF")

    def _pdf_ok(self, ruta: Path) -> None:
        self._fin_pdf()
        self.ruta_pdf = ruta
        abierto = abrir_archivo(ruta)
        self.lbl_estado.setText(f"PDF guardado en: {ruta}"
                                + ("" if abierto else " (ábrelo manualmente: no se pudo iniciar el visor)"))
        Toast.mostrar(self, "PDF guardado" + (" y abierto." if abierto else "."), "exito")
        self.pdf_generado.emit(ruta)

    def _pdf_error(self, exc: BaseException) -> None:
        self._fin_pdf()
        Toast.mostrar(self, f"No se pudo generar el PDF: {texto_error(exc) if hasattr(exc, 'codigo') else exc}",
                      "error", 6000)
