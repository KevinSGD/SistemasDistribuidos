"""Inventario: tabla con busqueda/filtro, alta, edicion, baja logica y exportacion (xlsx/pdf)."""
from __future__ import annotations

import math
from datetime import date, datetime
from pathlib import Path

from PyQt6.QtCore import QDate, Qt
from PyQt6.QtGui import QColor, QFont
from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QDateEdit, QFrame, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
    QPushButton, QStackedWidget, QVBoxLayout, QWidget,
)

from client.infrastructure.api_client import ErrorConexion
from shared.schemas import ProductoIn, ProductoUpdate

from ..styles.theme import COLOR_NIVEL, COLORES, fmt_moneda
from ..widgets import EstadoVacio, TablaEstandar
from . import _comunes as c
from ._exportar import COLUMNAS, ETIQUETA_NIVEL, FilaInventario, exportar_excel, exportar_pdf

TABLA, VACIO, SIN_RESULTADOS, ERROR = 0, 1, 2, 3
TODAS = "Todas las categorías"
_RANGO_NIVEL = {"critico": 3, "alto": 2, "medio": 1, "normal": 0}
COL_ID, COL_NOMBRE, COL_CATEGORIA, COL_BASE, COL_FINAL, COL_STOCK, COL_MAX, COL_VENC, COL_RIESGO = range(9)


def _numero(texto: str, entero: bool = False) -> float | int | None:
    t = (texto or "").strip().replace(",", ".")
    if not t:
        return None
    try:
        v = float(t)
    except ValueError:
        return None
    if not math.isfinite(v) or (entero and v != int(v)):
        return None
    return int(v) if entero else v


