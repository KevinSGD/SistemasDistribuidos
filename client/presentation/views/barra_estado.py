"""Barra superior comun a las ventanas autenticadas: usuario, conexion, reloj de sesion, salir.

Uso en cualquier ventana (QMainWindow o widget con layout vertical):

    from client.presentation.views.barra_estado import instalar_barra_estado
    self.barra = instalar_barra_estado(self, app_ctx)

`app_ctx` es la `Aplicacion`. Un cambio de vista del usuario debe llamar a
`app_ctx.marcar_actividad_vista()`; el refresco automatico no."""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QBoxLayout, QFrame, QHBoxLayout, QLabel, QMainWindow, QPushButton, QWidget

from ..styles.theme import COLORES, fuente
from ..widgets import IndicadorConexion, RelojSesion


class BarraEstado(QFrame):
    def __init__(self, app_ctx, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("barra_estado")
        self.setStyleSheet(
            f"#barra_estado {{ background: {COLORES['superficie']};"
            f" border-bottom: 1px solid {COLORES['borde']}; }}")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(16, 4, 16, 4)
        lay.setSpacing(8)

        s = app_ctx.sesion
        self.lbl_usuario = QLabel(f"{s.nombre} · {s.rol}" if s else "", self)
        self.lbl_usuario.setFont(fuente(12))
        self.lbl_usuario.setStyleSheet(f"color: {COLORES['texto_secundario']}; font-weight: 600;")
        self.conexion = IndicadorConexion(self)
        self.reloj = RelojSesion(self)
        self.btn_salir = QPushButton("Cerrar sesión", self)
        self.btn_salir.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_salir.clicked.connect(app_ctx.cerrar_sesion)

        lay.addWidget(self.lbl_usuario)
        lay.addStretch(1)
        lay.addWidget(self.conexion)
        lay.addWidget(self.reloj)
        lay.addWidget(self.btn_salir)

        if app_ctx.idle is not None:
            self.reloj.set_segundos(app_ctx.idle.restantes())
            app_ctx.idle.segundos_restantes.connect(self.reloj.set_segundos)
        app_ctx.estado_servidor.connect(self.conexion.set_estado)
        app_ctx.conexion_cambiada.connect(self._al_ws)
        self._ctx = app_ctx

    def _al_ws(self, conectado: bool) -> None:
        # el socket caido adelanta el aviso; el health lo confirma o corrige en <= 10 s
        if not conectado:
            self.conexion.set_estado(False, "Sin eventos en vivo (reconectando)")


def instalar_barra_estado(ventana: QWidget, app_ctx) -> BarraEstado:
    """Crea la barra y la coloca arriba: `setMenuWidget` en QMainWindow, o primer item del
    layout vertical de la ventana."""
    barra = BarraEstado(app_ctx, ventana)
    if isinstance(ventana, QMainWindow):
        ventana.setMenuWidget(barra)
    else:
        lay = ventana.layout()
        if not isinstance(lay, QBoxLayout):
            raise TypeError("La ventana necesita un QBoxLayout para instalar la barra de estado")
        lay.insertWidget(0, barra)
    return barra
