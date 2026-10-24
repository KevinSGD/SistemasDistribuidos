"""Modulo unico de tema: colores, tipografia, hoja de estilo global y formato.

Todos los colores de la UI salen de ``COLORES`` (paletas de contexto.md,
seccion "Interfaz Gráfica, Maquetación"). Ninguna vista ni widget debe
declarar hex sueltos.

Notas de accesibilidad (contraste WCAG contra blanco/fondo):
- ``texto_tenue`` (#9CA3AF) es el gris del documento para motivos y precios
  tachados; NO cumple AA (2.5:1), usar solo para texto decorativo/secundario
  no esencial. Para texto informativo usar ``texto_suave`` (#6B7280, 4.8:1).
- ``aviso`` (#D97706) se usa en acentos; para TEXTO de aviso sobre fondo claro
  usar ``aviso_texto`` (#B45309, 5.0:1).
"""
from __future__ import annotations

from string import Template

from PyQt6.QtGui import QColor, QFont
from PyQt6.QtWidgets import QApplication

# --------------------------------------------------------------------------
# Paleta
# --------------------------------------------------------------------------
COLORES: dict[str, str] = {
    # Base
    "fondo": "#F9FAFB",
    "superficie": "#FFFFFF",
    "superficie_alt": "#F3F4F6",
    "borde": "#E5E7EB",
    "borde_input": "#D1D5DB",
    "texto": "#111827",
    "texto_secundario": "#374151",
    "texto_suave": "#6B7280",
    "texto_tenue": "#9CA3AF",
    "texto_sobre_primario": "#FFFFFF",
    # Marca / acciones
    "primario": "#2563EB",
    "primario_hover": "#1D4ED8",
    "primario_press": "#1E40AF",
    "primario_texto": "#1E40AF",       # titulos de marca, total a pagar
    "primario_fondo": "#EFF6FF",       # badge de descuento, info
    "descuento_texto": "#1D4ED8",
    "hover_peligro_fondo": "#FEF2F2",  # hover del boton x del carrito
    # Estados
    "exito": "#16A34A",
    "exito_texto": "#15803D",          # precio con descuento (AA sobre blanco)
    "exito_oscuro": "#166534",
    "exito_fondo": "#F0FDF4",
    "exito_borde": "#BBF7D0",
    "peligro": "#DC2626",
    "peligro_fondo": "#FEE2E2",
    "aviso": "#D97706",
    "aviso_texto": "#B45309",
    "aviso_fondo": "#FEF3C7",
    "info": "#2563EB",
    "info_fondo": "#EFF6FF",
    # Niveles de riesgo
    "nivel_critico": "#DC2626",
    "nivel_critico_fondo": "#FEE2E2",
    "nivel_alto": "#D97706",
    "nivel_alto_fondo": "#FEF3C7",
    "nivel_medio": "#CA8A04",
    "nivel_medio_fondo": "#FEF9C3",
    "nivel_normal": "#374151",
    "nivel_normal_fondo": "#F3F4F6",
    # Deshabilitado (RNF-04)
    "deshabilitado_fondo": "#E5E7EB",
    "deshabilitado_texto": "#9CA3AF",
}

#: nivel -> (color de texto, color de fondo)
COLOR_NIVEL: dict[str, tuple[str, str]] = {
    "critico": (COLORES["nivel_critico"], COLORES["nivel_critico_fondo"]),
    "alto": (COLORES["nivel_alto"], COLORES["nivel_alto_fondo"]),
    "medio": (COLORES["nivel_medio"], COLORES["nivel_medio_fondo"]),
    "normal": (COLORES["nivel_normal"], COLORES["nivel_normal_fondo"]),
}

# --------------------------------------------------------------------------
# Tipografia
# --------------------------------------------------------------------------
_FALLBACKS = ["Inter", "Helvetica Neue", "Ubuntu", "DejaVu Sans", "Arial", "sans-serif"]

FUENTE: dict = {
    "familia": "Segoe UI",
    "fallbacks": _FALLBACKS,
    "familias": ["Segoe UI", *_FALLBACKS[:-1]],
    # Cadena lista para QSS/CSS
    "css": '"Segoe UI", "Inter", "Helvetica Neue", "Ubuntu", "DejaVu Sans", Arial, sans-serif',
    "tam_base": 13,  # px
}

PESO_NORMAL = QFont.Weight.Normal      # 400
PESO_SEMIBOLD = QFont.Weight.DemiBold  # 600
PESO_BOLD = QFont.Weight.Bold          # 700


def fuente(px: int = 13, peso: QFont.Weight = PESO_NORMAL, tachado: bool = False) -> QFont:
    """QFont con la familia del tema, tamano en px y peso dados."""
    f = QFont()
    f.setFamilies(FUENTE["familias"])
    f.setPixelSize(px)
    f.setWeight(peso)
    f.setStrikeOut(tachado)
    return f


def color(nombre_o_hex: str) -> str:
    """Resuelve un nombre de COLORES; si no existe, asume que ya es hex."""
    return COLORES.get(nombre_o_hex, nombre_o_hex)


def qcolor(nombre_o_hex: str, alfa: int = 255) -> QColor:
    c = QColor(color(nombre_o_hex))
    c.setAlpha(alfa)
    return c


