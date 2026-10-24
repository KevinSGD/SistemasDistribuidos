"""Dialogo de pago: pedido, datos del cliente y metodo (efectivo / tarjeta simulada). RF-17..RF-19.

La compra se envia con POST /compras en un worker. El IVA lo calcula el servidor sobre el precio
ya con descuento; aqui solo se PREVISUALIZA con `iva_pct`, y la factura final usa la respuesta.
Los numeros de tarjeta no existen en este dialogo: no se piden, no se guardan ni se envian."""
from __future__ import annotations

import re

from PyQt6.QtCore import Qt, QRegularExpression, pyqtSignal
from PyQt6.QtGui import QRegularExpressionValidator
from PyQt6.QtWidgets import (
    QButtonGroup, QDialog, QFrame, QGridLayout, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QPushButton,
    QRadioButton, QVBoxLayout, QWidget,
)

from client.application.mensajes import texto_error
from client.infrastructure.api_client import ApiError
from shared.dinero import dec
from shared.schemas import ClienteIn, CompraIn, FacturaOut, ItemCompraIn, PagoIn

from ..styles.theme import COLORES, fmt_moneda
from ..widgets import TablaEstandar
from .carrito_modelo import LineaCarrito, r2

#: errores de la compra que invalidan el pedido (el carrito se ajusta y el dialogo se cierra)
CODIGOS_PEDIDO_INVALIDO = frozenset({"STOCK_INSUFICIENTE", "PRODUCTO_VENCIDO",
                                     "PRODUCTO_INACTIVO", "NO_ENCONTRADO"})


# -- validaciones y utilidades puras --------------------------------------------------------
_RE_NOMBRE = re.compile(r"^[A-Za-zÁÉÍÓÚÜÑáéíóúüñ0-9 .,'&\-]+$")
_RE_DOC = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.\-]*$")


def validar_nombre(texto: str) -> str | None:
    """None si es valido; si no, el mensaje de error."""
    t = (texto or "").strip()
    if not t:
        return "El nombre es obligatorio"
    if len(t) > 150:
        return "Máximo 150 caracteres"
    if sum(c.isalpha() for c in t) < 2 or not _RE_NOMBRE.match(t):
        return "Escribe un nombre válido (letras, espacios, . , ' - &)"
    return None


def validar_documento(texto: str) -> str | None:
    t = (texto or "").strip()
    if not t:
        return "El documento es obligatorio"
    if len(t) > 20:
        return "Máximo 20 caracteres"
    if len(t) < 5 or not _RE_DOC.match(t) or sum(c.isalnum() for c in t) < 5:
        return "Documento no válido (mínimo 5 letras o números; se permiten . y -)"
    return None


def parsear_monto(texto: str, decimales: int = 0) -> float | None:
    """Convierte lo escrito por el usuario ('25000', '25.000', '25.000,50', '25,5') a float.
    None si esta vacio o no se entiende."""
    t = re.sub(r"[\s$]", "", texto or "")
    if not t or not re.fullmatch(r"[0-9.,]+", t):
        return None
    if "." in t and "," in t:
        dec = "," if t.rfind(",") > t.rfind(".") else "."
        mil = "." if dec == "," else ","
        t = t.replace(mil, "").replace(dec, ".")
    elif "," in t or "." in t:
        sep = "," if "," in t else "."
        partes = t.split(sep)
        if len(partes) == 2 and 1 <= len(partes[1]) <= 2:
            t = partes[0] + "." + partes[1]                 # decimal
        else:
            t = "".join(partes)                             # separador de miles
    try:
        return r2(float(t), decimales)
    except ValueError:
        return None


def calcular_vista_previa(lineas: list[LineaCarrito], iva_pct: float, decimales: int = 0) -> dict:
    """Total estimado en el cliente (el servidor tiene la ultima palabra)."""
    subtotal = r2(sum(l.subtotal_original for l in lineas), decimales)
    base = r2(sum(l.subtotal_final for l in lineas), decimales)
    iva = r2(dec(base) * dec(float(iva_pct or 0)) / 100, decimales)
    return {"subtotal": subtotal, "ahorro": r2(subtotal - base, decimales), "base": base,
            "iva": iva, "total": r2(base + iva, decimales)}


