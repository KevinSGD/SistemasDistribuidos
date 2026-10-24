"""Ventana minima usada mientras no existan MainWindow/BuyerWindow definitivas."""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QLabel, QMainWindow, QVBoxLayout, QWidget

from ..styles.theme import COLORES, fuente
from .barra_estado import instalar_barra_estado


class VentanaProvisional(QMainWindow):
    def __init__(self, app_ctx):
        super().__init__()
        s = app_ctx.sesion
        self.setWindowTitle("Inventario App")
        self.resize(720, 420)
        self.barra = instalar_barra_estado(self, app_ctx)
        centro = QWidget(self)
        lay = QVBoxLayout(centro)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_saludo = QLabel(f"Hola, {s.nombre}", centro)
        self.lbl_saludo.setFont(fuente(20, QFont.Weight.Bold))
        self.lbl_saludo.setStyleSheet(f"color: {COLORES['texto']};")
        self.lbl_rol = QLabel(f"Rol: {s.rol} (vista provisional)", centro)
        self.lbl_rol.setStyleSheet(f"color: {COLORES['texto_suave']};")
        lay.addWidget(self.lbl_saludo, alignment=Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self.lbl_rol, alignment=Qt.AlignmentFlag.AlignCenter)
        self.setCentralWidget(centro)
