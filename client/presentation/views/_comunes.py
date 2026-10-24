"""Piezas compartidas por las vistas del administrador (no hay logica de negocio aqui).

- `VistaBase`: consultas en segundo plano con descarte de respuestas obsoletas, overlay de carga y Toast.
- `FilaRiesgo`: tarjeta de un producto en riesgo (dashboard y alertas).
- `DialogoFormulario`: dialogo con errores junto a cada campo y llamada a la API fuera del hilo GUI.
- `confirmar`, `mensaje_api`, `abrir_ruta`: utilidades. Los tests sustituyen `confirmar`/`abrir_ruta`.
"""
from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any, Callable

from PyQt6.QtCore import QPointF, QRect, Qt, QUrl, pyqtSignal
from PyQt6.QtGui import QColor, QDesktopServices, QFont, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import (
    QDialog, QFrame, QHBoxLayout, QLabel, QMessageBox, QPushButton, QVBoxLayout, QWidget,
)

from client.application.mensajes import texto_error
from client.infrastructure.api_client import ApiError
from shared.schemas import ItemRiesgo

from ..styles.theme import COLORES, fmt_moneda, fuente
from ..widgets import BadgeNivel, Cargando, EstadoVacio, Toast

def _icono_check() -> str:
    """PNG de la marca de verificacion (el QSS necesita un archivo); se genera una sola vez."""
    ruta = Path(tempfile.gettempdir()) / "inventarioapp_check.png"
    if not ruta.exists():
        pm = QPixmap(36, 36)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(QColor("#FFFFFF"), 4.5)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        p.drawPolyline([QPointF(9, 19), QPointF(15.5, 25.5), QPointF(27, 11)])
        p.end()
        pm.save(str(ruta))
    return ruta.as_posix()


def estilo_formulario() -> str:
    """Hoja de estilo para entradas con error, QDateEdit y QCheckBox (el tema global no los cubre)."""
    C = COLORES
    return f"""
QDateEdit {{ background: {C['fondo']}; color: {C['texto']};
    border: 1px solid {C['borde_input']}; border-radius: 6px; padding: 6px 10px; min-height: 22px; }}
QDateEdit:focus {{ border: 2px solid {C['primario']}; padding: 5px 9px; background: {C['superficie']}; }}
QDateEdit:disabled {{ background: {C['deshabilitado_fondo']}; color: {C['deshabilitado_texto']}; }}
QLineEdit[error="true"], QComboBox[error="true"], QDateEdit[error="true"],
QSpinBox[error="true"], QDoubleSpinBox[error="true"] {{
    border: 2px solid {C['peligro']}; padding: 5px 9px; }}
QCheckBox {{ spacing: 8px; color: {C['texto_secundario']}; }}
QCheckBox::indicator {{ width: 18px; height: 18px; border: 1px solid {C['borde_input']};
    border-radius: 4px; background: {C['superficie']}; }}
QCheckBox::indicator:hover {{ border-color: {C['primario']}; }}
QCheckBox::indicator:checked {{ background: {C['primario']}; border-color: {C['primario']};
    image: url({_icono_check()}); }}
QLabel#errorCampo {{ color: {C['peligro']}; font-size: 12px; }}
QLabel#bannerError {{ color: {C['peligro']}; background: {C['peligro_fondo']};
    border-radius: 6px; padding: 8px 12px; font-size: 12px; }}
QLabel#etiquetaCampo {{ color: {C['texto_secundario']}; font-size: 12px; font-weight: 600; }}
"""


# ---------------------------------------------------------------------------
# utilidades
# ---------------------------------------------------------------------------
def titulo_vista(texto: str) -> QLabel:
    lbl = QLabel(texto)
    lbl.setStyleSheet(f"font-size: 20px; font-weight: 700; color: {COLORES['texto']};")
    return lbl


def confirmar(parent: QWidget | None, titulo: str, texto: str, aceptar: str = "Confirmar",
              peligro: bool = False) -> bool:
    """Confirmacion explicita iniciada por el usuario. Cancelar es la opcion por defecto."""
    caja = QMessageBox(QMessageBox.Icon.Question, titulo, texto,
                       QMessageBox.StandardButton.NoButton, parent)
    boton_ok = caja.addButton(aceptar, QMessageBox.ButtonRole.AcceptRole)
    boton_no = caja.addButton("Cancelar", QMessageBox.ButtonRole.RejectRole)
    if peligro:
        boton_ok.setProperty("variant", "danger")
    caja.setDefaultButton(boton_no)
    caja.setEscapeButton(boton_no)
    caja.exec()
    return caja.clickedButton() is boton_ok


