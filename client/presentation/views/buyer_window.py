"""Ventana del comprador: catalogo de ofertas + carrito + pago + factura (RF-12, RF-15..RF-21).

Todo el acceso a datos es por `app_ctx.api` dentro de `app_ctx.ejecutar` (hilo aparte). Los
eventos WS y el sondeo refrescan SIN contar como actividad del usuario; las acciones del usuario
(filtrar, agregar, pagar...) llaman a `app_ctx.marcar_actividad_vista()`."""
from __future__ import annotations

import unicodedata

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox, QFrame, QHBoxLayout, QLabel, QLineEdit, QMainWindow, QMessageBox, QPushButton,
    QScrollArea, QStackedWidget, QVBoxLayout, QWidget,
)

from client.application.mensajes import texto_error
from client.infrastructure.api_client import ApiError
from shared.schemas import ConfigPublicaOut, ItemRiesgo

from ..styles.theme import COLOR_NIVEL, COLORES, fmt_moneda
from ..widgets import BadgeNivel, Cargando, EstadoVacio, Toast
from ..widgets.tarjetas import normalizar_nivel
from .barra_estado import instalar_barra_estado
from .carrito import PanelCarrito
from .carrito_modelo import TIPO_NO_DISPONIBLE, TIPO_RECUPERADO, Cambio, Carrito
from .factura_view import FacturaDialog
from .pago_dialog import PagoDialog

TODAS = "Todas las categorías"
REFRESCO_MS = 300          # agrupa rafagas de eventos WS en una sola recarga


def _plano(texto: str) -> str:
    n = unicodedata.normalize("NFD", texto or "")
    return "".join(c for c in n if not unicodedata.combining(c)).casefold()


