"""Ventana del administrador: navegacion lateral + barra de estado + vistas.

Contrato con `Aplicacion` (app_ctx): senales `evento_ws` y `sondeo` refrescan datos SIN contar como
actividad; el cambio de vista por el usuario llama a `marcar_actividad_vista()`."""
from __future__ import annotations

from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QMainWindow, QPushButton, QStackedWidget, QVBoxLayout, QWidget,
)

from ..styles.theme import COLORES
from ..widgets import Toast
from . import _comunes as c
from .alerts_view import AlertsView
from .barra_estado import instalar_barra_estado
from .config_view import ConfigView
from .dashboard import DashboardView
from .inventory_view import InventoryView
from .usuarios_view import UsuariosView

#: (clave, etiqueta, clase)
VISTAS = (
    ("dashboard", "Dashboard", DashboardView),
    ("inventario", "Inventario", InventoryView),
    ("alertas", "Alertas", AlertsView),
    ("usuarios", "Usuarios", UsuariosView),
    ("configuracion", "Configuración", ConfigView),
)
_DATOS_PRODUCTOS = ("dashboard", "inventario", "alertas")
_EVENTOS = {
    "stock_actualizado": _DATOS_PRODUCTOS,
    "descuento_cambiado": _DATOS_PRODUCTOS,
    "productos_retirados": _DATOS_PRODUCTOS,
    "config_cambiada": (*_DATOS_PRODUCTOS, "configuracion"),
}
_SONDEO = (*_DATOS_PRODUCTOS, "usuarios", "configuracion")
MAX_NOMBRES_AVISO = 5
DEBOUNCE_MS = 250


def texto_retirados(nombres: list[str]) -> str:
    nombres = [str(n) for n in nombres if str(n).strip()]
    if not nombres:
        return "Se retiraron productos vencidos del inventario"
    vistos = ", ".join(nombres[:MAX_NOMBRES_AVISO])
    extra = len(nombres) - MAX_NOMBRES_AVISO
    cola = f" y {extra} más" if extra > 0 else ""
    cabecera = "Producto retirado por vencimiento" if len(nombres) == 1 else \
        f"{len(nombres)} productos retirados por vencimiento"
    return f"{cabecera}: {vistos}{cola}"