def abrir_ruta(ruta) -> None:
    """Abre un archivo o carpeta con la aplicacion del sistema."""
    QDesktopServices.openUrl(QUrl.fromLocalFile(str(ruta)))


def mensaje_api(exc: BaseException) -> str:
    """Texto para el usuario. En 422 de forma enumera `campo: mensaje`; en el resto, el del servidor."""
    if isinstance(exc, ApiError) and exc.codigo == "VALIDACION":
        errores = exc.detalle.get("errores")
        if isinstance(errores, list) and errores:
            partes = []
            for e in errores:
                campo = str(e.get("campo", "")).split(".")[-1]
                partes.append(f"{campo}: {e.get('mensaje', '')}" if campo else str(e.get("mensaje", "")))
            return "; ".join(partes)
    return texto_error(exc)


def mostrar_estado(estado: EstadoVacio, titulo: str | None = None, mensaje: str | None = None) -> None:
    """Cambia los textos de un EstadoVacio y reserva la altura del mensaje (el widget compartido no la
    reserva y recorta el texto cuando ocupa varias lineas)."""
    if titulo is not None:
        estado._titulo.setText(titulo)
    if mensaje is not None:
        estado._mensaje.setText(mensaje)
    ancho = estado._mensaje.maximumWidth()
    estado._mensaje.setFixedWidth(ancho)                 # sin ancho fijo el layout lo estrecha y recorta
    caja = estado._mensaje.fontMetrics().boundingRect(
        QRect(0, 0, ancho, 10_000),
        int(Qt.TextFlag.TextWordWrap) | int(Qt.AlignmentFlag.AlignHCenter), estado._mensaje.text())
    estado._mensaje.setMinimumHeight(caja.height() + 8)


def moneda_publica(api) -> str:
    """Simbolo de moneda del negocio; '$' si no se puede consultar (la llamada principal ya fallaria)."""
    try:
        return api.config_publica().moneda or "$"
    except Exception:  # noqa: BLE001
        return "$"


def campos_con_error(exc: BaseException) -> dict[str, str]:
    """campo -> mensaje para errores 422 que identifican el campo (detalle.errores/campo/clave)."""
    if not isinstance(exc, ApiError) or exc.http != 422:
        return {}
    d = exc.detalle
    out: dict[str, str] = {}
    errores = d.get("errores")
    if isinstance(errores, list):
        for e in errores:
            campo = str(e.get("campo", "")).split(".")[-1]
            if campo:
                out[campo] = str(e.get("mensaje", "")) or exc.mensaje
    for clave in ("campo", "clave"):
        if isinstance(d.get(clave), str):
            out[d[clave]] = exc.mensaje
    if not out and "aviso_segundos" in d and "inactividad_segundos" in d:
        out["aviso_segundos"] = exc.mensaje
    return out


# ---------------------------------------------------------------------------
# vista base
# ---------------------------------------------------------------------------
class VistaBase(QWidget):
    """Base de las vistas: `recargar(silencioso)` consulta y pinta; el MainWindow la invoca."""

    def __init__(self, app_ctx, parent: QWidget | None = None):
        super().__init__(parent)
        self.ctx = app_ctx
        self.cargada = False
        self._gen = 0
        self._cargando = Cargando(self)

    # -- API que implementan las vistas ------------------------------------------------------
    def recargar(self, silencioso: bool = False) -> None:  # pragma: no cover - abstracto
        raise NotImplementedError

    # -- utilidades ----------------------------------------------------------------------------
    def toast(self, texto: str, tipo: str = "info", duracion_ms: int = 3500) -> Toast:
        return Toast.mostrar(self.window(), texto, tipo, duracion_ms)

    def consultar(self, fn: Callable[[], Any], ok: Callable[[Any], None],
                  err: Callable[[BaseException], None] | None = None,
                  silencioso: bool = False) -> None:
        """Ejecuta `fn` en un hilo. Solo la ULTIMA consulta entrega su resultado (evita pisar datos
        nuevos con respuestas lentas). Con `silencioso` no se muestra el overlay de carga."""
        self._gen += 1
        gen = self._gen
        if not silencioso:
            self._cargando.iniciar()

        def fin_ok(valor):
            if gen != self._gen:
                return
            self._cargando.detener()
            self.cargada = True
            ok(valor)

        def fin_err(exc):
            if gen != self._gen:
                return
            self._cargando.detener()
            if err is not None:
                err(exc)

        self.ctx.ejecutar(fn, fin_ok, fin_err, self)