class TarjetaOferta(QFrame):
    """Tarjeta de un producto en oferta: borde del color del nivel, badge de descuento, precios."""

    agregar = pyqtSignal(int)

    def __init__(self, oferta: ItemRiesgo, moneda: str = "$", parent=None):
        super().__init__(parent)
        self.oferta = oferta
        self.producto_id = oferta.producto_id
        nivel = normalizar_nivel(oferta.nivel)
        acento = COLOR_NIVEL[nivel][0]
        self.setObjectName("tarjetaOferta")
        self.setProperty("nivel", nivel)
        self.setStyleSheet(
            f"QFrame#tarjetaOferta {{ background: {COLORES['superficie']};"
            f" border: 1px solid {acento}; border-left: 5px solid {acento}; border-radius: 8px; }}")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(16, 12, 16, 12)
        lay.setSpacing(16)

        info = QVBoxLayout()
        info.setSpacing(3)
        fila_nombre = QHBoxLayout()
        fila_nombre.setSpacing(8)
        self.lbl_nombre = QLabel(oferta.nombre)
        self.lbl_nombre.setStyleSheet(f"font-size: 15px; font-weight: 700; color: {COLORES['texto']};"
                                      " border: none; background: transparent;")
        self.badge_nivel = BadgeNivel(nivel)
        fila_nombre.addWidget(self.lbl_nombre)
        fila_nombre.addWidget(self.badge_nivel)
        fila_nombre.addStretch(1)
        info.addLayout(fila_nombre)
        self.lbl_detalle = QLabel()
        self.lbl_detalle.setTextFormat(Qt.TextFormat.RichText)
        self.lbl_detalle.setStyleSheet(f"font-size: 12px; color: {COLORES['texto_suave']};"
                                       " border: none; background: transparent;")
        info.addWidget(self.lbl_detalle)
        self.lbl_motivo = QLabel(oferta.motivo)
        self.lbl_motivo.setWordWrap(True)
        self.lbl_motivo.setStyleSheet(f"font-size: 12px; color: {COLORES['texto_suave']};"
                                      " border: none; background: transparent;")
        info.addWidget(self.lbl_motivo)
        self.lbl_en_carrito = QLabel("")
        self.lbl_en_carrito.setStyleSheet(f"font-size: 11px; font-weight: 700; color: {COLORES['primario_texto']};"
                                          " border: none; background: transparent;")
        self.lbl_en_carrito.setVisible(False)
        info.addWidget(self.lbl_en_carrito)
        info.addStretch(1)

        der = QVBoxLayout()
        der.setSpacing(4)
        der.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.lbl_descuento = QLabel(f"-{oferta.descuento:g}%")
        self.lbl_descuento.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_descuento.setStyleSheet(
            f"color: {COLORES['descuento_texto']}; background: {COLORES['primario_fondo']};"
            " font-size: 12px; font-weight: 700; padding: 2px 10px; border-radius: 9px; border: none;")
        self.lbl_original = QLabel(fmt_moneda(oferta.precio_original, moneda))
        self.lbl_original.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.lbl_original.setStyleSheet(f"font-size: 12px; color: {COLORES['texto_tenue']};"
                                        " text-decoration: line-through; border: none; background: transparent;")
        self.lbl_final = QLabel(fmt_moneda(oferta.precio_final, moneda))
        self.lbl_final.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.lbl_final.setStyleSheet(f"font-size: 18px; font-weight: 700; color: {COLORES['exito_texto']};"
                                     " border: none; background: transparent;")
        self.btn_agregar = QPushButton("Agregar al carrito")
        self.btn_agregar.setProperty("variant", "primary")
        self.btn_agregar.setMinimumHeight(34)
        self.btn_agregar.setMinimumWidth(150)
        self.btn_agregar.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_agregar.setAccessibleName(f"Agregar {oferta.nombre} al carrito")
        self.btn_agregar.clicked.connect(lambda: self.agregar.emit(self.producto_id))
        der.addWidget(self.lbl_descuento, 0, Qt.AlignmentFlag.AlignRight)
        der.addWidget(self.lbl_original)
        der.addWidget(self.lbl_final)
        der.addWidget(self.btn_agregar)
        lay.addLayout(info, 3)
        lay.addLayout(der, 2)
        self.stock = oferta.stock
        self.set_stock(oferta.stock)

    def set_stock(self, stock: int) -> None:
        self.stock = max(0, int(stock))
        o = self.oferta
        categoria = f"{o.categoria}  ·  " if o.categoria else ""
        self.lbl_detalle.setText(f"{categoria}Stock: <b>{self.stock}</b> "
                                 f"unidad{'es' if self.stock != 1 else ''}")
        agotado = self.stock <= 0
        self.btn_agregar.setEnabled(not agotado)
        self.btn_agregar.setText("Sin stock" if agotado else "Agregar al carrito")

    def set_en_carrito(self, n: int) -> None:
        self.lbl_en_carrito.setText(f"En tu carrito: {n}")
        self.lbl_en_carrito.setVisible(n > 0)