# ---------------------------------------------------------------------------
# dialogo de producto
# ---------------------------------------------------------------------------
class ProductoDialog(c.DialogoFormulario):
    def __init__(self, app_ctx, producto: FilaInventario | None = None,
                 categorias: list[str] | None = None, parent: QWidget | None = None):
        super().__init__(app_ctx, "Editar producto" if producto else "Agregar producto",
                         "Guardar cambios" if producto else "Crear producto", parent)
        self._producto = producto
        self.nombre = QLineEdit(self)
        self.nombre.setPlaceholderText("Ej. Leche entera 1 L")
        self.nombre.setMaxLength(100)
        self.categoria = QComboBox(self)
        self.categoria.setEditable(True)
        self.categoria.addItems(sorted(set(categorias or []) | {"General"}))
        self.categoria.lineEdit().setMaxLength(50)
        self.precio = QLineEdit(self)
        self.precio.setPlaceholderText("0")
        self.stock = QLineEdit(self)
        self.stock.setPlaceholderText("0")
        self.stock_max = QLineEdit(self)
        self.stock_max.setPlaceholderText("100")
        self.tiene_venc = QCheckBox("El producto tiene fecha de vencimiento", self)
        self.vencimiento = QDateEdit(self)
        self.vencimiento.setCalendarPopup(True)
        self.vencimiento.setDisplayFormat("dd/MM/yyyy")
        self.vencimiento.setDate(QDate.currentDate().addDays(30))
        self.vencimiento.setEnabled(False)
        self.tiene_venc.toggled.connect(self.vencimiento.setEnabled)

        self.agregar_campo("nombre", "Nombre *", self.nombre)
        self.agregar_campo("categoria", "Categoría", self.categoria)
        self.agregar_campo("precio_base", "Precio base *", self.precio)
        fila = QHBoxLayout()
        fila.setSpacing(12)
        self.contenido.addLayout(fila)
        # stock y stock maximo comparten fila: cada campo en su propia columna
        col_a, col_b = QVBoxLayout(), QVBoxLayout()
        fila.addLayout(col_a)
        fila.addLayout(col_b)
        self._columna(col_a, "stock", "Stock *", self.stock)
        self._columna(col_b, "stock_maximo", "Stock máximo *", self.stock_max)
        self.contenido.addWidget(self.tiene_venc)
        self.agregar_campo("fecha_vencimiento", "Fecha de vencimiento", self.vencimiento)

        if producto:
            self.nombre.setText(producto.nombre)
            i = self.categoria.findText(producto.categoria)
            if i >= 0:
                self.categoria.setCurrentIndex(i)
            else:
                self.categoria.setEditText(producto.categoria)
            self.precio.setText(f"{producto.precio_base:g}")
            self.stock.setText(str(producto.stock))
            self.stock_max.setText(str(producto.stock_maximo))
            if producto.vencimiento:
                self.tiene_venc.setChecked(True)
                d = date.fromisoformat(producto.vencimiento)
                self.vencimiento.setDate(QDate(d.year, d.month, d.day))
        else:
            self.categoria.setCurrentText("General")

    def _columna(self, caja: QVBoxLayout, clave: str, etiqueta: str, widget: QWidget) -> None:
        """Como agregar_campo, pero dentro de una columna existente."""
        previo = self.contenido
        self.contenido = caja
        try:
            self.agregar_campo(clave, etiqueta, widget)
        finally:
            self.contenido = previo

    def _fecha(self) -> date | None:
        if not self.tiene_venc.isChecked():
            return None
        q = self.vencimiento.date()
        return date(q.year(), q.month(), q.day())

    def validar(self):
        ok = True
        nombre = self.nombre.text().strip()
        if not nombre:
            self.error_campo("nombre", "El nombre es obligatorio")
            ok = False
        categoria = self.categoria.currentText().strip() or "General"
        if len(categoria) > 50:
            self.error_campo("categoria", "Máximo 50 caracteres")
            ok = False
        precio = _numero(self.precio.text())
        if self.precio.text().strip() == "":
            self.error_campo("precio_base", "El precio es obligatorio")
            ok = False
        elif precio is None or precio <= 0:
            self.error_campo("precio_base", "Ingresa un número mayor que 0")
            ok = False
        stock = _numero(self.stock.text(), entero=True)
        if self.stock.text().strip() == "":
            self.error_campo("stock", "Obligatorio")
            ok = False
        elif stock is None or stock < 0:
            self.error_campo("stock", "Entero igual o mayor que 0")
            ok = False
        maximo = _numero(self.stock_max.text(), entero=True)
        if self.stock_max.text().strip() == "":
            self.error_campo("stock_maximo", "Obligatorio")
            ok = False
        elif maximo is None or maximo <= 0:
            self.error_campo("stock_maximo", "Entero mayor que 0")
            ok = False
        fecha = self._fecha()
        original = self._producto.vencimiento if self._producto else None
        if fecha is not None and fecha < date.today() and fecha.isoformat() != original:
            self.error_campo("fecha_vencimiento", "La fecha ya pasó; elige una fecha futura")
            ok = False
        if not ok:
            return None

        venc = datetime(fecha.year, fecha.month, fecha.day) if fecha else None
        if self._producto is None:
            return ProductoIn(nombre=nombre, categoria=categoria, precio_base=precio, stock=stock,
                              stock_maximo=maximo, fecha_vencimiento=venc)
        p = self._producto
        cambios: dict = {}
        if nombre != p.nombre:
            cambios["nombre"] = nombre
        if categoria != p.categoria:
            cambios["categoria"] = categoria
        if abs(precio - p.precio_base) > 1e-9:
            cambios["precio_base"] = precio
        if stock != p.stock:
            cambios["stock"] = stock
        if maximo != p.stock_maximo:
            cambios["stock_maximo"] = maximo
        if (fecha.isoformat() if fecha else None) != p.vencimiento:
            cambios["fecha_vencimiento"] = venc
        if not cambios:
            self.error_general("No hay cambios que guardar")
            return None
        return ProductoUpdate(**cambios)

    def llamar(self, datos):
        api = self.ctx.api
        if self._producto is None:
            return api.crear_producto(datos)
        return api.actualizar_producto(self._producto.id, datos)