# ---------------------------------------------------------------------------
# fila de producto en riesgo
# ---------------------------------------------------------------------------
class FilaRiesgo(QFrame):
    """Nivel, nombre y motivo, % de descuento y precio original tachado / sugerido."""

    def __init__(self, item: ItemRiesgo, moneda: str = "$", detalle_stock: bool = False,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self.item = item
        self.setObjectName("filaRiesgo")
        self.setStyleSheet(
            f"QFrame#filaRiesgo {{ background: {COLORES['superficie']};"
            f" border: 1px solid {COLORES['borde']}; border-radius: 8px; }}")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 10, 14, 10)
        lay.setSpacing(14)

        self.badge = BadgeNivel(item.nivel, self)
        self.badge.setFixedWidth(72)
        lay.addWidget(self.badge, 0, Qt.AlignmentFlag.AlignVCenter)

        info = QVBoxLayout()
        info.setSpacing(2)
        self.lbl_nombre = QLabel(item.nombre, self)
        self.lbl_nombre.setFont(fuente(13, QFont.Weight.DemiBold))
        self.lbl_nombre.setStyleSheet(f"color: {COLORES['texto']};")
        self.lbl_motivo = QLabel(item.motivo, self)
        self.lbl_motivo.setWordWrap(True)
        self.lbl_motivo.setStyleSheet(f"color: {COLORES['texto_suave']}; font-size: 12px;")
        info.addWidget(self.lbl_nombre)
        info.addWidget(self.lbl_motivo)
        if detalle_stock:
            self.lbl_stock = QLabel(f"{item.categoria} · Stock {item.stock} de {item.stock_maximo}", self)
            self.lbl_stock.setStyleSheet(f"color: {COLORES['texto_suave']}; font-size: 12px;")
            info.addWidget(self.lbl_stock)
        lay.addLayout(info, 1)

        if item.descuento > 0:
            self.lbl_desc = QLabel(f"-{item.descuento:g}%", self)
            self.lbl_desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.lbl_desc.setStyleSheet(
                f"color: {COLORES['descuento_texto']}; background: {COLORES['primario_fondo']};"
                f" font-size: 12px; font-weight: 700; padding: 4px 10px; border-radius: 9px;")
            lay.addWidget(self.lbl_desc, 0, Qt.AlignmentFlag.AlignVCenter)

        precios = QVBoxLayout()
        precios.setSpacing(0)
        if item.descuento > 0:
            self.lbl_original = QLabel(f"<s>{fmt_moneda(item.precio_original, moneda)}</s>", self)
            self.lbl_original.setTextFormat(Qt.TextFormat.RichText)
            self.lbl_original.setAlignment(Qt.AlignmentFlag.AlignRight)
            self.lbl_original.setStyleSheet(f"color: {COLORES['texto_suave']}; font-size: 12px;")
            precios.addWidget(self.lbl_original)
        self.lbl_final = QLabel(fmt_moneda(item.precio_final, moneda), self)
        self.lbl_final.setAlignment(Qt.AlignmentFlag.AlignRight)
        color = COLORES["exito_texto"] if item.descuento > 0 else COLORES["texto"]
        self.lbl_final.setStyleSheet(f"color: {color}; font-size: 14px; font-weight: 700;")
        precios.addWidget(self.lbl_final)
        cont = QWidget(self)
        cont.setLayout(precios)
        cont.setMinimumWidth(96)
        lay.addWidget(cont, 0, Qt.AlignmentFlag.AlignVCenter)