class MainWindow(QMainWindow):
    def __init__(self, app_ctx):
        super().__init__()
        self.ctx = app_ctx
        self.setWindowTitle("Inventario App — Administrador")
        self.setMinimumSize(1100, 700)
        self.resize(1240, 780)
        self.barra = instalar_barra_estado(self, app_ctx)
        # el boton de la barra pide confirmacion antes de cerrar sesion
        self.barra.btn_salir.clicked.disconnect()
        self.barra.btn_salir.clicked.connect(self.pedir_cerrar_sesion)

        central = QWidget(self)
        self.setCentralWidget(central)
        central.setFocusPolicy(Qt.FocusPolicy.ClickFocus)    # el foco inicial no cae en "Cerrar sesión"
        central.setFocus()
        raiz = QHBoxLayout(central)
        raiz.setContentsMargins(0, 0, 0, 0)
        raiz.setSpacing(0)

        self.botones: dict[str, QPushButton] = {}
        raiz.addWidget(self._crear_menu())
        self.contenido = QStackedWidget(central)
        self.contenido.setStyleSheet(f"QStackedWidget {{ background: {COLORES['fondo']}; }}")
        raiz.addWidget(self.contenido, 1)

        self.vistas: dict[str, c.VistaBase] = {}
        for clave, _etq, clase in VISTAS:
            v = clase(app_ctx)
            self.vistas[clave] = v
            self.contenido.addWidget(v)

        self._pendientes: set[str] = set()
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(DEBOUNCE_MS)
        self._debounce.timeout.connect(self._refrescar_pendientes)

        app_ctx.evento_ws.connect(self._al_evento)
        app_ctx.sondeo.connect(self._al_sondeo)
        self.setStyleSheet(self._estilo())
        self.ir_a("dashboard", por_usuario=False)

    # -- menu lateral -------------------------------------------------------------------------------
    def _crear_menu(self) -> QFrame:
        menu = QFrame(self)
        menu.setObjectName("menu")
        menu.setFixedWidth(210)
        lay = QVBoxLayout(menu)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        cab = QFrame(menu)
        cab.setObjectName("menu_cab")
        cab.setFixedHeight(64)
        cl = QVBoxLayout(cab)
        cl.setContentsMargins(20, 0, 20, 0)
        titulo = QLabel("Inventario App", cab)
        titulo.setObjectName("menu_titulo")
        sub = QLabel("Administración", cab)
        sub.setObjectName("menu_sub")
        cl.addStretch(1)
        cl.addWidget(titulo)
        cl.addWidget(sub)
        cl.addStretch(1)
        lay.addWidget(cab)
        lay.addSpacing(10)

        for clave, etiqueta, _clase in VISTAS:
            b = QPushButton(etiqueta, menu)
            b.setObjectName("nav_btn")
            b.setFixedHeight(44)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
            b.setAccessibleName(f"Ir a {etiqueta}")
            b.clicked.connect(lambda _=False, k=clave: self.ir_a(k))
            lay.addWidget(b)
            self.botones[clave] = b
        lay.addStretch(1)
        ver = QLabel("v1.0.0", menu)
        ver.setObjectName("menu_version")
        ver.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ver.setFixedHeight(28)
        lay.addWidget(ver)
        return menu

    def _estilo(self) -> str:
        C = COLORES
        return f"""
        #menu {{ background: {C['superficie']}; border-right: 1px solid {C['borde']}; }}
        #menu_cab {{ background: {C['superficie']}; border-bottom: 1px solid {C['borde']}; }}
        #menu_titulo {{ color: {C['primario_texto']}; font-size: 15px; font-weight: 700; }}
        #menu_sub {{ color: {C['texto_suave']}; font-size: 11px; }}
        #menu_version {{ color: {C['texto_suave']}; font-size: 11px; border-top: 1px solid {C['superficie_alt']}; }}
        #nav_btn {{ background: transparent; color: {C['texto_suave']}; font-size: 13px; font-weight: 500;
            text-align: left; padding-left: 20px; border: none; border-radius: 0; border-left: 3px solid transparent; }}
        #nav_btn:hover {{ background: {C['superficie_alt']}; color: {C['texto']}; }}
        #nav_btn[activo="true"] {{ background: {C['primario_fondo']}; color: {C['descuento_texto']};
            border-left: 3px solid {C['primario']}; font-weight: 600; }}
        #nav_btn:focus {{ border: 2px solid {C['primario']}; padding-left: 18px; }}
        """

    # -- navegacion -----------------------------------------------------------------------------------
    def vista_actual(self) -> str:
        return VISTAS[self.contenido.currentIndex()][0]

    def ir_a(self, clave: str, por_usuario: bool = True) -> None:
        indice = next(i for i, (k, _e, _c) in enumerate(VISTAS) if k == clave)
        if por_usuario:
            self.ctx.marcar_actividad_vista()
        self.contenido.setCurrentIndex(indice)
        for k, b in self.botones.items():
            b.setProperty("activo", k == clave)
            b.style().unpolish(b)
            b.style().polish(b)
        self.vistas[clave].recargar(silencioso=self.vistas[clave].cargada)

    # -- refresco por eventos ---------------------------------------------------------------------------
    def _al_evento(self, nombre: str, payload: dict) -> None:
        if nombre == "productos_retirados":
            self.avisar_retirados(payload.get("nombres") or [])
        destino = _EVENTOS.get(nombre)
        if destino:
            self._encolar(destino)

    def _al_sondeo(self) -> None:
        self._encolar(_SONDEO)

    def avisar_retirados(self, nombres: list[str]) -> None:
        """Aviso NO modal (Toast) con los productos retirados por vencimiento."""
        Toast.mostrar(self, texto_retirados(nombres), "aviso", 12_000)

    def _encolar(self, claves) -> None:
        self._pendientes.update(claves)
        if not self._debounce.isActive():
            self._debounce.start()

    def _refrescar_pendientes(self) -> None:
        pendientes, self._pendientes = self._pendientes, set()
        actual = self.vista_actual()
        for clave in pendientes:
            v = self.vistas[clave]
            if clave == actual or v.cargada:
                v.recargar(silencioso=True)

    # -- sesion ---------------------------------------------------------------------------------------------
    def pedir_cerrar_sesion(self) -> None:
        if c.confirmar(self, "Cerrar sesión", "¿Deseas cerrar sesión?", "Cerrar sesión"):
            self.ctx.cerrar_sesion()
