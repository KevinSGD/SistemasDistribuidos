"""Facturas (solo administrador): consulta y auditoria de SOLO LECTURA.

Las facturas son inmutables: esta pantalla no anula, edita ni borra nada. Filtra por fecha, texto
y metodo de pago (el servidor calcula tambien los totales con los mismos filtros), muestra el
detalle en el dialogo de factura y exporta a Excel. Se refresca con el evento `factura_creada` y
con el sondeo, sin pisar los filtros del usuario."""
from __future__ import annotations

from datetime import date, datetime, time
from pathlib import Path

from PyQt6.QtCore import QDate, Qt, QTimer
from PyQt6.QtWidgets import (
    QComboBox, QDateEdit, QFrame, QGridLayout, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
    QPushButton, QScrollArea, QSizePolicy, QStackedWidget, QVBoxLayout, QWidget,
)

from client.infrastructure.api_client import ErrorConexion
from client.infrastructure.factura_pdf import METODOS

from ..styles.theme import COLORES, fmt_moneda
from ..widgets import EstadoVacio, TablaEstandar, TarjetaResumen
from . import _comunes as c
from ._exportar_facturas import exportar_facturas_excel
from .factura_view import FacturaDialog

COLUMNAS = ["Número", "Fecha y hora", "Cliente", "Documento", "Método", "Cuenta", "Ahorro", "Total"]
COL_NUMERO, COL_FECHA, COL_CLIENTE, COL_DOC, COL_METODO, COL_CUENTA, COL_AHORRO, COL_TOTAL = range(8)
TABLA, VACIO, SIN_RESULTADOS, ERROR = range(4)
LIMITE_UI = 500                  # filas que baja la pantalla (el servidor admite hasta 1000)
DEBOUNCE_BUSQUEDA_MS = 350
MIN_ALTO_TABLA = 250
SIN_LIMITE = QDate(2000, 1, 1)   # fecha minima = "sin limite" (se muestra como texto especial)
SIN_DATO = "—"
ATAJOS = (("hoy", "Hoy"), ("7dias", "7 días"), ("mes", "Este mes"), ("todo", "Todo"))
METODOS_FILTRO = (("Todos los métodos", None), (METODOS["efectivo"], "efectivo"),
                  (METODOS["tarjeta_simulada"], "tarjeta_simulada"))


def _elidir(widget: QLabel, texto: str, ancho: int) -> str:
    return widget.fontMetrics().elidedText(texto, Qt.TextElideMode.ElideRight, ancho)


class PanelMini(QFrame):
    """Cuadro compacto de 3 columnas (nombre, cantidad, total) con filas fijas que se reescriben."""

    def __init__(self, titulo: str, filas: int, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("panelMini")
        self.setStyleSheet(
            f"QFrame#panelMini {{ background: {COLORES['superficie']};"
            f" border: 1px solid {COLORES['borde']}; border-radius: 10px; }}"
            f" QFrame#panelMini QLabel {{ border: none; font-size: 12px; color: {COLORES['texto']}; }}")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 10, 14, 10)
        lay.setSpacing(6)
        self.lbl_titulo = QLabel(titulo, self)
        self.lbl_titulo.setStyleSheet(
            f"color: {COLORES['texto_suave']}; font-size: 12px; font-weight: 600; border: none;")
        lay.addWidget(self.lbl_titulo)
        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(3)
        grid.setColumnStretch(0, 1)
        self.celdas: list[tuple[QLabel, QLabel, QLabel]] = []
        for i in range(filas):
            nombre, cant, total = QLabel(self), QLabel(self), QLabel(self)
            nombre.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
            cant.setStyleSheet(f"color: {COLORES['texto_suave']};")
            for w in (cant, total):
                w.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            total.setStyleSheet("font-weight: 700;")
            grid.addWidget(nombre, i, 0)
            grid.addWidget(cant, i, 1)
            grid.addWidget(total, i, 2)
            self.celdas.append((nombre, cant, total))
        lay.addLayout(grid)
        lay.addStretch(1)

    def set_filas(self, filas: list[tuple[str, str, str]], vacio: str = "Sin datos") -> None:
        if not filas:
            filas = [(vacio, "", "")]
        for i, (nombre, cant, total) in enumerate(self.celdas):
            if i < len(filas):
                n, q, t = filas[i]
                nombre.setToolTip(n)
                nombre.setText(_elidir(nombre, n, 230))
                cant.setText(q)
                total.setText(t)
            for w in (nombre, cant, total):
                w.setVisible(i < len(filas))

    def textos(self) -> list[tuple[str, str, str]]:
        return [(n.toolTip() or n.text(), q.text(), t.text())
                for n, q, t in self.celdas if not n.isHidden()]


