"""Configuracion (admin): negocio, descuentos, umbrales, escaneo y Seguridad de sesion (GET/PUT /config).

El efecto sobre la sesion abierta lo aplica `Aplicacion` al recibir el evento `config_cambiada`
(refresca el IdleMonitor). Esta vista solo lo vigila y, si el WebSocket no lo entrego a tiempo, hace
una unica consulta de respaldo a /auth/sesion."""
from __future__ import annotations

from PyQt6.QtCore import QRegularExpression, Qt, QTimer
from PyQt6.QtGui import QRegularExpressionValidator
from PyQt6.QtWidgets import (
    QComboBox, QDoubleSpinBox, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QScrollArea, QSpinBox, QVBoxLayout, QWidget,
)

from shared.schemas import ConfigUpdate

from ..styles.theme import COLORES
from . import _comunes as c

INACTIVIDAD_MIN, INACTIVIDAD_MAX, AVISO_MIN = 30, 3600, 5
MONEDAS = ["$", "€", "£", "USD", "COP", "MXN"]

#: Valores por defecto del servidor (server/infrastructure/db/seed.py) para "Restablecer".
#: No incluye los datos del negocio (nombre, NIT, direccion, telefono, moneda, IVA).
DEFECTOS: dict[str, int | float] = {
    "descuento_critico": 50.0, "descuento_alto": 30.0, "descuento_medio": 15.0,
    "descuento_sobrestock": 10.0,
    "dias_alerta_vencimiento": 7, "dias_critico_vencimiento": 3, "umbral_stock_bajo": 10,
    "intervalo_escaneo_segundos": 60,
    "inactividad_segundos": 180, "aviso_segundos": 30,
}
TEXTOS = ("nombre_negocio", "nit", "direccion", "telefono", "moneda")
DECIMALES = ("iva_pct", "descuento_critico", "descuento_alto", "descuento_medio", "descuento_sobrestock")
ENTEROS = ("dias_alerta_vencimiento", "dias_critico_vencimiento", "umbral_stock_bajo",
           "intervalo_escaneo_segundos", "inactividad_segundos", "aviso_segundos")
CLAVES_SESION = ("inactividad_segundos", "aviso_segundos")


def duracion(n: int) -> str:
    """90 -> '1 min 30 s'; 45 -> '45 s'."""
    return f"{n // 60} min {n % 60} s" if n >= 60 else f"{n} s"


def vista_previa(inactividad: int, aviso: int) -> str:
    return (f"Se cerrará la sesión tras {duracion(inactividad)} sin actividad; "
            f"aviso {duracion(aviso)} antes")


class _Rueda:
    """Evita cambiar valores con la rueda del raton al desplazar el formulario."""

    def wheelEvent(self, ev):  # noqa: N802
        if self.hasFocus():
            super().wheelEvent(ev)
        else:
            ev.ignore()


class _Spin(_Rueda, QSpinBox):
    pass


class _SpinDec(_Rueda, QDoubleSpinBox):
    pass