# ---------------------------------------------------------------------------
# vista
# ---------------------------------------------------------------------------
class InventoryView(c.VistaBase):
    def __init__(self, app_ctx, parent: QWidget | None = None):
        super().__init__(app_ctx, parent)
        self._filas: list[FilaInventario] = []
        self._visibles: list[FilaInventario] = []
        self._moneda = "$"
        self._negocio = "Mi Negocio"
        self._exportando = False
        self._dialogo: c.DialogoFormulario | None = None
        self._ultimo_reporte: Path | None = None

        lay = QVBoxLayout(self)
        lay.setContentsMargins(32, 28, 32, 28)
        lay.setSpacing(14)

        cab = QHBoxLayout()
        cab.addWidget(c.titulo_vista("Inventario de productos"))
        cab.addStretch(1)
        self.btn_agregar = QPushButton("Agregar producto", self)
        self.btn_agregar.setProperty("variant", "primary")
        self.btn_agregar.clicked.connect(self.agregar)
        cab.addWidget(self.btn_agregar)
        lay.addLayout(cab)

        filtros = QHBoxLayout()
        filtros.setSpacing(10)
        self.busqueda = QLineEdit(self)
        self.busqueda.setPlaceholderText("Buscar por nombre, categoría o ID")
        self.busqueda.setClearButtonEnabled(True)
        self.busqueda.setMinimumWidth(280)
        self.busqueda.textChanged.connect(self._aplicar_filtros)
        self.filtro_categoria = QComboBox(self)
        self.filtro_categoria.setMinimumWidth(190)
        self.filtro_categoria.addItem(TODAS)
        self.filtro_categoria.currentIndexChanged.connect(self._aplicar_filtros)
        self.lbl_conteo = QLabel("", self)
        self.lbl_conteo.setStyleSheet(f"color: {COLORES['texto_suave']}; font-size: 12px;")
        filtros.addWidget(self.busqueda, 2)
        filtros.addWidget(self.filtro_categoria, 1)
        filtros.addStretch(1)
        filtros.addWidget(self.lbl_conteo)
        lay.addLayout(filtros)

        # franja con el ultimo reporte exportado
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

        self.paginas = QStackedWidget(self)
        lay.addWidget(self.paginas, 1)
        self.tabla = TablaEstandar(COLUMNAS, self)
        self.tabla.setAccessibleName("Tabla de inventario")
        h = self.tabla.horizontalHeader()
        for col in range(len(COLUMNAS)):
            h.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(COL_NOMBRE, QHeaderView.ResizeMode.Stretch)
        h.setStretchLastSection(False)
        h.setSortIndicator(COL_ID, Qt.SortOrder.AscendingOrder)
        self.tabla.itemSelectionChanged.connect(self._actualizar_botones)
        self.tabla.itemDoubleClicked.connect(lambda *_: self.editar())
        self.paginas.addWidget(self.tabla)
        self.estado_vacio = EstadoVacio("∅", "Aún no hay productos",
                                        "Agrega el primer producto para empezar a controlar el inventario.",
                                        "Agregar producto", self)
        c.mostrar_estado(self.estado_vacio)
        self.estado_vacio.accion.connect(self.agregar)
        self.paginas.addWidget(self.estado_vacio)
        self.estado_sin_resultados = EstadoVacio("∅", "Sin coincidencias",
                                                 "Ningún producto coincide con la búsqueda o el filtro.",
                                                 "Limpiar filtros", self)
        c.mostrar_estado(self.estado_sin_resultados)
        self.estado_sin_resultados.accion.connect(self.limpiar_filtros)
        self.paginas.addWidget(self.estado_sin_resultados)
        self.estado_error = EstadoVacio.error_conexion(self)
        c.mostrar_estado(self.estado_error)
        self.estado_error.accion.connect(lambda: self.recargar())
        self.paginas.addWidget(self.estado_error)

        pie = QHBoxLayout()
        pie.setSpacing(8)
        self.btn_editar = QPushButton("Editar", self)
        self.btn_baja = QPushButton("Dar de baja", self)
        self.btn_baja.setProperty("variant", "danger")
        self.btn_actualizar = QPushButton("Actualizar", self)
        self.btn_excel = QPushButton("Exportar Excel", self)
        self.btn_pdf = QPushButton("Exportar PDF", self)
        self.btn_editar.clicked.connect(self.editar)
        self.btn_baja.clicked.connect(self.dar_de_baja)
        self.btn_actualizar.clicked.connect(lambda: self.recargar())
        self.btn_excel.clicked.connect(lambda: self.exportar("xlsx"))
        self.btn_pdf.clicked.connect(lambda: self.exportar("pdf"))
        pie.addWidget(self.btn_editar)
        pie.addWidget(self.btn_baja)
        pie.addStretch(1)
        pie.addWidget(self.btn_actualizar)
        pie.addWidget(self.btn_excel)
        pie.addWidget(self.btn_pdf)
        lay.addLayout(pie)
        self._actualizar_botones()

    # -- carga ----------------------------------------------------------------------------------------
    def recargar(self, silencioso: bool = False) -> None:
        api = self.ctx.api
        if api is None:
            return

        def trabajo():
            productos = api.listar_productos(True)
            alertas = api.alertas_riesgo()
            try:
                pub = api.config_publica()
                moneda, negocio = pub.moneda or "$", pub.nombre_negocio
            except Exception:  # noqa: BLE001
                moneda, negocio = "$", "Mi Negocio"
            riesgo = {i.producto_id: i for g in (alertas.critico, alertas.alto, alertas.medio) for i in g}
            filas = []
            for p in productos:
                r = riesgo.get(p.id)
                filas.append(FilaInventario(
                    p.id, p.nombre, p.categoria, p.precio_base,
                    r.precio_final if r else p.precio_base, r.descuento if r else 0.0,
                    p.stock, p.stock_maximo,
                    p.fecha_vencimiento.date().isoformat() if p.fecha_vencimiento else None,
                    r.nivel if r else "normal"))
            return filas, moneda, negocio

        self.consultar(trabajo, self._recibir, lambda e: self._error(e, silencioso), silencioso)

    def _error(self, exc: BaseException, silencioso: bool) -> None:
        if silencioso and self.cargada and self.paginas.currentIndex() != ERROR:
            return
        c.mostrar_estado(self.estado_error, "Sin conexión con el servidor" if isinstance(exc, ErrorConexion)
            else "No se pudo cargar el inventario", c.mensaje_api(exc))
        self.paginas.setCurrentIndex(ERROR)

    def _recibir(self, datos) -> None:
        self._filas, self._moneda, self._negocio = datos
        actual = self.filtro_categoria.currentText()
        cats = sorted({f.categoria for f in self._filas}, key=str.casefold)
        self.filtro_categoria.blockSignals(True)
        self.filtro_categoria.clear()
        self.filtro_categoria.addItems([TODAS, *cats])
        i = self.filtro_categoria.findText(actual)
        self.filtro_categoria.setCurrentIndex(i if i >= 0 else 0)
        self.filtro_categoria.blockSignals(False)
        self._aplicar_filtros()

    # -- filtros y tabla --------------------------------------------------------------------------------
    def limpiar_filtros(self) -> None:
        self.busqueda.clear()
        self.filtro_categoria.setCurrentIndex(0)

    def _aplicar_filtros(self, *_):
        texto = self.busqueda.text().strip().casefold()
        cat = self.filtro_categoria.currentText()
        self._visibles = [
            f for f in self._filas
            if (cat in (TODAS, "") or f.categoria == cat)
            and (not texto or texto in f.nombre.casefold() or texto in f.categoria.casefold()
                 or texto == str(f.id))]
        self._pintar_tabla()

    def _pintar_tabla(self) -> None:
        sel = self.producto_seleccionado()
        sel_id = sel.id if sel else None
        m = self._moneda
        filas = [[f.id, f.nombre, f.categoria, f.precio_base, f.precio_final, f.stock, f.stock_maximo,
                  f.vencimiento or "Sin vencimiento", _RANGO_NIVEL.get(f.nivel, 0)]
                 for f in self._visibles]
        self.tabla.blockSignals(True)
        self.tabla.set_filas(filas, formateadores={
            COL_ID: str, COL_BASE: lambda v: fmt_moneda(v, m), COL_FINAL: lambda v: fmt_moneda(v, m),
            COL_RIESGO: lambda v: ETIQUETA_NIVEL[{3: "critico", 2: "alto", 1: "medio", 0: "normal"}[v]]})
        por_id = {f.id: f for f in self._visibles}
        fila_sel = -1
        for r in range(self.tabla.rowCount()):
            f = por_id[int(self.tabla.texto(r, COL_ID))]
            txt, fondo = COLOR_NIVEL.get(f.nivel, COLOR_NIVEL["normal"])
            it = self.tabla.item(r, COL_RIESGO)
            it.setForeground(QColor(txt))
            it.setBackground(QColor(fondo))
            it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            fuente = it.font()
            fuente.setWeight(QFont.Weight.DemiBold)
            it.setFont(fuente)
            if f.descuento > 0:
                p = self.tabla.item(r, COL_FINAL)
                p.setForeground(QColor(COLORES["exito_texto"]))
                p.setToolTip(f"Descuento de {f.descuento:g}% sobre {fmt_moneda(f.precio_base, m)}")
            self.tabla.item(r, COL_VENC).setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if f.id == sel_id:
                fila_sel = r
        for col in (COL_VENC, COL_RIESGO):
            hi = self.tabla.horizontalHeaderItem(col)
            if hi is not None:
                hi.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.tabla.blockSignals(False)
        if fila_sel >= 0:
            self.tabla.selectRow(fila_sel)
        else:
            self.tabla.clearSelection()
        total, vis = len(self._filas), len(self._visibles)
        self.lbl_conteo.setText(f"{vis} de {total} productos" if vis != total else f"{total} productos")
        self.paginas.setCurrentIndex(
            VACIO if total == 0 else TABLA if vis else SIN_RESULTADOS)
        self._actualizar_botones()

    def producto_seleccionado(self) -> FilaInventario | None:
        fila = self.tabla.currentRow()
        if fila < 0 or not self.tabla.selectionModel().hasSelection():
            return None
        it = self.tabla.item(fila, COL_ID)
        if it is None:
            return None
        pid = int(it.text())
        return next((f for f in self._filas if f.id == pid), None)

    def seleccionar(self, producto_id: int) -> bool:
        for r in range(self.tabla.rowCount()):
            if int(self.tabla.texto(r, COL_ID)) == producto_id:
                self.tabla.selectRow(r)
                return True
        return False

    def _actualizar_botones(self) -> None:
        hay = self.producto_seleccionado() is not None
        self.btn_editar.setEnabled(hay)
        self.btn_baja.setEnabled(hay)
        hay_datos = bool(self._visibles) and not self._exportando
        self.btn_excel.setEnabled(hay_datos)
        self.btn_pdf.setEnabled(hay_datos)

    # -- alta / edicion ------------------------------------------------------------------------------------
    def agregar(self) -> None:
        self._abrir_dialogo(None)

    def editar(self) -> None:
        p = self.producto_seleccionado()
        if p is not None:
            self._abrir_dialogo(p)

    def _abrir_dialogo(self, producto: FilaInventario | None) -> None:
        cats = sorted({f.categoria for f in self._filas})
        dlg = ProductoDialog(self.ctx, producto, cats, self.window())
        self._dialogo = dlg
        dlg.guardado.connect(lambda p, nuevo=producto is None: self._guardado(p, nuevo))
        dlg.finished.connect(lambda _=0: setattr(self, "_dialogo", None))
        dlg.open()

    def _guardado(self, p, nuevo: bool) -> None:
        self.toast(f"Producto «{p.nombre}» {'creado' if nuevo else 'actualizado'}", "exito")
        self.recargar(silencioso=True)

    # -- baja logica (RNF-04) --------------------------------------------------------------------------------
    def dar_de_baja(self) -> None:
        p = self.producto_seleccionado()
        api = self.ctx.api
        if p is None or api is None:
            return
        if not c.confirmar(
                self.window(), "Dar de baja producto",
                f"¿Dar de baja «{p.nombre}»?\n\nDejará de mostrarse en el inventario y de venderse. "
                "El historial de facturas se conserva.", "Dar de baja", peligro=True):
            return
        self.ctx.ejecutar(lambda: api.eliminar_producto(p.id),
                          lambda _: self._baja_ok(p), self._baja_error, self)

    def _baja_ok(self, p: FilaInventario) -> None:
        self.toast(f"Producto «{p.nombre}» dado de baja", "exito")
        self.recargar(silencioso=True)

    def _baja_error(self, exc: BaseException) -> None:
        self.toast(c.mensaje_api(exc), "error", 6000)
        self.recargar(silencioso=True)

    # -- exportacion ------------------------------------------------------------------------------------------
    def exportar(self, formato: str) -> None:
        """Genera el reporte con las filas visibles (respeta busqueda y categoria), fuera del hilo GUI."""
        if self._exportando:
            return
        filas, moneda, negocio = list(self._visibles), self._moneda, self._negocio
        if not filas:
            self.toast("No hay productos para exportar", "aviso")
            return
        funcion = exportar_excel if formato == "xlsx" else exportar_pdf
        self._exportando = True
        boton = self.btn_excel if formato == "xlsx" else self.btn_pdf
        texto_original = boton.text()
        boton.setText("Exportando…")
        self._actualizar_botones()

        def fin():
            self._exportando = False
            boton.setText(texto_original)
            self._actualizar_botones()

        def ok(ruta: Path):
            fin()
            self._ultimo_reporte = ruta
            self.lbl_reporte.setText(f"Reporte guardado: {ruta.name} ({len(filas)} productos)")
            self.lbl_reporte.setToolTip(str(ruta))
            self.barra_reporte.show()
            self.toast(f"{'Excel' if formato == 'xlsx' else 'PDF'} guardado: {ruta.name}", "exito", 5000)

        def err(exc: BaseException):
            fin()
            self.toast(f"No se pudo exportar: {exc}", "error", 6000)

        self.ctx.ejecutar(lambda: funcion(filas, moneda, negocio), ok, err, self)

    def _abrir(self, archivo: bool) -> None:
        if self._ultimo_reporte is not None:
            c.abrir_ruta(self._ultimo_reporte if archivo else self._ultimo_reporte.parent)