class FacturasView(c.VistaBase):
    def __init__(self, app_ctx, parent: QWidget | None = None):
        super().__init__(app_ctx, parent)
        self._facturas: list = []
        self._por_numero: dict = {}
        self._resumen = None
        self._moneda = "$"
        self._iva_pct = 0.0
        self._negocio = "Mi Negocio"
        self._exportando = False
        self._ultimo_reporte: Path | None = None
        self.dialogo_factura: FacturaDialog | None = None
        self.setStyleSheet(c.estilo_formulario())

        # Todo el contenido va en un area con scroll: en ventanas bajas la tabla conserva una
        # altura minima legible y la pagina se desplaza, en vez de aplastar la tabla.
        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        contenido = QWidget()
        contenido.setObjectName("contenidoFacturas")
        contenido.setStyleSheet("QWidget#contenidoFacturas { background: transparent; }")
        scroll.setWidget(contenido)
        raiz.addWidget(scroll)
        lay = QVBoxLayout(contenido)
        lay.setContentsMargins(32, 24, 32, 8)
        lay.setSpacing(10)

        cab = QHBoxLayout()
        cab.addWidget(c.titulo_vista("Facturas"))
        sub = QLabel("Consulta y auditoría · las facturas son de solo lectura", self)
        sub.setStyleSheet(f"color: {COLORES['texto_suave']}; font-size: 12px; padding-left: 10px;")
        cab.addWidget(sub, 0, Qt.AlignmentFlag.AlignBottom)
        cab.addStretch(1)
        lay.addLayout(cab)

        # -- filtros ---------------------------------------------------------------------------
        fila1 = QHBoxLayout()
        fila1.setSpacing(8)
        self.f_desde = self._crear_fecha("Fecha inicial del rango (vacía = sin límite)")
        self.f_hasta = self._crear_fecha("Fecha final del rango (vacía = sin límite)")
        fila1.addWidget(self._etiqueta("Desde"))
        fila1.addWidget(self.f_desde)
        fila1.addWidget(self._etiqueta("Hasta"))
        fila1.addWidget(self.f_hasta)
        fila1.addSpacing(6)
        self.atajos: dict[str, QPushButton] = {}
        for clave, texto in ATAJOS:
            b = QPushButton(texto, self)
            b.setCheckable(True)
            b.setAccessibleName(f"Rango: {texto}")
            b.setStyleSheet(
                f"QPushButton {{ padding: 4px 12px; min-height: 20px; }}"
                f" QPushButton:checked {{ background: {COLORES['primario_fondo']};"
                f" color: {COLORES['descuento_texto']}; border: 1px solid {COLORES['primario']}; }}")
            b.clicked.connect(lambda _=False, k=clave: self.aplicar_atajo(k))
            fila1.addWidget(b)
            self.atajos[clave] = b
        fila1.addStretch(1)
        lay.addLayout(fila1)

        fila2 = QHBoxLayout()
        fila2.setSpacing(8)
        self.busqueda = QLineEdit(self)
        self.busqueda.setPlaceholderText("Buscar por número, cliente o documento")
        self.busqueda.setClearButtonEnabled(True)
        self.busqueda.setMinimumWidth(320)
        self.busqueda.setAccessibleName("Buscar facturas")
        self.combo_metodo = QComboBox(self)
        self.combo_metodo.setMinimumWidth(190)
        self.combo_metodo.setAccessibleName("Filtrar por método de pago")
        for etiqueta, valor in METODOS_FILTRO:
            self.combo_metodo.addItem(etiqueta, valor)
        fila2.addWidget(self.busqueda, 2)
        fila2.addWidget(self.combo_metodo, 1)
        fila2.addStretch(2)
        lay.addLayout(fila2)

        self._timer_busqueda = QTimer(self)
        self._timer_busqueda.setSingleShot(True)
        self._timer_busqueda.setInterval(DEBOUNCE_BUSQUEDA_MS)
        self._timer_busqueda.timeout.connect(self._filtros_cambiaron)
        self.busqueda.textChanged.connect(lambda _t: self._timer_busqueda.start())
        self.combo_metodo.currentIndexChanged.connect(lambda _i: self._filtros_cambiaron())
        self.f_desde.dateChanged.connect(lambda _d: self._fecha_manual())
        self.f_hasta.dateChanged.connect(lambda _d: self._fecha_manual())

        # -- tarjetas --------------------------------------------------------------------------
        tarjetas = QHBoxLayout()
        tarjetas.setSpacing(10)
        self.t_cantidad = TarjetaResumen("Facturas", "–", "texto_secundario", self)
        self.t_total = TarjetaResumen("Total vendido", "–", "primario_texto", self)
        self.t_ahorro = TarjetaResumen("Ahorro otorgado", "–", "exito_texto", self)
        self.t_iva = TarjetaResumen("IVA", "–", "texto_secundario", self)
        self.t_ticket = TarjetaResumen("Ticket promedio", "–", "texto", self)
        for t in (self.t_cantidad, self.t_total, self.t_ahorro, self.t_iva, self.t_ticket):
            t.setMinimumSize(120, 74)
            t._valor.setStyleSheet(
                f"color: {t.color_valor}; font-size: 22px; font-weight: 700; border: none;")
            tarjetas.addWidget(t, 1)
        lay.addLayout(tarjetas)

        paneles = QHBoxLayout()
        paneles.setSpacing(10)
        self.panel_metodos = PanelMini("Ventas por método de pago", 2, self)
        self.panel_top = PanelMini("Top 5 productos (por unidades)", 5, self)
        paneles.addWidget(self.panel_metodos, 1)
        paneles.addWidget(self.panel_top, 2)
        lay.addLayout(paneles)

        # -- franja del ultimo reporte ------------------------------------------------------------
        self.barra_reporte = QFrame(self)
        self.barra_reporte.setObjectName("barraReporte")
        self.barra_reporte.setStyleSheet(
            f"QFrame#barraReporte {{ background: {COLORES['exito_fondo']};"
            f" border: 1px solid {COLORES['exito_borde']}; border-radius: 8px; }}"
            f" QFrame#barraReporte QLabel {{ color: {COLORES['exito_oscuro']}; font-size: 12px; }}")
        br = QHBoxLayout(self.barra_reporte)
        br.setContentsMargins(14, 6, 8, 6)
        self.lbl_reporte = QLabel("", self.barra_reporte)
        self.btn_abrir_archivo = QPushButton("Abrir archivo", self.barra_reporte)
        self.btn_abrir_carpeta = QPushButton("Abrir carpeta", self.barra_reporte)
        self.btn_cerrar_reporte = QPushButton("✕", self.barra_reporte)
        self.btn_cerrar_reporte.setFixedWidth(34)
        self.btn_cerrar_reporte.setToolTip("Ocultar")
        self.btn_cerrar_reporte.setAccessibleName("Ocultar aviso de reporte")
        for b in (self.btn_abrir_archivo, self.btn_abrir_carpeta, self.btn_cerrar_reporte):
            b.setStyleSheet("padding: 3px 10px; min-height: 18px; font-size: 12px;")
        br.addWidget(self.lbl_reporte, 1)
        br.addWidget(self.btn_abrir_archivo)
        br.addWidget(self.btn_abrir_carpeta)
        br.addWidget(self.btn_cerrar_reporte)
        self.btn_abrir_archivo.clicked.connect(lambda: self._abrir(archivo=True))
        self.btn_abrir_carpeta.clicked.connect(lambda: self._abrir(archivo=False))
        self.btn_cerrar_reporte.clicked.connect(self.barra_reporte.hide)
        self.barra_reporte.hide()
        lay.addWidget(self.barra_reporte)

        # -- tabla y estados ------------------------------------------------------------------------
        self.paginas = QStackedWidget(self)
        self.paginas.setMinimumHeight(MIN_ALTO_TABLA)
        lay.addWidget(self.paginas, 1)
        self.tabla = TablaEstandar(COLUMNAS, self)
        self.tabla.setAccessibleName("Tabla de facturas")
        h = self.tabla.horizontalHeader()
        for col in range(len(COLUMNAS)):
            h.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(COL_CLIENTE, QHeaderView.ResizeMode.Stretch)
        h.setStretchLastSection(False)
        h.setSortIndicator(COL_FECHA, Qt.SortOrder.DescendingOrder)
        self.tabla.itemSelectionChanged.connect(self._actualizar_botones)
        self.tabla.itemDoubleClicked.connect(lambda *_: self.ver_factura())
        self.paginas.addWidget(self.tabla)
        self.estado_vacio = EstadoVacio(
            "∅", "Aún no hay facturas",
            "Las facturas aparecerán aquí cuando los compradores realicen compras.", None, self)
        c.mostrar_estado(self.estado_vacio)
        self.paginas.addWidget(self.estado_vacio)
        self.estado_sin_resultados = EstadoVacio(
            "∅", "Sin coincidencias", "Ninguna factura coincide con los filtros aplicados.",
            "Limpiar filtros", self)
        c.mostrar_estado(self.estado_sin_resultados)
        self.estado_sin_resultados.accion.connect(self.limpiar_filtros)
        self.paginas.addWidget(self.estado_sin_resultados)
        self.estado_error = EstadoVacio.error_conexion(self)
        c.mostrar_estado(self.estado_error)
        self.estado_error.accion.connect(lambda: self.recargar(manual=True))
        self.paginas.addWidget(self.estado_error)

        # -- pie ----------------------------------------------------------------------------------------
        pie = QHBoxLayout()               # fijo al pie (fuera del area con scroll)
        pie.setContentsMargins(32, 6, 32, 18)
        pie.setSpacing(8)
        self.btn_ver = QPushButton("Ver factura", self)
        self.btn_ver.setProperty("variant", "primary")
        self.btn_ver.clicked.connect(self.ver_factura)
        self.lbl_conteo = QLabel("", self)
        self.lbl_conteo.setStyleSheet(f"color: {COLORES['texto_suave']}; font-size: 12px;")
        self.btn_actualizar = QPushButton("Actualizar", self)
        self.btn_actualizar.clicked.connect(lambda: self.recargar(manual=True))
        self.btn_excel = QPushButton("Exportar a Excel", self)
        self.btn_excel.clicked.connect(self.exportar)
        pie.addWidget(self.btn_ver)
        pie.addSpacing(10)
        pie.addWidget(self.lbl_conteo)
        pie.addStretch(1)
        pie.addWidget(self.btn_actualizar)
        pie.addWidget(self.btn_excel)
        raiz.addLayout(pie)
        self._actualizar_botones()

    # -- construccion ---------------------------------------------------------------------------------
    @staticmethod
    def _etiqueta(texto: str) -> QLabel:
        lbl = QLabel(texto)
        lbl.setStyleSheet(f"color: {COLORES['texto_secundario']}; font-size: 12px; font-weight: 600;")
        return lbl

    def _crear_fecha(self, ayuda: str) -> QDateEdit:
        d = QDateEdit(self)
        d.setCalendarPopup(True)
        d.setDisplayFormat("dd/MM/yyyy")
        d.setMinimumDate(SIN_LIMITE)
        d.setSpecialValueText("Sin límite")
        d.setDate(SIN_LIMITE)
        d.setMinimumWidth(130)
        d.setToolTip(ayuda)
        d.setAccessibleName(ayuda)
        return d

    # -- filtros -----------------------------------------------------------------------------------------
    def filtros(self) -> dict:
        """Filtros vigentes tal como se envian al servidor (desde 00:00, hasta 23:59:59)."""
        d, h = self.f_desde.date(), self.f_hasta.date()
        return {
            "desde": datetime.combine(d.toPyDate(), time.min) if d != SIN_LIMITE else None,
            "hasta": datetime.combine(h.toPyDate(), time.max) if h != SIN_LIMITE else None,
            "q": self.busqueda.text().strip() or None,
            "metodo_pago": self.combo_metodo.currentData(),
        }

    def hay_filtros(self) -> bool:
        return any(v is not None for v in self.filtros().values())

    def describir_filtros(self) -> str:
        f = self.filtros()
        partes = []
        if f["desde"]:
            partes.append(f"desde {f['desde']:%Y-%m-%d}")
        if f["hasta"]:
            partes.append(f"hasta {f['hasta']:%Y-%m-%d}")
        if f["q"]:
            partes.append(f"texto «{f['q']}»")
        if f["metodo_pago"]:
            partes.append(f"método {METODOS.get(f['metodo_pago'], f['metodo_pago'])}")
        return ", ".join(partes)

    def _marcar_atajo(self, clave: str | None) -> None:
        for k, b in self.atajos.items():
            b.setChecked(k == clave)

    def aplicar_atajo(self, clave: str) -> None:
        hoy = date.today()
        if clave == "hoy":
            desde = hasta = hoy
        elif clave == "7dias":
            desde, hasta = date.fromordinal(hoy.toordinal() - 6), hoy
        elif clave == "mes":
            desde, hasta = hoy.replace(day=1), hoy
        else:
            desde = hasta = None
        for w, d in ((self.f_desde, desde), (self.f_hasta, hasta)):
            w.blockSignals(True)
            w.setDate(QDate(d.year, d.month, d.day) if d else SIN_LIMITE)
            w.blockSignals(False)
        self._marcar_atajo(clave)
        self._filtros_cambiaron()

    def _fecha_manual(self) -> None:
        self._marcar_atajo(None)
        self._filtros_cambiaron()

    def limpiar_filtros(self) -> None:
        self.busqueda.blockSignals(True)
        self.busqueda.clear()
        self.busqueda.blockSignals(False)
        self.combo_metodo.blockSignals(True)
        self.combo_metodo.setCurrentIndex(0)
        self.combo_metodo.blockSignals(False)
        self.aplicar_atajo("todo")

    def _filtros_cambiaron(self) -> None:
        self._timer_busqueda.stop()
        self.lbl_conteo.setText("Actualizando…")
        self.recargar(silencioso=True, manual=True)

    # -- carga -----------------------------------------------------------------------------------------------
    def recargar(self, silencioso: bool = False, manual: bool = False) -> None:
        """`silencioso`: sin overlay (eventos, sondeo, cambios de filtro). `manual`: el usuario lo
        pidio, asi que un fallo se muestra aunque ya hubiera datos."""
        api = self.ctx.api
        if api is None:
            return
        filtros = self.filtros()

        def trabajo():
            lista = api.listar_facturas(filtros["desde"], filtros["hasta"], LIMITE_UI,
                                        q=filtros["q"], metodo_pago=filtros["metodo_pago"])
            resumen = api.resumen_facturas(filtros["desde"], filtros["hasta"], q=filtros["q"],
                                           metodo_pago=filtros["metodo_pago"])
            try:
                cfg = api.config_publica()
                publica = (cfg.moneda or "$", float(cfg.iva_pct or 0), cfg.nombre_negocio)
            except Exception:  # noqa: BLE001 - la moneda es cosmetica; se usa el valor anterior
                publica = (self._moneda, self._iva_pct, self._negocio)
            return lista, resumen, publica

        self.consultar(trabajo, self._pintar, lambda exc: self._error(exc, silencioso, manual),
                       silencioso)

    def _error(self, exc: BaseException, silencioso: bool, manual: bool) -> None:
        if silencioso and not manual and self.cargada and self.paginas.currentIndex() != ERROR:
            return                                   # se conservan los ultimos datos buenos
        c.mostrar_estado(
            self.estado_error,
            "Sin conexión con el servidor" if isinstance(exc, ErrorConexion)
            else "No se pudieron cargar las facturas", c.mensaje_api(exc))
        self.paginas.setCurrentIndex(ERROR)
        self.lbl_conteo.setText("")
        self.panel_metodos.set_filas([], "–")
        self.panel_top.set_filas([], "–")
        for t in (self.t_cantidad, self.t_total, self.t_ahorro, self.t_iva, self.t_ticket):
            t.set_valor("–")
        self._actualizar_botones()

    def _pintar(self, datos) -> None:
        lista, resumen, (moneda, iva_pct, negocio) = datos
        self._moneda, self._iva_pct, self._negocio = moneda, iva_pct, negocio
        self._facturas = list(lista)
        self._por_numero = {f.numero: f for f in self._facturas}
        self._resumen = resumen

        m = lambda v: fmt_moneda(v, moneda)           # noqa: E731
        self.t_cantidad.set_valor(f"{resumen.cantidad:,}".replace(",", "."))
        self.t_total.set_valor(m(resumen.total))
        self.t_ahorro.set_valor(m(resumen.ahorro))
        self.t_iva.set_valor(m(resumen.iva))
        self.t_ticket.set_valor(m(resumen.ticket_promedio))
        self.panel_metodos.set_filas([
            (METODOS.get(x.metodo, x.metodo), f"{x.cantidad} fact.", m(x.total))
            for x in resumen.por_metodo], "Sin ventas")
        self.panel_top.set_filas([
            (f"{i}. {t.nombre}", f"{t.unidades} uds", m(t.total))
            for i, t in enumerate(resumen.top_productos, 1)], "Sin ventas")

        self._llenar_tabla()
        n = len(self._facturas)
        if resumen.cantidad > n:
            self.lbl_conteo.setText(f"Mostrando {n} de {resumen.cantidad} facturas · "
                                    "afina los filtros para ver el resto")
        else:
            self.lbl_conteo.setText(f"{n} factura" + ("" if n == 1 else "s"))
        if n:
            self.paginas.setCurrentIndex(TABLA)
        else:
            self.paginas.setCurrentIndex(SIN_RESULTADOS if self.hay_filtros() else VACIO)
        self._actualizar_botones()

    def _llenar_tabla(self) -> None:
        seleccion = self.numero_seleccionado()
        scroll = self.tabla.verticalScrollBar().value()
        m = self._moneda
        filas = [[
            f.numero, f.fecha.timestamp(), f.cliente.nombre or SIN_DATO,
            f.cliente.documento or SIN_DATO, METODOS.get(f.metodo_pago, f.metodo_pago),
            f.usuario_nombre or SIN_DATO, f.ahorro, f.total,
        ] for f in self._facturas]
        # El tiempo se guarda como numero para ordenar bien; se muestra como fecha legible.
        self.tabla.set_filas(filas, formateadores={
            COL_FECHA: lambda ts: datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M"),
            COL_AHORRO: lambda v: SIN_DATO if not v else fmt_moneda(v, m),
            COL_TOTAL: lambda v: fmt_moneda(v, m)})
        izq = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        for r in range(self.tabla.rowCount()):
            self.tabla.item(r, COL_FECHA).setTextAlignment(izq)
        enc = self.tabla.horizontalHeaderItem(COL_FECHA)
        if enc is not None:
            enc.setTextAlignment(izq)
        if seleccion:
            for r in range(self.tabla.rowCount()):
                if self.tabla.texto(r, COL_NUMERO) == seleccion:
                    self.tabla.selectRow(r)
                    break
        self.tabla.verticalScrollBar().setValue(scroll)

    # -- seleccion y detalle ---------------------------------------------------------------------------------
    def numero_seleccionado(self) -> str | None:
        fila = self.tabla.currentRow()
        if fila < 0 or not self.tabla.selectedItems():
            return None
        return self.tabla.texto(fila, COL_NUMERO) or None

    def factura_seleccionada(self):
        n = self.numero_seleccionado()
        return self._por_numero.get(n) if n else None

    def _actualizar_botones(self) -> None:
        self.btn_ver.setEnabled(self.paginas.currentIndex() == TABLA
                                and self.factura_seleccionada() is not None)
        self.btn_excel.setEnabled(not self._exportando and self.tabla.rowCount() > 0
                                  and self.paginas.currentIndex() == TABLA)

    def ver_factura(self) -> None:
        f = self.factura_seleccionada()
        if f is None:
            return
        dlg = FacturaDialog(self.ctx, f, self._iva_pct, self.window(), modo_consulta=True)
        self.dialogo_factura = dlg
        dlg.finished.connect(lambda _=0: setattr(self, "dialogo_factura", None))
        dlg.open()

    # -- evento en vivo -------------------------------------------------------------------------------------------
    def avisar_nueva(self, payload: dict) -> None:
        numero = payload.get("numero") if isinstance(payload, dict) else None
        self.toast(f"Nueva factura {numero}" if numero else "Nueva factura", "info", 3000)

    # -- exportacion ------------------------------------------------------------------------------------------------
    def filas_visibles(self) -> list:
        """FacturaOut en el orden en que se ven en la tabla."""
        return [self._por_numero[n] for r in range(self.tabla.rowCount())
                if (n := self.tabla.texto(r, COL_NUMERO)) in self._por_numero]

    def exportar(self) -> None:
        if self._exportando:
            return
        filas = self.filas_visibles()
        if not filas or self._resumen is None:
            self.toast("No hay facturas para exportar", "aviso")
            return
        resumen, moneda, negocio = self._resumen, self._moneda, self._negocio
        filtros = self.describir_filtros()
        self._exportando = True
        self.btn_excel.setText("Exportando…")
        self._actualizar_botones()

        def fin():
            self._exportando = False
            self.btn_excel.setText("Exportar a Excel")
            self._actualizar_botones()

        def ok(ruta: Path):
            fin()
            self._ultimo_reporte = ruta
            parcial = resumen.cantidad > len(filas)
            detalle = f"{len(filas)} de {resumen.cantidad} facturas" if parcial else f"{len(filas)} facturas"
            self.lbl_reporte.setText(f"Reporte guardado: {ruta.name} ({detalle})")
            self.lbl_reporte.setToolTip(str(ruta))
            self.barra_reporte.show()
            self.toast(f"Excel guardado: {ruta.name}", "exito", 5000)

        def err(exc: BaseException):
            fin()
            self.toast(f"No se pudo exportar: {exc}", "error", 6000)

        self.ctx.ejecutar(
            lambda: exportar_facturas_excel(filas, resumen, moneda, negocio, filtros),
            ok, err, self)

    def _abrir(self, archivo: bool) -> None:
        if self._ultimo_reporte is not None:
            c.abrir_ruta(self._ultimo_reporte if archivo else self._ultimo_reporte.parent)

    # -- ayudas para pruebas ---------------------------------------------------------------------------------------------
    @property
    def pagina(self) -> int:
        return self.paginas.currentIndex()

    def numeros(self) -> list[str]:
        return [self.tabla.texto(r, COL_NUMERO) for r in range(self.tabla.rowCount())]
