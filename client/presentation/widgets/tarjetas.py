"""Badge de nivel, tarjeta de resumen y estado vacio/error."""
from __future__ import annotations

import unicodedata

from PyQt6.QtCore import QRect, Qt, pyqtSignal
from PyQt6.QtWidgets import QFrame, QLabel, QPushButton, QVBoxLayout, QWidget

from ..styles.theme import COLOR_NIVEL, COLOR_NIVEL_BADGE, COLORES, PESO_BOLD, fuente
from ..styles.theme import color as resolver_color

_ETIQUETAS = {"critico": "Crítico", "alto": "Alto", "medio": "Medio", "normal": "Normal"}


def normalizar_nivel(nivel: str) -> str:
    n = unicodedata.normalize("NFD", str(nivel or "")).encode("ascii", "ignore").decode().lower().strip()
    return n if n in COLOR_NIVEL else "normal"


class BadgeNivel(QLabel):
    """Pildora Crítico/Alto/Medio/Normal con la paleta del documento."""

    def __init__(self, nivel: str = "normal", parent=None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setFont(fuente(11))
        self.nivel = "normal"
        self.set_nivel(nivel)

    def set_nivel(self, nivel: str) -> None:
        self.nivel = normalizar_nivel(nivel)
        texto, fondo = COLOR_NIVEL_BADGE[self.nivel]  # texto AA sobre el fondo del documento
        etiqueta = _ETIQUETAS[self.nivel]
        self.setText(etiqueta)
        self.setAccessibleName(f"Nivel de riesgo {etiqueta}")
        self.setStyleSheet(
            f"QLabel {{ color: {texto}; background: {fondo}; font-size: 11px; font-weight: 700;"
            f" border-radius: 9px; padding: 2px 10px; }}"
        )


class TarjetaResumen(QFrame):
    """Tarjeta del dashboard: etiqueta gris + numero grande de color."""

    def __init__(self, titulo: str, valor, color: str = "texto_secundario", parent=None):
        """``color``: nombre de COLORES (p. ej. "nivel_critico") o hex."""
        super().__init__(parent)
        self._color = resolver_color(color)
        self.setObjectName("tarjetaResumen")
        self.setStyleSheet(
            f"QFrame#tarjetaResumen {{ background: {COLORES['superficie']};"
            f" border: 1px solid {COLORES['borde']}; border-radius: 10px; }}"
        )
        self.setMinimumSize(150, 92)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 12, 16, 12)
        lay.setSpacing(2)
        self._titulo = QLabel(titulo, self)
        self._titulo.setStyleSheet(
            f"color: {COLORES['texto_suave']}; font-size: 12px; font-weight: 600; border: none;"
        )
        self._valor = QLabel(self)
        self._valor.setStyleSheet(
            f"color: {self._color}; font-size: 30px; font-weight: 700; border: none;"
        )
        lay.addWidget(self._titulo)
        lay.addWidget(self._valor)
        lay.addStretch(1)
        self.set_valor(valor)

    @property
    def titulo(self) -> str:
        return self._titulo.text()

    @property
    def valor(self) -> str:
        return self._valor.text()

    @property
    def color_valor(self) -> str:
        return self._color

    def set_valor(self, valor) -> None:
        self._valor.setText(str(valor))
        self.setAccessibleName(f"{self._titulo.text()}: {valor}")


class EstadoVacio(QWidget):
    """Estado vacio o de error con icono de texto, titulo, mensaje y,
    opcionalmente, un boton de accion (p. ej. 'Reintentar')."""

    accion = pyqtSignal()
    ANCHO_TEXTO = 360

    def __init__(self, icono_texto: str, titulo: str, mensaje: str,
                 texto_boton: str | None = None, parent=None, error: bool = False):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.setSpacing(8)
        acento = COLORES["peligro"] if error else COLORES["texto_suave"]
        self._icono = QLabel(icono_texto, self)
        self._icono.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._icono.setFixedSize(64, 64)
        self._icono.setStyleSheet(
            f"background: {COLORES['peligro_fondo'] if error else COLORES['superficie_alt']};"
            f" color: {acento}; border-radius: 32px; font-size: 28px; font-weight: 700;"
        )
        self._titulo = QLabel(titulo, self)
        self._titulo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._titulo.setWordWrap(True)
        self._titulo.setFont(fuente(16, PESO_BOLD))
        self._titulo.setStyleSheet(f"color: {COLORES['texto']}; font-size: 16px; font-weight: 700;")
        self._mensaje = QLabel(mensaje, self)
        self._mensaje.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._mensaje.setWordWrap(True)
        self._mensaje.setFont(fuente(13))
        self._mensaje.setStyleSheet(f"color: {COLORES['texto_suave']}; font-size: 13px;")
        lay.addWidget(self._icono, 0, Qt.AlignmentFlag.AlignHCenter)
        lay.addWidget(self._titulo, 0, Qt.AlignmentFlag.AlignHCenter)
        lay.addWidget(self._mensaje, 0, Qt.AlignmentFlag.AlignHCenter)
        self._boton: QPushButton | None = None
        if texto_boton:
            self._boton = QPushButton(texto_boton, self)
            self._boton.setProperty("variant", "primary")
            self._boton.setMinimumHeight(36)
            self._boton.clicked.connect(self.accion)
            lay.addSpacing(6)
            lay.addWidget(self._boton, 0, Qt.AlignmentFlag.AlignHCenter)
        self._reservar_alturas()

    # ---- API publica de textos
    def set_textos(self, titulo: str | None = None, mensaje: str | None = None) -> None:
        """Cambia titulo y/o mensaje (None = sin cambios) y recalcula la altura reservada."""
        if titulo is not None:
            self._titulo.setText(titulo)
        if mensaje is not None:
            self._mensaje.setText(mensaje)
        self._reservar_alturas()

    @property
    def titulo(self) -> str:
        return self._titulo.text()

    @property
    def mensaje(self) -> str:
        return self._mensaje.text()

    def _reservar_alturas(self) -> None:
        """Fija ancho (<= ANCHO_TEXTO) y alto de cada label midiendo el texto con ajuste de
        linea; sin esto el layout estrecha el label y recorta los mensajes multilinea."""
        for lbl in (self._titulo, self._mensaje):
            fm = lbl.fontMetrics()
            caja = fm.boundingRect(QRect(0, 0, self.ANCHO_TEXTO, 10000),
                                   Qt.TextFlag.TextWordWrap.value | Qt.AlignmentFlag.AlignCenter.value,
                                   lbl.text())
            lbl.setFixedSize(self.ANCHO_TEXTO, max(caja.height(), fm.height()) + 6)
        self.updateGeometry()

    @classmethod
    def error_conexion(cls, parent=None) -> "EstadoVacio":
        return cls("!", "Sin conexión con el servidor",
                   "No pudimos comunicarnos con el servidor. Revisa tu red e intenta de nuevo.",
                   "Reintentar", parent, error=True)

    @classmethod
    def sin_resultados(cls, parent=None) -> "EstadoVacio":
        return cls("∅", "Sin resultados", "No hay datos para mostrar.", None, parent)

    @property
    def boton(self) -> QPushButton | None:
        return self._boton
