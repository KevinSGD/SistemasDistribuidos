"""Overlay de carga con spinner pintado y esqueleto pulsante."""
from __future__ import annotations

import math

from PyQt6.QtCore import QEvent, QRectF, Qt, QTimer
from PyQt6.QtGui import QPainter, QPen
from PyQt6.QtWidgets import QVBoxLayout, QWidget

from ..styles.theme import COLORES, fuente, qcolor


class Cargando(QWidget):
    """Overlay que cubre al parent (se redimensiona con el). Bloquea la
    interaccion con lo que cubre mientras esta visible. El timer solo corre
    mientras es visible."""

    def __init__(self, parent: QWidget, texto: str = "Cargando…"):
        super().__init__(parent)
        self.texto = texto
        self._angulo = 0
        self._timer = QTimer(self)
        self._timer.setInterval(40)
        self._timer.timeout.connect(self._girar)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAccessibleName(texto)
        parent.installEventFilter(self)
        self.setGeometry(parent.rect())
        self.hide()

    # API
    def iniciar(self, texto: str | None = None) -> None:
        if texto is not None:
            self.texto = texto
            self.setAccessibleName(texto)
        self.setGeometry(self.parentWidget().rect())
        self.show()
        self.raise_()

    def detener(self) -> None:
        self.hide()

    @property
    def activo(self) -> bool:
        return self._timer.isActive()

    # internals
    def eventFilter(self, obj, ev):  # noqa: N802
        if obj is self.parentWidget() and ev.type() == QEvent.Type.Resize:
            self.setGeometry(self.parentWidget().rect())
        return False

    def showEvent(self, ev):  # noqa: N802
        self._timer.start()
        super().showEvent(ev)

    def hideEvent(self, ev):  # noqa: N802
        self._timer.stop()
        super().hideEvent(ev)

    def _girar(self) -> None:
        self._angulo = (self._angulo + 30) % 360
        self.update()

    def paintEvent(self, _):  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), qcolor("superficie", 215))
        cx, cy = self.width() / 2, self.height() / 2 - 12
        radio, n = 18, 12
        for i in range(n):
            ang = math.radians(self._angulo + i * 360 / n)
            alfa = int(255 * (i + 1) / n)
            pen = QPen(qcolor("primario", alfa), 3.5)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.setPen(pen)
            p.drawLine(
                int(cx + math.cos(ang) * (radio - 7)), int(cy + math.sin(ang) * (radio - 7)),
                int(cx + math.cos(ang) * radio), int(cy + math.sin(ang) * radio),
            )
        p.setPen(qcolor("texto_secundario"))
        p.setFont(fuente(13))
        p.drawText(QRectF(0, cy + radio + 12, self.width(), 24),
                   Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop, self.texto)

    def keyPressEvent(self, ev):  # noqa: N802
        ev.accept()  # traga teclas mientras carga


class Esqueleto(QWidget):
    """Barras grises que pulsan: marcador de posicion mientras llegan datos."""

    def __init__(self, filas: int = 5, parent=None):
        super().__init__(parent)
        self.filas = filas
        self._fase = 0.0
        self._timer = QTimer(self)
        self._timer.setInterval(50)
        self._timer.timeout.connect(self._tick)
        self.setMinimumHeight(filas * 40)
        self.setAccessibleName("Cargando contenido")

    def showEvent(self, ev):  # noqa: N802
        self._timer.start()
        super().showEvent(ev)

    def hideEvent(self, ev):  # noqa: N802
        self._timer.stop()
        super().hideEvent(ev)

    def _tick(self) -> None:
        self._fase = (self._fase + 0.08) % (2 * math.pi)
        self.update()

    def paintEvent(self, _):  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        alfa = int(150 + 105 * (0.5 + 0.5 * math.sin(self._fase)))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(qcolor("borde", alfa))
        for i in range(self.filas):
            y = i * 40 + 8
            ancho = self.width() * (0.95 if i % 2 == 0 else 0.7)
            p.drawRoundedRect(QRectF(0, y, ancho, 22), 6, 6)