class BuyerWindow(QMainWindow):
    def __init__(self, app_ctx):
        super().__init__()
        self.ctx = app_ctx
        self.carrito = Carrito()
        self.ofertas: list[ItemRiesgo] = []
        self.config = ConfigPublicaOut(moneda="$", nombre_negocio="")
        self.tarjetas: dict[int, TarjetaOferta] = {}
        self.dialogo_pago: PagoDialog | None = None
        self.dialogo_factura: FacturaDialog | None = None
        self._gen = 0
        self._firma: list | None = None
        self._cargado = False
        self._cargas_en_curso = 0

        s = app_ctx.sesion
        self.setWindowTitle("Tienda — Productos en oferta")
        self.setMinimumSize(1060, 680)
        self.resize(1180, 760)

        self.barra = instalar_barra_estado(self, app_ctx)
        self._adaptar_barra(s.nombre if s else "")

        central = QWidget()
        self.setCentralWidget(central)
        cuerpo = QHBoxLayout(central)
        cuerpo.setContentsMargins(0, 0, 0, 0)
        cuerpo.setSpacing(0)
        cuerpo.addWidget(self._panel_catalogo(), 6)
        self.panel_carrito = PanelCarrito(self.carrito)
        self.panel_carrito.aumentar.connect(lambda p: self._cambiar_cantidad(p, +1))
        self.panel_carrito.disminuir.connect(lambda p: self._cambiar_cantidad(p, -1))
        self.panel_carrito.quitar.connect(self._quitar)
        self.panel_carrito.vaciar_pedido.connect(self._pedir_vaciar)
        self.panel_carrito.ir_al_pago.connect(self._ir_al_pago)
        cuerpo.addWidget(self.panel_carrito, 3)

        self._t_refresco = QTimer(self)
        self._t_refresco.setSingleShot(True)
        self._t_refresco.setInterval(REFRESCO_MS)
        self._t_refresco.timeout.connect(lambda: self.cargar(silencioso=True))

        app_ctx.evento_ws.connect(self._al_evento)
        app_ctx.sondeo.connect(self._programar_refresco)
        self._cargar_config()
        self.cargar()

    # -- construccion ---------------------------------------------------------------------
    def _adaptar_barra(self, nombre: str) -> None:
        b = self.barra
        marca = QLabel("Inventario App")
        marca.setStyleSheet(f"font-size: 15px; font-weight: 700; color: {COLORES['primario_texto']};")
        b.layout().insertWidget(0, marca)
        b.layout().insertSpacing(1, 16)
        b.lbl_usuario.setText(f"Hola, {nombre}")
        b.btn_salir.clicked.disconnect()                # el cierre pide confirmacion
        b.btn_salir.clicked.connect(self._pedir_cerrar_sesion)

    def _panel_catalogo(self) -> QWidget:
        panel = QWidget()
        panel.setObjectName("panelCatalogo")
        panel.setStyleSheet(f"QWidget#panelCatalogo {{ background: {COLORES['fondo']}; }}")
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(28, 22, 16, 22)
        lay.setSpacing(12)

        cab = QHBoxLayout()
        titulo = QLabel("Productos en oferta")
        titulo.setStyleSheet(f"font-size: 18px; font-weight: 700; color: {COLORES['texto']};")
        self.lbl_conteo = QLabel("")
        self.lbl_conteo.setStyleSheet(f"font-size: 12px; color: {COLORES['texto_suave']};")
        cab.addWidget(titulo)
        cab.addStretch(1)
        cab.addWidget(self.lbl_conteo)
        lay.addLayout(cab)

        filtros = QHBoxLayout()
        filtros.setSpacing(8)
        self.buscador = QLineEdit()
        self.buscador.setPlaceholderText("Buscar producto…")
        self.buscador.setClearButtonEnabled(True)
        self.buscador.setAccessibleName("Buscar producto")
        self.buscador.textChanged.connect(lambda _: self._reconstruir())
        self.filtro_categoria = QComboBox()
        self.filtro_categoria.setAccessibleName("Filtrar por categoría")
        self.filtro_categoria.setMinimumWidth(200)
        self.filtro_categoria.addItem(TODAS)
        self.filtro_categoria.currentIndexChanged.connect(self._al_cambiar_categoria)
        self.btn_actualizar = QPushButton("Actualizar")
        self.btn_actualizar.clicked.connect(self._actualizar_manual)
        filtros.addWidget(self.buscador, 1)
        filtros.addWidget(self.filtro_categoria)
        filtros.addWidget(self.btn_actualizar)
        lay.addLayout(filtros)

        self.pila = QStackedWidget()
        self.pila.setStyleSheet("QStackedWidget { background: transparent; }")
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        self._lista = QWidget()
        self._lista.setObjectName("listaOfertas")
        self._lista.setStyleSheet("QWidget#listaOfertas { background: transparent; }")
        self._lista_lay = QVBoxLayout(self._lista)
        self._lista_lay.setContentsMargins(0, 0, 8, 0)
        self._lista_lay.setSpacing(10)
        self._scroll.setWidget(self._lista)
        self.vista_vacia = EstadoVacio("∅", "No hay productos en oferta",
                                       "Vuelve más tarde: aquí aparecerán los productos con descuento.")
        self.vista_sin_resultados = EstadoVacio("∅", "Sin coincidencias",
                                                "Ningún producto coincide con tu búsqueda o categoría.",
                                                "Limpiar filtros")
        self.vista_sin_resultados.accion.connect(self.limpiar_filtros)
        self.vista_error = EstadoVacio.error_conexion()
        self.vista_error.accion.connect(self.cargar)
        self._paginas = {"lista": self._scroll, "vacio": self.vista_vacia,
                         "sin_resultados": self.vista_sin_resultados, "error": self.vista_error,
                         "cargando": QWidget()}
        for w in self._paginas.values():
            self.pila.addWidget(w)
        self.cargando = Cargando(self.pila, "Cargando ofertas…")
        lay.addWidget(self.pila, 1)
        self.pila.setCurrentWidget(self._paginas["cargando"])
        return panel

    # -- utilidades -----------------------------------------------------------------------
    @property
    def estado(self) -> str:
        actual = self.pila.currentWidget()
        for nombre, w in self._paginas.items():
            if w is actual:
                return nombre
        return ""

    @property
    def moneda(self) -> str:
        return self.config.moneda or "$"

    def _actividad(self) -> None:
        self.ctx.marcar_actividad_vista()

    def _confirmar(self, titulo: str, texto: str) -> bool:
        caja = QMessageBox(QMessageBox.Icon.Question, titulo, texto, parent=self)
        si = caja.addButton("Sí", QMessageBox.ButtonRole.AcceptRole)
        no = caja.addButton("No", QMessageBox.ButtonRole.RejectRole)
        caja.setDefaultButton(no)
        caja.exec()
        return caja.clickedButton() is si

    def _toast(self, texto: str, tipo: str = "aviso", ms: int = 4500) -> None:
        Toast.mostrar(self, texto, tipo, ms)

    def _avisar_cambios(self, cambios: list[Cambio]) -> None:
        for c in cambios[:3]:
            self._toast(c.mensaje, "error" if c.tipo == TIPO_NO_DISPONIBLE else
                        ("info" if c.tipo == TIPO_RECUPERADO else "aviso"), 6000)
        if len(cambios) > 3:
            self._toast(f"Hay {len(cambios) - 3} cambios más en tu carrito.", "aviso", 6000)

    # -- carga de datos -------------------------------------------------------------------
    def _cargar_config(self) -> None:
        api = self.ctx.api
        if api is None:
            return

        def ok(cfg: ConfigPublicaOut) -> None:
            cambio = cfg.moneda != self.config.moneda
            self.config = cfg
            self.panel_carrito.configurar(cfg.moneda, cfg.iva_pct)
            if cambio and self._cargado:
                self._reconstruir(forzar=True)
        self.ctx.ejecutar(api.config_publica, ok, lambda e: None, self)

    def cargar(self, silencioso: bool = False) -> None:
        """GET /ofertas en un worker. `silencioso`: refresco automatico (sin overlay ni error)."""
        api = self.ctx.api
        if api is None:
            return
        self._gen += 1
        gen = self._gen
        if not silencioso and not self._cargado:
            self.pila.setCurrentWidget(self._paginas["cargando"])
            self.cargando.iniciar()
        self.ctx.ejecutar(api.listar_ofertas, lambda o: self._ofertas_ok(gen, o),
                          lambda e: self._ofertas_error(gen, e, silencioso), self)

    def _programar_refresco(self, *_) -> None:
        self._t_refresco.start()

    def _actualizar_manual(self) -> None:
        self._actividad()
        self.cargar(silencioso=self._cargado)

    def _ofertas_ok(self, gen: int, ofertas: list[ItemRiesgo]) -> None:
        if gen != self._gen:
            return                                       # llego una respuesta mas reciente
        self.cargando.detener()
        self._cargado = True
        self.ofertas = list(ofertas)
        self._actualizar_categorias()
        self._avisar_cambios(self.carrito.sincronizar(self.ofertas))
        self.panel_carrito.refrescar()
        self._reconstruir()

    def _ofertas_error(self, gen: int, exc: BaseException, silencioso: bool) -> None:
        if gen != self._gen:
            return
        self.cargando.detener()
        if self._cargado:
            if not silencioso:
                self._toast(texto_error(exc), "error")
            return                                       # se conserva lo ultimo conocido
        self.pila.setCurrentWidget(self._paginas["error"])
        self.lbl_conteo.setText("")

    # -- filtros --------------------------------------------------------------------------
    def _actualizar_categorias(self) -> None:
        actual = self.filtro_categoria.currentText()
        cats = sorted({o.categoria for o in self.ofertas if o.categoria}, key=_plano)
        self.filtro_categoria.blockSignals(True)
        self.filtro_categoria.clear()
        self.filtro_categoria.addItem(TODAS)
        self.filtro_categoria.addItems(cats)
        i = self.filtro_categoria.findText(actual)
        self.filtro_categoria.setCurrentIndex(max(0, i))
        self.filtro_categoria.blockSignals(False)

    def _al_cambiar_categoria(self, _=None) -> None:
        self._actividad()                                # cambio de vista del usuario
        self._reconstruir()

    def limpiar_filtros(self) -> None:
        self._actividad()
        self.buscador.clear()
        self.filtro_categoria.setCurrentIndex(0)

    def visibles(self) -> list[ItemRiesgo]:
        cat = self.filtro_categoria.currentText()
        q = _plano(self.buscador.text().strip())
        return [o for o in self.ofertas
                if (cat == TODAS or o.categoria == cat)
                and (not q or q in _plano(o.nombre) or q in _plano(o.categoria))]

    @property
    def filtrando(self) -> bool:
        return bool(self.buscador.text().strip()) or self.filtro_categoria.currentIndex() > 0

    # -- catalogo -------------------------------------------------------------------------
    def _reconstruir(self, forzar: bool = False) -> None:
        if not self._cargado:
            return
        vis = self.visibles()
        n, total = len(vis), len(self.ofertas)
        if self.filtrando:
            self.lbl_conteo.setText(f"{n} de {total} producto{'s' if total != 1 else ''}")
        else:
            self.lbl_conteo.setText(f"{total} producto{'s' if total != 1 else ''}")
        firma = [o.model_dump(mode="json") for o in vis]
        if not self.ofertas:
            self.pila.setCurrentWidget(self._paginas["vacio"])
        elif not vis:
            self.pila.setCurrentWidget(self._paginas["sin_resultados"])
        else:
            self.pila.setCurrentWidget(self._paginas["lista"])
        if not forzar and firma == self._firma and (not vis or self.tarjetas):
            self._sincronizar_en_carrito()
            return
        self._firma = firma
        pos = self._scroll.verticalScrollBar().value()
        while self._lista_lay.count():
            it = self._lista_lay.takeAt(0)
            w = it.widget()
            if w is not None:
                w.hide()
                w.deleteLater()
        self.tarjetas.clear()
        for o in vis:
            t = TarjetaOferta(o, self.moneda)
            t.agregar.connect(self._agregar)
            self.tarjetas[o.producto_id] = t
            self._lista_lay.addWidget(t)
        self._lista_lay.addStretch(1)
        self._sincronizar_en_carrito()
        self._scroll.verticalScrollBar().setValue(pos)

    def _sincronizar_en_carrito(self) -> None:
        for pid, t in self.tarjetas.items():
            t.set_en_carrito(self.carrito.cantidad_de(pid))

    # -- acciones del carrito -------------------------------------------------------------
    def _oferta(self, pid: int) -> ItemRiesgo | None:
        return next((o for o in self.ofertas if o.producto_id == pid), None)

    def _agregar(self, pid: int) -> None:
        self._actividad()
        o = self._oferta(pid)
        if o is None:
            return
        r = self.carrito.agregar(o)
        if not r.ok:
            self._toast(r.mensaje, "aviso")
        self.panel_carrito.refrescar()
        self._sincronizar_en_carrito()

    def _cambiar_cantidad(self, pid: int, delta: int) -> None:
        self._actividad()
        r = self.carrito.cambiar(pid, delta)
        if not r.ok:
            self._toast(r.mensaje, "aviso")
        self.panel_carrito.refrescar()
        self._sincronizar_en_carrito()

    def _quitar(self, pid: int) -> None:
        self._actividad()
        self.carrito.quitar(pid)
        self.panel_carrito.refrescar()
        self._sincronizar_en_carrito()

    def _pedir_vaciar(self) -> None:
        self._actividad()
        if not len(self.carrito):
            return
        if self._confirmar("Vaciar carrito", "¿Eliminar todos los productos del carrito?"):
            self.carrito.vaciar()
            self.panel_carrito.refrescar()
            self._sincronizar_en_carrito()

    # -- eventos del servidor (no cuentan como actividad) ---------------------------------
    def _al_evento(self, nombre: str, payload: dict) -> None:
        if nombre == "stock_actualizado":
            self._aplicar_stock(payload)
            self._programar_refresco()
        elif nombre == "descuento_cambiado":
            self._programar_refresco()
        elif nombre == "config_cambiada":
            self._cargar_config()
            self._programar_refresco()

    def _aplicar_stock(self, payload: dict) -> None:
        try:
            pid, stock = int(payload["producto_id"]), int(payload["stock"])
        except (KeyError, TypeError, ValueError):
            return
        activo = payload.get("activo", True)
        for i, o in enumerate(self.ofertas):
            if o.producto_id == pid:
                self.ofertas[i] = o.model_copy(update={"stock": stock})
        t = self.tarjetas.get(pid)
        if t is not None:
            t.set_stock(stock)
        if pid in self.carrito:
            self._avisar_cambios(self.carrito.aplicar_stock(pid, stock, bool(activo)))
            self.panel_carrito.refrescar()

    # -- pago y factura -------------------------------------------------------------------
    def _ir_al_pago(self) -> None:
        self._actividad()
        if not len(self.carrito) or self.dialogo_pago is not None:
            return
        if self.carrito.hay_problemas:
            self._toast("Hay productos que ya no están disponibles. Quítalos del carrito para continuar.",
                        "error", 6000)
            return
        self.carrito.reconocer()
        self.panel_carrito.refrescar()
        dlg = PagoDialog(self.ctx, self.carrito.snapshot(), self.moneda, self.config.iva_pct, self)
        dlg.compra_exitosa.connect(self._compra_ok)
        dlg.pedido_rechazado.connect(self._compra_rechazada)
        dlg.finished.connect(self._pago_cerrado)
        self.dialogo_pago = dlg
        dlg.open()

    def _pago_cerrado(self, _=0) -> None:
        d, self.dialogo_pago = self.dialogo_pago, None
        if d is not None:
            d.deleteLater()

    def _compra_ok(self, factura) -> None:
        self.carrito.vaciar()
        self.panel_carrito.refrescar()
        self._sincronizar_en_carrito()
        self.cargar(silencioso=True)                     # el stock ya cambio en el servidor
        dlg = FacturaDialog(self.ctx, factura, self.config.iva_pct, self)
        dlg.finished.connect(self._factura_cerrada)
        self.dialogo_factura = dlg
        dlg.open()

    def _factura_cerrada(self, _=0) -> None:
        d, self.dialogo_factura = self.dialogo_factura, None
        self._actividad()
        if d is not None:
            d.deleteLater()
        self.carrito.vaciar()
        self.panel_carrito.refrescar()
        self.cargar(silencioso=True)

    def _compra_rechazada(self, exc: ApiError) -> None:
        """409 al comprar: ajustar el carrito, avisar con detalle y refrescar el catalogo."""
        det = exc.detalle or {}
        pid = det.get("producto_id")
        cambios = self.carrito.rechazo_servidor(pid if isinstance(pid, int) else None, exc.codigo,
                                                det.get("disponible"))
        extra = ""
        if exc.codigo == "STOCK_INSUFICIENTE" and "disponible" in det:
            extra = f" Disponible: {det['disponible']}, pedido: {det.get('solicitado', '?')}."
        self._toast((exc.mensaje or texto_error(exc)) + "." + extra
                    + " Revisa tu carrito.", "error", 8000)
        self._avisar_cambios(cambios)
        self.panel_carrito.refrescar()
        self._sincronizar_en_carrito()
        self.cargar(silencioso=True)

    # -- sesion ---------------------------------------------------------------------------
    def _pedir_cerrar_sesion(self) -> None:
        self._actividad()
        texto = "¿Deseas cerrar sesión?"
        if len(self.carrito):
            texto += " Se perderá el contenido de tu carrito."
        if self._confirmar("Cerrar sesión", texto):
            self.ctx.cerrar_sesion()