class ConfigView(c.VistaBase):
    def __init__(self, app_ctx, parent: QWidget | None = None):
        super().__init__(app_ctx, parent)
        self.setStyleSheet(c.estilo_formulario())
        self._widgets: dict[str, QWidget] = {}
        self._errores: dict[str, QLabel] = {}
        self._base: dict[str, object] = {}
        self._srv: dict[str, str] = {}          # errores devueltos por el servidor, por campo
        self._esperado: tuple[int, int] | None = None
        self._intentos = 0
        self._guardando = False

        lay = QVBoxLayout(self)
        lay.setContentsMargins(32, 28, 32, 20)
        lay.setSpacing(14)
        lay.addWidget(c.titulo_vista("Configuración"))

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        cont = QWidget()
        cont.setStyleSheet("background: transparent;")
        cols = QHBoxLayout(cont)
        cols.setContentsMargins(0, 0, 8, 0)
        cols.setSpacing(16)
        izq, der = QVBoxLayout(), QVBoxLayout()
        izq.setSpacing(16)
        der.setSpacing(16)
        cols.addLayout(izq, 1)
        cols.addLayout(der, 1)
        izq.addWidget(self._seccion_negocio())
        izq.addWidget(self._seccion_sesion())
        izq.addStretch(1)
        der.addWidget(self._seccion_descuentos())
        der.addWidget(self._seccion_umbrales())
        der.addWidget(self._seccion_escaneo())
        der.addStretch(1)
        scroll.setWidget(cont)
        lay.addWidget(scroll, 1)

        self.lbl_error = QLabel("", self)
        self.lbl_error.setObjectName("bannerError")
        self.lbl_error.setWordWrap(True)
        self.lbl_error.hide()
        lay.addWidget(self.lbl_error)

        pie = QHBoxLayout()
        pie.setSpacing(8)
        self.btn_defectos = QPushButton("Restablecer valores por defecto", self)
        self.btn_defectos.clicked.connect(self.restablecer)
        self.btn_descartar = QPushButton("Descartar cambios", self)
        self.btn_descartar.clicked.connect(self.descartar)
        self.btn_guardar = QPushButton("Guardar configuración", self)
        self.btn_guardar.setProperty("variant", "primary")
        self.btn_guardar.clicked.connect(self.guardar)
        pie.addWidget(self.btn_defectos)
        pie.addStretch(1)
        pie.addWidget(self.btn_descartar)
        pie.addWidget(self.btn_guardar)
        lay.addLayout(pie)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._vigilar)
        self._refrescar_validacion()

    # ---------------------------------------------------------------------------------------------
    # construccion
    # ---------------------------------------------------------------------------------------------
    def _tarjeta(self, titulo: str, descripcion: str = "") -> tuple[QFrame, QGridLayout]:
        marco = QFrame(self)
        marco.setObjectName("seccion")
        marco.setStyleSheet(
            f"QFrame#seccion {{ background: {COLORES['superficie']}; border: 1px solid {COLORES['borde']};"
            f" border-radius: 10px; }} QFrame#seccion QLabel {{ border: none; background: transparent; }}")
        v = QVBoxLayout(marco)
        v.setContentsMargins(20, 16, 20, 18)
        v.setSpacing(4)
        t = QLabel(titulo, marco)
        t.setStyleSheet(f"font-size: 14px; font-weight: 700; color: {COLORES['primario_texto']};")
        v.addWidget(t)
        if descripcion:
            d = QLabel(descripcion, marco)
            d.setWordWrap(True)
            d.setStyleSheet(f"font-size: 12px; color: {COLORES['texto_suave']};")
            v.addWidget(d)
        v.addSpacing(6)
        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(4)
        grid.setColumnStretch(1, 1)
        v.addLayout(grid)
        return marco, grid

    def _fila(self, grid: QGridLayout, clave: str, etiqueta: str, widget: QWidget) -> None:
        r = grid.rowCount()
        lbl = QLabel(etiqueta, self)
        lbl.setStyleSheet(f"font-size: 12px; font-weight: 600; color: {COLORES['texto_secundario']};")
        lbl.setMinimumWidth(150)
        grid.addWidget(lbl, r, 0, Qt.AlignmentFlag.AlignVCenter)
        grid.addWidget(widget, r, 1)
        err = QLabel("", self)
        err.setObjectName("errorCampo")
        err.setWordWrap(True)
        err.hide()
        grid.addWidget(err, r + 1, 1)
        self._widgets[clave] = widget
        self._errores[clave] = err
        widget.setAccessibleName(etiqueta)
        if isinstance(widget, QLineEdit):
            widget.textChanged.connect(lambda *_a, k=clave: self._al_cambiar(k))
        elif isinstance(widget, QComboBox):
            widget.currentTextChanged.connect(lambda *_a, k=clave: self._al_cambiar(k))
        else:
            widget.valueChanged.connect(lambda *_a, k=clave: self._al_cambiar(k))

    def _texto(self, ancho_max: int = 150) -> QLineEdit:
        e = QLineEdit(self)
        e.setMaxLength(ancho_max)
        return e

    def _dec(self, maximo: float = 100.0) -> QDoubleSpinBox:
        s = _SpinDec(self)
        s.setRange(0, maximo)
        s.setDecimals(2)
        s.setSuffix(" %")
        s.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        s.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.NoButtons)
        return s

    def _ent(self, minimo: int, maximo: int, sufijo: str = "") -> QSpinBox:
        s = _Spin(self)
        s.setRange(minimo, maximo)
        s.setSuffix(sufijo)
        s.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        s.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
        return s

    def _seccion_negocio(self) -> QFrame:
        marco, g = self._tarjeta("Datos del negocio", "Aparecen en las facturas.")
        self._fila(g, "nombre_negocio", "Nombre del negocio", self._texto(150))
        self._fila(g, "nit", "NIT / RUT", self._texto(50))
        self._fila(g, "direccion", "Dirección", self._texto(200))
        self._fila(g, "telefono", "Teléfono", self._texto(50))
        moneda = QComboBox(self)
        moneda.setEditable(True)
        moneda.addItems(MONEDAS)
        moneda.lineEdit().setMaxLength(10)
        self._fila(g, "moneda", "Moneda", moneda)
        self._fila(g, "iva_pct", "IVA", self._dec())
        return marco

    def _seccion_descuentos(self) -> QFrame:
        marco, g = self._tarjeta("Reglas de descuento", "Porcentaje que se aplica según el nivel de riesgo.")
        self._fila(g, "descuento_critico", "Nivel crítico", self._dec())
        self._fila(g, "descuento_alto", "Nivel alto", self._dec())
        self._fila(g, "descuento_medio", "Nivel medio", self._dec())
        self._fila(g, "descuento_sobrestock", "Sobrestock", self._dec())
        return marco

    def _seccion_umbrales(self) -> QFrame:
        marco, g = self._tarjeta("Umbrales de alerta")
        self._fila(g, "dias_alerta_vencimiento", "Días de alerta por vencimiento", self._ent(0, 3650, " días"))
        self._fila(g, "dias_critico_vencimiento", "Días en nivel crítico", self._ent(0, 3650, " días"))
        self._fila(g, "umbral_stock_bajo", "Stock bajo", self._ent(0, 1_000_000, " unidades"))
        return marco

    def _seccion_escaneo(self) -> QFrame:
        marco, g = self._tarjeta("Automatización", "Cada cuánto el servidor evalúa el inventario.")
        self._fila(g, "intervalo_escaneo_segundos", "Escaneo cada", self._ent(10, 3600, " s"))
        return marco

    def _seccion_sesion(self) -> QFrame:
        marco, g = self._tarjeta(
            "Seguridad de sesión",
            "Cierra la sesión de cualquier usuario sin actividad (teclado o ratón) y avisa antes.")
        for clave, etiqueta in (("inactividad_segundos", "Tiempo de inactividad (s)"),
                                ("aviso_segundos", "Aviso previo (s)")):
            e = QLineEdit(self)
            e.setValidator(QRegularExpressionValidator(QRegularExpression(r"\d{0,5}"), e))
            e.setMaxLength(5)
            self._fila(g, clave, etiqueta, e)
        self.lbl_rango = QLabel(
            f"Inactividad: {INACTIVIDAD_MIN}–{INACTIVIDAD_MAX} s (por defecto 180). "
            f"Aviso: mínimo {AVISO_MIN} s y menor que la inactividad (por defecto 30).", self)
        self.lbl_rango.setWordWrap(True)
        self.lbl_rango.setStyleSheet(f"font-size: 11px; color: {COLORES['texto_suave']};")
        g.addWidget(self.lbl_rango, g.rowCount(), 0, 1, 2)
        self.lbl_previa = QLabel("", self)
        self.lbl_previa.setWordWrap(True)
        self.lbl_previa.setObjectName("previaSesion")
        self.lbl_previa.setStyleSheet(
            f"QLabel#previaSesion {{ background: {COLORES['primario_fondo']}; color: {COLORES['primario_texto']};"
            f" border-radius: 6px; padding: 8px 12px; font-size: 12px; font-weight: 600; }}")
        g.addWidget(self.lbl_previa, g.rowCount(), 0, 1, 2)
        self.lbl_vigente = QLabel("", self)
        self.lbl_vigente.setWordWrap(True)
        self.lbl_vigente.setStyleSheet(f"font-size: 12px; color: {COLORES['exito_texto']}; font-weight: 600;")
        self.lbl_vigente.hide()
        g.addWidget(self.lbl_vigente, g.rowCount(), 0, 1, 2)
        return marco

    # ---------------------------------------------------------------------------------------------
    # valores
    # ---------------------------------------------------------------------------------------------
    def _leer(self, clave: str):
        """Valor actual del widget con su tipo; None si el campo es invalido/vacio."""
        w = self._widgets[clave]
        if clave in TEXTOS:
            return (w.currentText() if isinstance(w, QComboBox) else w.text()).strip()
        if clave in DECIMALES:
            return round(w.value(), 2)
        if clave in CLAVES_SESION:
            t = w.text().strip()
            return int(t) if t.isdigit() else None
        return w.value()

    def _escribir(self, clave: str, valor) -> None:
        w = self._widgets[clave]
        w.blockSignals(True)
        try:
            if isinstance(w, QComboBox):
                if w.findText(str(valor)) < 0:
                    w.addItem(str(valor))
                w.setCurrentText(str(valor))
            elif isinstance(w, QLineEdit):
                w.setText("" if valor is None else str(valor))
            else:
                w.setValue(valor)
        finally:
            w.blockSignals(False)

    def valores(self) -> dict:
        return {k: self._leer(k) for k in self._widgets}

    def cambios(self) -> dict:
        """Claves modificadas respecto a lo guardado en el servidor."""
        out = {}
        for k, v in self.valores().items():
            b = self._base.get(k)
            if isinstance(v, float) or isinstance(b, float):
                if v is None or b is None or abs(float(v) - float(b)) > 1e-9:
                    out[k] = v
            elif v != b:
                out[k] = v
        return out

    def hay_cambios(self) -> bool:
        return bool(self._base) and bool(self.cambios())

    # ---------------------------------------------------------------------------------------------
    # validacion en vivo
    # ---------------------------------------------------------------------------------------------
    def errores_locales(self) -> dict[str, str]:
        v = self.valores()
        e: dict[str, str] = {}
        if not self._base:
            return e                                 # aun sin datos del servidor
        inact, aviso = v["inactividad_segundos"], v["aviso_segundos"]
        if inact is None:
            e["inactividad_segundos"] = "Ingresa un número entero"
        elif not INACTIVIDAD_MIN <= inact <= INACTIVIDAD_MAX:
            e["inactividad_segundos"] = f"Debe estar entre {INACTIVIDAD_MIN} y {INACTIVIDAD_MAX} segundos"
        if aviso is None:
            e["aviso_segundos"] = "Ingresa un número entero"
        elif aviso < AVISO_MIN:
            e["aviso_segundos"] = f"Debe ser de al menos {AVISO_MIN} segundos"
        elif inact is not None and aviso >= inact:
            e["aviso_segundos"] = "Debe ser menor que el tiempo de inactividad"
        if not v["nombre_negocio"]:
            e["nombre_negocio"] = "El nombre del negocio es obligatorio"
        if not v["moneda"]:
            e["moneda"] = "La moneda es obligatoria"
        if v["dias_critico_vencimiento"] > v["dias_alerta_vencimiento"]:
            e["dias_critico_vencimiento"] = "No puede superar los días de alerta"
        return e

    def _al_cambiar(self, clave: str) -> None:
        self._srv.pop(clave, None)               # el error del servidor sobre este campo ya no aplica
        self.lbl_error.hide()
        self._refrescar_validacion()

    def _mostrar_error(self, clave: str, texto: str) -> None:
        lbl, w = self._errores[clave], self._widgets[clave]
        lbl.setText(texto)
        lbl.setVisible(bool(texto))
        w.setProperty("error", "true" if texto else "false")
        w.style().unpolish(w)
        w.style().polish(w)

    def _refrescar_validacion(self) -> None:
        errores = self.errores_locales()
        for clave in self._widgets:
            self._mostrar_error(clave, errores.get(clave) or self._srv.get(clave, ""))
        v = self.valores()
        sesion_ok = (not any(k in errores for k in CLAVES_SESION)
                     and v["inactividad_segundos"] is not None and v["aviso_segundos"] is not None)
        self.lbl_previa.setText(vista_previa(v["inactividad_segundos"], v["aviso_segundos"])
                                if sesion_ok else
                                ("Corrige los valores para ver la vista previa" if self._base else ""))
        self.lbl_previa.setEnabled(sesion_ok)
        cambios = self.hay_cambios()
        self.btn_guardar.setEnabled(cambios and not errores and not self._guardando)
        self.btn_descartar.setEnabled(cambios and not self._guardando)
        self.btn_guardar.setToolTip("" if cambios else "No hay cambios por guardar")

    # ---------------------------------------------------------------------------------------------
    # carga
    # ---------------------------------------------------------------------------------------------
    def recargar(self, silencioso: bool = False) -> None:
        api = self.ctx.api
        if api is None:
            return
        if self.cargada and self.hay_cambios():
            return                                   # no se pisan ediciones sin guardar
        self.consultar(api.obtener_config, self._aplicar,
                       lambda e: self._falla_carga(e, silencioso), silencioso)

    def _falla_carga(self, exc: BaseException, silencioso: bool) -> None:
        if not silencioso:
            self.toast(c.mensaje_api(exc), "error", 6000)

    def _aplicar(self, cfg) -> None:
        datos = cfg.model_dump()
        self._base = {}
        for k in self._widgets:
            val = datos.get(k)
            if k in DECIMALES and val is not None:
                val = round(float(val), 2)
            elif k in TEXTOS:
                val = val or ""
            self._base[k] = val
            self._escribir(k, val)
        self._srv.clear()
        self.lbl_error.hide()
        self._refrescar_validacion()

    def descartar(self) -> None:
        self._srv.clear()
        for k, v in self._base.items():
            self._escribir(k, v)
        self.lbl_error.hide()
        self._refrescar_validacion()

    # ---------------------------------------------------------------------------------------------
    # guardado
    # ---------------------------------------------------------------------------------------------
    def guardar(self) -> None:
        if self.errores_locales():
            return
        cambios = self.cambios()
        if not cambios:
            self.toast("No hay cambios por guardar", "info")
            return
        self._enviar(cambios, "Configuración guardada")

    def restablecer(self) -> None:
        if not c.confirmar(
                self.window(), "Restablecer valores por defecto",
                "Se restablecerán los descuentos, umbrales, el intervalo de escaneo y la seguridad de "
                "sesión a sus valores originales.\n\nLos datos del negocio no se modifican.",
                "Restablecer", peligro=True):
            return
        diff = {k: v for k, v in DEFECTOS.items()
                if abs(float(self._base.get(k) or 0) - float(v)) > 1e-9 or k not in self._base}
        if not diff:
            self.toast("La configuración ya tiene los valores por defecto", "info")
            return
        self._enviar(diff, "Valores por defecto restablecidos")

    def _enviar(self, cambios: dict, mensaje_ok: str) -> None:
        api = self.ctx.api
        if api is None or self._guardando:
            return
        self._guardando = True
        self.lbl_error.hide()
        self.btn_guardar.setEnabled(False)
        self.btn_guardar.setText("Guardando…")
        modelo = ConfigUpdate(**cambios)

        def ok(cfg):
            self._fin_guardado()
            self._aplicar(cfg)
            self.toast(mensaje_ok, "exito")
            if any(k in cambios for k in CLAVES_SESION):
                self._vigilar_aplicacion(cfg.inactividad_segundos, cfg.aviso_segundos)

        def err(exc: BaseException):
            self._fin_guardado()
            por_campo = {k: t for k, t in c.campos_con_error(exc).items() if k in self._widgets}
            self._srv.update(por_campo)
            self._refrescar_validacion()
            if not por_campo:
                self.lbl_error.setText(c.mensaje_api(exc))
                self.lbl_error.show()
            self.toast(c.mensaje_api(exc), "error", 6000)

        self.ctx.ejecutar(lambda: api.actualizar_config(modelo), ok, err, self)

    def _fin_guardado(self) -> None:
        self._guardando = False
        self.btn_guardar.setText("Guardar configuración")
        self._refrescar_validacion()

    # ---------------------------------------------------------------------------------------------
    # efecto sobre la sesion abierta
    # ---------------------------------------------------------------------------------------------
    def _vigilar_aplicacion(self, inactividad: int, aviso: int) -> None:
        self._esperado = (inactividad, aviso)
        self._intentos = 0
        self.lbl_vigente.setText("Aplicando a tu sesión actual…")
        self.lbl_vigente.show()
        self._timer.start(250)

    def aplicado_en_sesion(self) -> bool:
        idle = self.ctx.idle
        return (idle is not None and self._esperado is not None
                and (idle.inactividad_segundos, idle.aviso_segundos) == self._esperado)

    def _vigilar(self) -> None:
        self._intentos += 1
        if self.aplicado_en_sesion():
            self._timer.stop()
            self.lbl_vigente.setText("✓ Aplicado a tu sesión actual. " + vista_previa(*self._esperado))
        elif self._intentos == 10:
            self._respaldo()                         # el evento WS no llego: una consulta directa
        elif self._intentos > 40:
            self._timer.stop()
            self.lbl_vigente.setText("No se pudo confirmar el cambio en esta sesión; se aplicará en el "
                                     "próximo inicio de sesión.")

    def _respaldo(self) -> None:
        api, ctx = self.ctx.api, self.ctx

        def ok(est):
            if ctx.api is api and ctx.idle is not None:
                ctx.idle.actualizar_config(est.inactividad_segundos, est.aviso_segundos)
                if ctx.sesion is not None:
                    ctx.sesion.inactividad_segundos = est.inactividad_segundos
                    ctx.sesion.aviso_segundos = est.aviso_segundos

        if api is not None:
            ctx.ejecutar(api.estado_sesion, ok, None, self)