# --------------------------------------------------------------------------
# Formato
# --------------------------------------------------------------------------
def fmt_moneda(valor: float | int, moneda: str = "$") -> str:
    """Formatea dinero estilo es-CO: miles con '.', decimales con ','.

    Regla: sin decimales si ``moneda`` es "COP" o si el valor es entero
    (p. ej. 1234.0); en otro caso 2 decimales. Simbolo de una sola letra
    pegado ("$1.234"); codigos largos con espacio ("COP 1.234").
    Negativos: "-$1.234".
    """
    try:
        v = float(valor)
    except (TypeError, ValueError):
        v = 0.0
    sin_decimales = moneda.upper() == "COP" or round(v, 2) == int(round(v, 2))
    texto = f"{abs(v):,.0f}" if sin_decimales else f"{abs(v):,.2f}"
    # en-US -> es-CO: intercambiar separadores
    texto = texto.replace(",", "\0").replace(".", ",").replace("\0", ".")
    prefijo = moneda if len(moneda) <= 1 else moneda + " "
    signo = "-" if v < 0 and any(c not in "0.," for c in texto) else ""
    return f"{signo}{prefijo}{texto}"


# --------------------------------------------------------------------------
# Hoja de estilo global
# --------------------------------------------------------------------------
_QSS = Template(
    """
* { font-family: $fuente; }
QWidget { color: $texto; }
QMainWindow, QDialog { background: $fondo; }
QToolTip {
    background: $texto; color: $superficie; border: 1px solid $texto_secundario;
    padding: 4px 8px; font-size: 12px;
}

/* ---- Botones ---- */
QPushButton {
    background: $superficie_alt; color: $texto_secundario;
    border: 1px solid $borde_input; border-radius: 6px;
    padding: 6px 14px; min-height: 22px; font-size: 13px; font-weight: 600;
}
QPushButton:hover { background: $borde; }
QPushButton:pressed { background: $borde_input; }
QPushButton:focus { border: 2px solid $primario; padding: 5px 13px; }
QPushButton[variant="primary"] {
    background: $primario; color: $texto_sobre_primario; border: 1px solid $primario;
}
QPushButton[variant="primary"]:hover { background: $primario_hover; border-color: $primario_hover; }
QPushButton[variant="primary"]:pressed { background: $primario_press; border-color: $primario_press; }
QPushButton[variant="primary"]:focus { border: 2px solid $primario_press; padding: 5px 13px; }
QPushButton[variant="danger"] {
    background: $superficie; color: $peligro; border: 1px solid $peligro;
}
QPushButton[variant="danger"]:hover { background: $peligro_fondo; }
QPushButton[variant="danger"]:pressed { background: $peligro_fondo; border-color: $peligro; }
QPushButton[variant="danger"]:focus { border: 2px solid $peligro; padding: 5px 13px; }
QPushButton:disabled, QPushButton[variant]:disabled {
    background: $deshabilitado_fondo; color: $deshabilitado_texto;
    border: 1px solid $borde; font-weight: 400;
}

/* ---- Entradas ---- */
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QPlainTextEdit, QTextEdit {
    background: $fondo; color: $texto; border: 1px solid $borde_input;
    border-radius: 6px; padding: 6px 10px; min-height: 22px;
    selection-background-color: $primario; selection-color: $texto_sobre_primario;
}
QLineEdit:hover, QSpinBox:hover, QDoubleSpinBox:hover, QComboBox:hover { border-color: $texto_suave; }
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus,
QPlainTextEdit:focus, QTextEdit:focus { border: 2px solid $primario; padding: 5px 9px; background: $superficie; }
QLineEdit[error="true"] { border: 2px solid $peligro; padding: 5px 9px; }
QLineEdit:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled, QComboBox:disabled {
    background: $deshabilitado_fondo; color: $deshabilitado_texto; border-color: $borde;
}
QComboBox::drop-down { border: none; width: 24px; }
QComboBox QAbstractItemView {
    background: $superficie; color: $texto; border: 1px solid $borde_input;
    selection-background-color: $primario_fondo; selection-color: $primario_texto; outline: 0;
}
QSpinBox::up-button, QSpinBox::down-button,
QDoubleSpinBox::up-button, QDoubleSpinBox::down-button { width: 18px; border: none; background: transparent; }

/* ---- Tablas ---- */
QTableWidget, QTableView {
    background: $superficie; alternate-background-color: $fondo; color: $texto_secundario;
    border: 1px solid $borde; border-radius: 6px; gridline-color: $borde;
    selection-background-color: $primario_fondo; selection-color: $primario_texto;
}
QTableWidget::item { padding: 6px 10px; }
QTableWidget::item:focus { outline: none; border: 1px solid $primario; }
QHeaderView::section {
    background: $superficie; color: $primario_texto; font-weight: 600; font-size: 13px;
    border: none; border-bottom: 2px solid $borde; padding: 8px 10px;
}
QTableWidget:focus { border: 2px solid $primario; }

/* ---- Scroll ---- */
QScrollBar:vertical { background: transparent; width: 12px; margin: 0; }
QScrollBar:horizontal { background: transparent; height: 12px; margin: 0; }
QScrollBar::handle:vertical { background: $borde_input; border-radius: 4px; min-height: 32px; margin: 2px; }
QScrollBar::handle:horizontal { background: $borde_input; border-radius: 4px; min-width: 32px; margin: 2px; }
QScrollBar::handle:hover { background: $texto_tenue; }
QScrollBar::handle:pressed { background: $texto_suave; }
QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }

/* ---- Dialogos de mensaje ---- */
QMessageBox { background: $superficie; }
QMessageBox QLabel { color: $texto; font-size: 13px; }
QMessageBox QPushButton { min-width: 84px; }
"""
)


def hoja_estilo() -> str:
    """Hoja de estilo global resuelta con la paleta."""
    return _QSS.substitute(fuente=FUENTE["css"], **COLORES)


def aplicar_tema(app: QApplication) -> None:
    """Aplica fuente base y hoja de estilo global a la aplicacion."""
    app.setFont(fuente(FUENTE["tam_base"]))
    app.setStyleSheet(hoja_estilo())