def _lbl(texto="", px=13, color="texto", peso=400, derecha=False) -> QLabel:
    l = QLabel(texto)
    l.setStyleSheet(f"font-size: {px}px; color: {COLORES[color]}; font-weight: {peso};")
    if derecha:
        l.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    return l


def _caja(nombre: str, fondo="superficie", borde="borde") -> QFrame:
    f = QFrame()
    f.setObjectName(nombre)
    f.setStyleSheet(f"QFrame#{nombre} {{ background: {COLORES[fondo]};"
                    f" border: 1px solid {COLORES[borde]}; border-radius: 8px; }}")
    return f


class PagoDialog(QDialog):
    compra_exitosa = pyqtSignal(object)        # FacturaOut
    pedido_rechazado = pyqtSignal(object)      # ApiError 409 (el carrito debe ajustarse)

    def __init__(self, app_ctx, lineas: list[LineaCarrito], moneda: str = "$", iva_pct: float = 0.0,
                 decimales: int = 0, parent: QWidget | None = None):
        super().__init__(parent)
        self._ctx = app_ctx
        self.lineas = list(lineas)
        self.moneda = moneda or "$"
        self.iva_pct = float(iva_pct or 0)
        self.decimales = int(decimales or 0)
        self.vista = calcular_vista_previa(self.lineas, self.iva_pct, self.decimales)
        self.factura: FacturaOut | None = None
        self.procesando = False
        self._tocados: set[str] = set()
        self.setWindowTitle("Proceso de pago")
        self.setMinimumSize(780, 720)
        self.setModal(True)
        self.setStyleSheet(
            "QRadioButton { spacing: 8px; font-size: 13px; }"
            f"QRadioButton::indicator {{ width: 14px; height: 14px; border-radius: 8px;"
            f" border: 2px solid {COLORES['borde_input']}; background: {COLORES['superficie']}; }}"
            f"QRadioButton::indicator:checked {{ border: 2px solid {COLORES['primario']};"
            f" background: qradialgradient(cx:0.5, cy:0.5, radius:0.5, fx:0.5, fy:0.5,"
            f" stop:0 {COLORES['primario']}, stop:0.45 {COLORES['primario']},"
            f" stop:0.5 {COLORES['superficie']}, stop:1 {COLORES['superficie']}); }}")
        self._construir()
        self._validar()

    # -- construccion ---------------------------------------------------------------------
    def _construir(self) -> None:
        m = self.moneda
        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(28, 22, 28, 22)
        raiz.setSpacing(12)
        raiz.addWidget(_lbl("Resumen y pago", 19, "texto", 700))

        self.tabla = TablaEstandar(["Producto", "Cant.", "Precio unit.", "Desc.", "P. c/desc.", "Subtotal"])
        self.tabla.set_filas(
            [[l.nombre, l.cantidad, l.precio_original, l.descuento, l.precio_final, l.subtotal_final]
             for l in self.lineas],
            formateador=lambda v: fmt_moneda(v, m, self.decimales),
            formateadores={1: str, 3: lambda v: f"-{v:g}%" if v else "—"})
        self.tabla.setSortingEnabled(False)
        self.tabla.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        cab = self.tabla.horizontalHeader()
        cab.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        cab.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        cab.setStretchLastSection(False)
        self.tabla.setSelectionMode(TablaEstandar.SelectionMode.NoSelection)
        self.tabla.verticalHeader().setDefaultSectionSize(34)
        self.tabla.setMaximumHeight(min(210, 44 + 34 * max(1, len(self.lineas))))
        raiz.addWidget(self.tabla)

        # Totales (vista previa)
        tot = QGridLayout()
        tot.setColumnStretch(0, 1)
        filas = [("Subtotal sin descuento", fmt_moneda(self.vista["subtotal"], m, self.decimales), "texto_suave", 400)]
        if self.vista["ahorro"]:
            filas.append(("Ahorro", "-" + fmt_moneda(self.vista["ahorro"], m, self.decimales), "exito_texto", 700))
        if self.iva_pct:
            filas.append(("Base gravable", fmt_moneda(self.vista["base"], m, self.decimales), "texto_suave", 400))
            filas.append((f"IVA {self.iva_pct:g}% (estimado)", fmt_moneda(self.vista["iva"], m, self.decimales),
                          "texto_suave", 400))
        for i, (k, v, c, p) in enumerate(filas):
            tot.addWidget(_lbl(k, 12, c, p, True), i, 0)
            tot.addWidget(_lbl(v, 12, c, p, True), i, 1)
        n = len(filas)
        tot.addWidget(_lbl("TOTAL A PAGAR", 15, "texto", 700, True), n, 0)
        self.lbl_total = _lbl(fmt_moneda(self.vista["total"], m, self.decimales), 18, "primario_texto", 700, True)
        tot.addWidget(self.lbl_total, n, 1)
        raiz.addLayout(tot)

        cols = QHBoxLayout()
        cols.setSpacing(14)
        cols.addWidget(self._panel_cliente(), 1)
        cols.addWidget(self._panel_pago(), 1)
        raiz.addLayout(cols)

        self.lbl_error = QLabel("")
        self.lbl_error.setWordWrap(True)
        self.lbl_error.setVisible(False)
        self.lbl_error.setStyleSheet(
            f"background: {COLORES['peligro_fondo']}; color: {COLORES['peligro']}; font-size: 13px;"
            f" font-weight: 600; border: 1px solid {COLORES['peligro']}; border-radius: 6px; padding: 8px 12px;")
        raiz.addWidget(self.lbl_error)

        botones = QHBoxLayout()
        self.btn_cancelar = QPushButton("Cancelar")
        self.btn_cancelar.setMinimumHeight(40)
        self.btn_cancelar.clicked.connect(self.reject)
        self.btn_confirmar = QPushButton("Confirmar pago")
        self.btn_confirmar.setProperty("variant", "primary")
        self.btn_confirmar.setMinimumHeight(40)
        self.btn_confirmar.setMinimumWidth(180)
        self.btn_confirmar.setDefault(True)
        self.btn_confirmar.clicked.connect(self._confirmar)
        botones.addWidget(self.btn_cancelar)
        botones.addStretch(1)
        botones.addWidget(self.btn_confirmar)
        raiz.addLayout(botones)

    def _panel_cliente(self) -> QFrame:
        caja = _caja("cajaCliente")
        lay = QVBoxLayout(caja)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(4)
        lay.addWidget(_lbl("Datos del cliente", 13, "texto", 700))
        lay.addSpacing(4)
        lay.addWidget(_lbl("Nombre completo", 12, "texto_suave"))
        self.input_nombre = QLineEdit()
        self.input_nombre.setPlaceholderText("Ej. María Pérez")
        self.input_nombre.setMaxLength(150)
        self.input_nombre.setAccessibleName("Nombre del cliente")
        lay.addWidget(self.input_nombre)
        self.err_nombre = _lbl("", 11, "peligro", 600)
        lay.addWidget(self.err_nombre)
        lay.addWidget(_lbl("Documento (cédula, NIT)", 12, "texto_suave"))
        self.input_documento = QLineEdit()
        self.input_documento.setPlaceholderText("Ej. 1020304050")
        self.input_documento.setMaxLength(20)
        self.input_documento.setAccessibleName("Documento del cliente")
        lay.addWidget(self.input_documento)
        self.err_documento = _lbl("", 11, "peligro", 600)
        lay.addWidget(self.err_documento)
        lay.addStretch(1)
        self.input_nombre.textChanged.connect(lambda _: self._validar("nombre"))
        self.input_documento.textChanged.connect(lambda _: self._validar("documento"))
        self.input_nombre.editingFinished.connect(lambda: self._validar("nombre", True))
        self.input_documento.editingFinished.connect(lambda: self._validar("documento", True))
        return caja

    def _panel_pago(self) -> QFrame:
        caja = _caja("cajaPago", "exito_fondo", "exito_borde")
        lay = QVBoxLayout(caja)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(6)
        lay.addWidget(_lbl("Método de pago", 13, "exito_oscuro", 700))
        fila = QHBoxLayout()
        self.radio_efectivo = QRadioButton("Efectivo")
        self.radio_tarjeta = QRadioButton("Tarjeta (simulada)")
        self.radio_efectivo.setChecked(True)
        grupo = QButtonGroup(self)
        grupo.addButton(self.radio_efectivo)
        grupo.addButton(self.radio_tarjeta)
        fila.addWidget(self.radio_efectivo)
        fila.addWidget(self.radio_tarjeta)
        fila.addStretch(1)
        lay.addLayout(fila)

        # Efectivo
        self.panel_efectivo = QWidget()
        pe = QVBoxLayout(self.panel_efectivo)
        pe.setContentsMargins(0, 4, 0, 0)
        pe.setSpacing(6)
        pe.addWidget(_lbl("Monto recibido", 12, "texto_suave"))
        fila_m = QHBoxLayout()
        self.input_monto = QLineEdit()
        self.input_monto.setPlaceholderText("0")
        self.input_monto.setAccessibleName("Monto recibido")
        self.input_monto.setValidator(QRegularExpressionValidator(
            QRegularExpression(r"[0-9.,\s$]{0,18}"), self.input_monto))
        self.btn_exacto = QPushButton("Exacto")
        self.btn_exacto.setToolTip("Pagar el total exacto")
        self.btn_exacto.clicked.connect(self._poner_exacto)
        fila_m.addWidget(self.input_monto, 1)
        fila_m.addWidget(self.btn_exacto)
        pe.addLayout(fila_m)
        fila_c = QHBoxLayout()
        fila_c.addWidget(_lbl("Cambio", 12, "texto_suave", 600))
        self.lbl_cambio = _lbl("—", 15, "exito_texto", 700, True)
        fila_c.addWidget(self.lbl_cambio, 1)
        pe.addLayout(fila_c)
        self.lbl_faltante = _lbl("", 12, "peligro", 700)
        self.lbl_faltante.setWordWrap(True)
        pe.addWidget(self.lbl_faltante)
        lay.addWidget(self.panel_efectivo)

        # Tarjeta simulada
        self.panel_tarjeta = QWidget()
        pt = QVBoxLayout(self.panel_tarjeta)
        pt.setContentsMargins(0, 4, 0, 0)
        self.lbl_tarjeta = _lbl("Pago simulado: la tarjeta se autoriza automáticamente.\n"
                                "No se solicitan, guardan ni envían números de tarjeta.",
                                12, "texto_secundario")
        self.lbl_tarjeta.setWordWrap(True)
        pt.addWidget(self.lbl_tarjeta)
        lay.addWidget(self.panel_tarjeta)
        lay.addStretch(1)
        self.panel_tarjeta.setVisible(False)

        self.radio_efectivo.toggled.connect(self._cambio_metodo)
        self.input_monto.textChanged.connect(lambda _: self._validar())
        return caja

    # -- estado -----------------------------------------------------------------------------
    @property
    def metodo(self) -> str:
        return "efectivo" if self.radio_efectivo.isChecked() else "tarjeta_simulada"

    @property
    def monto(self) -> float | None:
        return parsear_monto(self.input_monto.text(), self.decimales)

    def _cambio_metodo(self) -> None:
        efectivo = self.radio_efectivo.isChecked()
        self.panel_efectivo.setVisible(efectivo)
        self.panel_tarjeta.setVisible(not efectivo)
        self._validar()

    def _poner_exacto(self) -> None:
        t = self.vista["total"]
        self.input_monto.setText(f"{t:.{self.decimales}f}".rstrip("0").rstrip(".")
                                 if self.decimales and t != int(t) else str(int(t)))

    def _marcar_campo(self, campo: QLineEdit, label: QLabel, error: str | None, mostrar: bool) -> None:
        label.setText(error if (error and mostrar) else "")
        campo.setProperty("error", "true" if (error and mostrar) else "false")
        campo.style().unpolish(campo)
        campo.style().polish(campo)

    def _validar(self, campo: str | None = None, terminado: bool = False) -> bool:
        """Actualiza mensajes y habilita Confirmar. Los errores de un campo se muestran cuando el
        usuario ya escribio en el (o termino de editarlo)."""
        if campo and (terminado or (campo == "nombre" and self.input_nombre.text())
                      or (campo == "documento" and self.input_documento.text())):
            self._tocados.add(campo)
        err_n = validar_nombre(self.input_nombre.text())
        err_d = validar_documento(self.input_documento.text())
        self._marcar_campo(self.input_nombre, self.err_nombre, err_n, "nombre" in self._tocados)
        self._marcar_campo(self.input_documento, self.err_documento, err_d, "documento" in self._tocados)
        ok_pago = True
        if self.metodo == "efectivo":
            monto = self.monto
            total = self.vista["total"]
            if monto is None:
                self.lbl_cambio.setText("—")
                self.lbl_faltante.setText("")
                ok_pago = False
            elif r2(monto, self.decimales) < total:
                self.lbl_cambio.setText("—")
                self.lbl_faltante.setText(f"Faltan {fmt_moneda(r2(total - monto, self.decimales), self.moneda, self.decimales)} "
                                          "para completar el pago")
                ok_pago = False
            else:
                self.lbl_cambio.setText(fmt_moneda(r2(monto - total, self.decimales), self.moneda, self.decimales))
                self.lbl_faltante.setText("")
        valido = err_n is None and err_d is None and ok_pago
        self.btn_confirmar.setEnabled(valido and not self.procesando)
        return valido

    def _bloquear(self, bloqueado: bool) -> None:
        for w in (self.input_nombre, self.input_documento, self.input_monto, self.btn_exacto,
                  self.radio_efectivo, self.radio_tarjeta, self.btn_cancelar):
            w.setEnabled(not bloqueado)

    # -- confirmar --------------------------------------------------------------------------
    def construir_compra(self) -> CompraIn:
        pago = (PagoIn(metodo="efectivo", efectivo_recibido=self.monto)
                if self.metodo == "efectivo" else PagoIn(metodo="tarjeta_simulada"))
        return CompraIn(
            items=[ItemCompraIn(producto_id=l.producto_id, cantidad=l.cantidad) for l in self.lineas],
            cliente=ClienteIn(nombre=self.input_nombre.text().strip(),
                              documento=self.input_documento.text().strip()),
            pago=pago)

    def _confirmar(self) -> None:
        if self.procesando:                       # doble clic / Enter repetido
            return
        self._tocados.update({"nombre", "documento"})
        if not self._validar():
            return
        api = self._ctx.api
        if api is None:
            return
        compra = self.construir_compra()
        self.lbl_error.setVisible(False)
        self.procesando = True
        self._bloquear(True)
        self.btn_confirmar.setEnabled(False)
        self.btn_confirmar.setText("Procesando…")
        if self.metodo == "tarjeta_simulada":
            self.lbl_tarjeta.setText("Autorizando tarjeta simulada…")
        self._ctx.ejecutar(lambda: api.comprar(compra), self._compra_ok, self._compra_error, self)

    def _terminar_proceso(self) -> None:
        self.procesando = False
        self._bloquear(False)
        self.btn_confirmar.setText("Confirmar pago")
        self.lbl_tarjeta.setText("Pago simulado: la tarjeta se autoriza automáticamente.\n"
                                 "No se solicitan, guardan ni envían números de tarjeta.")
        self._validar()

    def _compra_ok(self, factura: FacturaOut) -> None:
        self.factura = factura
        self.procesando = False
        self.compra_exitosa.emit(factura)
        self.accept()

    def _compra_error(self, exc: BaseException) -> None:
        self._terminar_proceso()
        if isinstance(exc, ApiError) and exc.codigo in CODIGOS_PEDIDO_INVALIDO:
            self.pedido_rechazado.emit(exc)       # la ventana ajusta el carrito y refresca
            self.reject()
            return
        if isinstance(exc, ApiError) and exc.codigo == "EFECTIVO_INSUFICIENTE":
            falta = exc.detalle.get("faltante")
            self.mostrar_error("El efectivo recibido no alcanza para el total confirmado por el servidor"
                               + (f": faltan {fmt_moneda(falta, self.moneda, self.decimales)}." if falta else "."))
            return
        self.mostrar_error(texto_error(exc))

    def mostrar_error(self, texto: str) -> None:
        self.lbl_error.setText(texto)
        self.lbl_error.setVisible(True)

    def reject(self) -> None:  # noqa: D401
        if self.procesando:                       # no cancelar a mitad de una compra
            return
        super().reject()