# ---------------------------------------------------------------------------
# dialogo de formulario
# ---------------------------------------------------------------------------
class DialogoFormulario(QDialog):
    """Dialogo no bloqueante (se abre con `open()`): valida en cliente, llama a la API en un hilo y
    muestra los errores del servidor (409/422) junto al campo o en un aviso. Subclases: `validar()`
    devuelve los datos o None (tras llamar a `error_campo`), y `llamar(datos)` hace la peticion."""

    guardado = pyqtSignal(object)

    def __init__(self, app_ctx, titulo: str, texto_guardar: str = "Guardar",
                 parent: QWidget | None = None, ancho: int = 440):
        super().__init__(parent)
        self.ctx = app_ctx
        self.setWindowTitle(titulo)
        self.setMinimumWidth(ancho)
        self.setStyleSheet(estilo_formulario() + f"QDialog {{ background: {COLORES['superficie']}; }}")
        self._campos: dict[str, tuple[QWidget, QLabel]] = {}
        self._ocupado = False
        self._texto_btn = texto_guardar

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(24, 22, 24, 20)
        raiz.setSpacing(12)
        lbl = QLabel(titulo, self)
        lbl.setStyleSheet(f"font-size: 17px; font-weight: 700; color: {COLORES['texto']};")
        raiz.addWidget(lbl)
        self.contenido = QVBoxLayout()
        self.contenido.setSpacing(10)
        raiz.addLayout(self.contenido)

        self.lbl_error = QLabel("", self)
        self.lbl_error.setObjectName("bannerError")
        self.lbl_error.setWordWrap(True)
        self.lbl_error.hide()
        raiz.addWidget(self.lbl_error)

        botones = QHBoxLayout()
        botones.addStretch(1)
        self.btn_cancelar = QPushButton("Cancelar", self)
        self.btn_guardar = QPushButton(texto_guardar, self)
        self.btn_guardar.setProperty("variant", "primary")
        self.btn_guardar.setDefault(True)
        self.btn_cancelar.clicked.connect(self.reject)
        self.btn_guardar.clicked.connect(self._al_guardar)
        botones.addWidget(self.btn_cancelar)
        botones.addWidget(self.btn_guardar)
        raiz.addLayout(botones)

    # -- construccion ----------------------------------------------------------------------------
    def agregar_campo(self, clave: str, etiqueta: str, widget: QWidget,
                      ayuda: str | None = None) -> QWidget:
        caja = QVBoxLayout()
        caja.setSpacing(4)
        et = QLabel(etiqueta, self)
        et.setObjectName("etiquetaCampo")
        caja.addWidget(et)
        caja.addWidget(widget)
        if ayuda:
            lbl_ayuda = QLabel(ayuda, self)
            lbl_ayuda.setStyleSheet(f"color: {COLORES['texto_suave']}; font-size: 11px;")
            caja.addWidget(lbl_ayuda)
        err = QLabel("", self)
        err.setObjectName("errorCampo")
        err.setWordWrap(True)
        err.hide()
        caja.addWidget(err)
        self.contenido.addLayout(caja)
        self._campos[clave] = (widget, err)
        for senal in ("textChanged", "currentTextChanged", "dateChanged"):
            if hasattr(widget, senal):
                getattr(widget, senal).connect(lambda *_a, k=clave: self._limpiar_campo(k))
        return widget

    def _limpiar_campo(self, clave: str) -> None:
        widget, lbl = self._campos[clave]
        if not lbl.isHidden():
            lbl.hide()
            lbl.setText("")
            self._marcar(widget, False)

    # -- errores -----------------------------------------------------------------------------------
    def error_campo(self, clave: str, texto: str) -> None:
        widget, lbl = self._campos[clave]
        lbl.setText(texto)
        lbl.show()
        self._marcar(widget, True)

    def limpiar_errores(self) -> None:
        for widget, lbl in self._campos.values():
            lbl.hide()
            lbl.setText("")
            self._marcar(widget, False)
        self.lbl_error.hide()
        self.lbl_error.setText("")

    def error_general(self, texto: str) -> None:
        self.lbl_error.setText(texto)
        self.lbl_error.show()

    def texto_error_campo(self, clave: str) -> str:
        return self._campos[clave][1].text()

    @staticmethod
    def _marcar(widget: QWidget, error: bool) -> None:
        widget.setProperty("error", "true" if error else "false")
        widget.style().unpolish(widget)
        widget.style().polish(widget)

    # -- guardado ------------------------------------------------------------------------------------
    def validar(self) -> Any | None:  # pragma: no cover - abstracto
        raise NotImplementedError

    def llamar(self, datos: Any) -> Any:  # pragma: no cover - abstracto
        raise NotImplementedError

    def _al_guardar(self) -> None:
        if self._ocupado:
            return
        self.limpiar_errores()
        datos = self.validar()
        if datos is None:
            for widget, lbl in self._campos.values():
                if not lbl.isHidden():
                    widget.setFocus()
                    break
            return
        self._poner_ocupado(True)
        self.ctx.ejecutar(lambda: self.llamar(datos), self._al_ok, self._al_error, self)

    def _poner_ocupado(self, ocupado: bool) -> None:
        self._ocupado = ocupado
        self.btn_guardar.setEnabled(not ocupado)
        self.btn_cancelar.setEnabled(not ocupado)
        self.btn_guardar.setText("Guardando…" if ocupado else self._texto_guardar())

    def _texto_guardar(self) -> str:
        return getattr(self, "_texto_btn", "Guardar")

    def _al_ok(self, resultado: Any) -> None:
        self._poner_ocupado(False)
        self.guardado.emit(resultado)
        self.accept()

    def _al_error(self, exc: BaseException) -> None:
        self._poner_ocupado(False)
        por_campo = {k: v for k, v in campos_con_error(exc).items() if k in self._campos}
        for clave, texto in por_campo.items():
            self.error_campo(clave, texto)
        if por_campo:
            return
        self.error_general(mensaje_api(exc))
