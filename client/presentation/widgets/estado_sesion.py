"""Indicadores de barra superior: conexion con el servidor y tiempo de sesion."""
from __future__ import annotations

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QPainter
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QWidget

from ..styles.theme import COLORES, fuente, qcolor


class _Punto(QWidget):
    def __init__(self, diametro: int = 10, parent=None):
        super().__init__(parent)
        self._d = diametro
        self._color = COLORES["texto_tenue"]
        self.setFixedSize(diametro + 2, diametro + 2)

    def set_color(self, hex_: str) -> None:
        self._color = hex_
        self.update()

    def paintEvent(self, _):  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(qcolor(self._color))
        p.drawEllipse(1, 1, self._d, self._d)


class IndicadorConexion(QWidget):
    """Punto de color + texto. Verde: en linea; rojo: desconectado."""

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 4, 8, 4)
        lay.setSpacing(6)
        self._punto = _Punto(10, self)
        self._texto = QLabel(self)
        self._texto.setFont(fuente(12))
        lay.addWidget(self._punto)
        lay.addWidget(self._texto)
        self.conectado = False
        self.set_estado(False, "Servidor desconectado")

    def set_estado(self, conectado: bool, texto: str) -> None:
        self.conectado = bool(conectado)
        self._punto.set_color(COLORES["exito"] if conectado else COLORES["peligro"])
        # Texto en tono oscuro del mismo matiz: contraste AA sobre blanco.
        self._texto.setStyleSheet(
            f"color: {COLORES['exito_texto'] if conectado else COLORES['peligro']};"
            " font-weight: 600;"
        )
        self._texto.setText(texto)
        self.setAccessibleName(f"Conexion: {texto}")
        self.setToolTip(texto)


class RelojSesion(QWidget):
    """Muestra 'Sesión: mm:ss'. n<=30 aviso, n<=10 peligro."""

    UMBRAL_AVISO = 30
    UMBRAL_PELIGRO = 10

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 4, 8, 4)
        self._label = QLabel(self)
        self._label.setFont(fuente(12))
        lay.addWidget(self._label)
        self.segundos = 0
        self.nivel = "normal"
        self.set_segundos(0)

    @classmethod
    def nivel_para(cls, n: int) -> str:
        if n <= cls.UMBRAL_PELIGRO:
            return "peligro"
        if n <= cls.UMBRAL_AVISO:
            return "aviso"
        return "normal"

    @staticmethod
    def formatear(n: int) -> str:
        n = max(0, int(n))
        return f"Sesión: {n // 60:02d}:{n % 60:02d}"

    @property
    def texto(self) -> str:
        return self._label.text()

    @property
    def color_actual(self) -> str:
        return {
            "normal": COLORES["texto_suave"],
            "aviso": COLORES["aviso_texto"],
            "peligro": COLORES["peligro"],
        }[self.nivel]

    def set_segundos(self, n: int) -> None:
        self.segundos = max(0, int(n))
        self.nivel = self.nivel_para(self.segundos)
        peso = 400 if self.nivel == "normal" else 700
        self._label.setStyleSheet(f"color: {self.color_actual}; font-weight: {peso};")
        self._label.setText(self.formatear(self.segundos))
        self.setAccessibleName(self.formatear(self.segundos))

    def sizeHint(self) -> QSize:  # noqa: N802
        return super().sizeHint()
