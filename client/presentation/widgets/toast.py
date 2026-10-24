"""Notificacion no modal, apilable, esquina inferior derecha del parent."""
from __future__ import annotations

import weakref

from PyQt6.QtCore import QEasingCurve, QEvent, QObject, QPropertyAnimation, QRect, Qt, QTimer
from PyQt6.QtWidgets import QGraphicsOpacityEffect, QLabel, QWidget

from ..styles.theme import COLORES, fuente

# tipo -> (acento, fondo, icono)
_TIPOS = {
    "info": (COLORES["info"], COLORES["info_fondo"], "i"),
    "exito": (COLORES["exito"], COLORES["exito_fondo"], "✓"),
    "error": (COLORES["peligro"], COLORES["peligro_fondo"], "!"),
    "aviso": (COLORES["aviso"], COLORES["aviso_fondo"], "!"),
}
_MARGEN = 16
_SEPARACION = 8
_ANCHO_MAX = 360


class _Vigilante(QObject):
    """Reposiciona los toasts cuando el parent cambia de tamano."""

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        parent.installEventFilter(self)

    def eventFilter(self, obj, ev):  # noqa: N802
        if ev.type() in (QEvent.Type.Resize, QEvent.Type.Show):
            Toast._reordenar(obj)
        return False


class Toast(QLabel):
    """No es una ventana: es un hijo del parent, no roba foco ni bloquea."""

    _pilas: "weakref.WeakKeyDictionary[QWidget, list[Toast]]" = weakref.WeakKeyDictionary()
    _vigilantes: "weakref.WeakKeyDictionary[QWidget, _Vigilante]" = weakref.WeakKeyDictionary()

    @classmethod
    def mostrar(cls, parent: QWidget, texto: str, tipo: str = "info",
                duracion_ms: int = 3500) -> "Toast":
        tipo = tipo if tipo in _TIPOS else "info"
        if parent not in cls._vigilantes:
            cls._vigilantes[parent] = _Vigilante(parent)
        t = cls(parent, texto, tipo, duracion_ms)
        cls._pilas.setdefault(parent, []).append(t)
        t.show()
        t.raise_()
        cls._reordenar(parent)
        return t

    @classmethod
    def activos(cls, parent: QWidget) -> list["Toast"]:
        return list(cls._pilas.get(parent, []))

    @classmethod
    def _reordenar(cls, parent: QWidget) -> None:
        """El mas reciente abajo; los anteriores se apilan hacia arriba."""
        y = parent.height() - _MARGEN
        for t in reversed(cls._pilas.get(parent, [])):
            y -= t.height()
            t.move(parent.width() - _MARGEN - t.width(), y)
            y -= _SEPARACION

    def __init__(self, parent: QWidget, texto: str, tipo: str, duracion_ms: int):
        super().__init__(parent)
        self._parent_ref = parent
        self.tipo = tipo
        acento, fondo, icono = _TIPOS[tipo]
        self.setText(f"{icono}   {texto}")
        self.setWordWrap(True)
        self.setFont(fuente(13))
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAccessibleName(f"Notificacion {tipo}")
        self.setStyleSheet(
            f"QLabel {{ background: {fondo}; color: {COLORES['texto']};"
            f" border: 1px solid {COLORES['borde']}; border-left: 5px solid {acento};"
            f" border-radius: 6px; padding: 10px 14px; }}"
        )
        self.setFixedWidth(_ANCHO_MAX)
        self.ensurePolished()
        self.setFixedHeight(self._altura_real())
        self._efecto = QGraphicsOpacityEffect(self)
        self._efecto.setOpacity(1.0)
        self.setGraphicsEffect(self._efecto)
        self._anim = QPropertyAnimation(self._efecto, b"opacity", self)
        self._anim.setDuration(400)
        self._anim.setStartValue(1.0)
        self._anim.setEndValue(0.0)
        self._anim.setEasingCurve(QEasingCurve.Type.InOutQuad)
        self._anim.finished.connect(self.cerrar)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._anim.start)
        self._timer.start(max(0, duracion_ms))

    def _altura_real(self) -> int:
        """Altura medida con la fuente ya resuelta: texto con ajuste de linea
        al ancho disponible + padding (10+10) + bordes (1+1) + holgura."""
        disponible = _ANCHO_MAX - (14 + 14) - (5 + 1)
        caja = self.fontMetrics().boundingRect(
            QRect(0, 0, disponible, 100000),
            int(Qt.TextFlag.TextWordWrap) | int(Qt.AlignmentFlag.AlignLeft),
            self.text(),
        )
        return caja.height() + 20 + 2 + 4

    def mousePressEvent(self, ev):  # noqa: N802
        self.cerrar()  # clic para descartar

    def cerrar(self) -> None:
        self._timer.stop()
        self._anim.stop()
        parent = self._parent_ref
        pila = Toast._pilas.get(parent)
        if pila and self in pila:
            pila.remove(self)
        self.hide()
        self.deleteLater()
        if parent is not None:
            Toast._reordenar(parent)
