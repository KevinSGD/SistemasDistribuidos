"""Alertas: productos problematicos agrupados por severidad y escaneo manual."""
from __future__ import annotations


from PyQt6.QtWidgets import (
    QHBoxLayout, QLabel, QPushButton, QScrollArea, QStackedWidget, QVBoxLayout, QWidget,
)

from client.infrastructure.api_client import ErrorConexion

from ..styles.theme import COLORES
from ..widgets import BadgeNivel, EstadoVacio
from ._comunes import (
    FilaRiesgo, VistaBase, mensaje_api, moneda_publica, mostrar_estado, titulo_vista,
)

LISTA, VACIO, ERROR = 0, 1, 2
_NIVELES = (("critico", "Crítico"), ("alto", "Alto"), ("medio", "Medio"))


def _plural(n: int) -> str:
    return f"{n} producto" if n == 1 else f"{n} productos"


class AlertsView(VistaBase):
    def __init__(self, app_ctx, parent: QWidget | None = None):
        super().__init__(app_ctx, parent)
        self._escaneando = False
        lay = QVBoxLayout(self)
        lay.setContentsMargins(32, 28, 32, 28)
        lay.setSpacing(16)

        cabecera = QHBoxLayout()
        cabecera.addWidget(titulo_vista("Alertas de inventario"))
        cabecera.addStretch(1)
        self.btn_escanear = QPushButton("Escanear ahora", self)
        self.btn_escanear.setProperty("variant", "primary")
        self.btn_escanear.setToolTip("Evalúa el inventario ahora, aplica descuentos y retira vencidos")
        self.btn_escanear.clicked.connect(self.escanear)
        cabecera.addWidget(self.btn_escanear)
        lay.addLayout(cabecera)

        self.paginas = QStackedWidget(self)
        lay.addWidget(self.paginas, 1)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        self._contenedor = QWidget()
        self._contenedor.setStyleSheet("background: transparent;")
        self._lista = QVBoxLayout(self._contenedor)
        self._lista.setContentsMargins(0, 0, 8, 0)
        self._lista.setSpacing(8)
        self._lista.addStretch(1)
        scroll.setWidget(self._contenedor)
        self.paginas.addWidget(scroll)

        self.estado_vacio = EstadoVacio("✓", "Sin alertas activas",
                                        "El inventario está en orden.", None, self)
        mostrar_estado(self.estado_vacio)
        self.paginas.addWidget(self.estado_vacio)
        self.estado_error = EstadoVacio.error_conexion(self)
        mostrar_estado(self.estado_error)
        self.estado_error.accion.connect(lambda: self.recargar())
        self.paginas.addWidget(self.estado_error)

    # -- datos ---------------------------------------------------------------------------------------
    def recargar(self, silencioso: bool = False) -> None:
        api = self.ctx.api
        if api is None:
            return

        def trabajo():
            return api.alertas_riesgo(), moneda_publica(api)

        self.consultar(trabajo, self._pintar, lambda exc: self._error(exc, silencioso), silencioso)

    def _error(self, exc: BaseException, silencioso: bool) -> None:
        if silencioso and self.cargada and self.paginas.currentIndex() != ERROR:
            return
        mostrar_estado(self.estado_error, "Sin conexión con el servidor" if isinstance(exc, ErrorConexion)
            else "No se pudieron cargar las alertas", mensaje_api(exc))
        self.paginas.setCurrentIndex(ERROR)

    def _pintar(self, datos) -> None:
        alertas, moneda = datos
        while self._lista.count() > 1:
            it = self._lista.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        pos = 0
        for nivel, etiqueta in _NIVELES:
            items = getattr(alertas, nivel)
            if not items:
                continue
            self._lista.insertWidget(pos, self._encabezado(nivel, etiqueta, len(items)))
            pos += 1
            for item in items:
                self._lista.insertWidget(pos, FilaRiesgo(item, moneda, True, self._contenedor))
                pos += 1
        self.paginas.setCurrentIndex(LISTA if pos else VACIO)

    def _encabezado(self, nivel: str, etiqueta: str, n: int) -> QWidget:
        w = QWidget(self._contenedor)
        h = QHBoxLayout(w)
        h.setContentsMargins(0, 8, 0, 2)
        h.setSpacing(10)
        h.addWidget(BadgeNivel(nivel, w))
        lbl = QLabel(f"{_plural(n)} en nivel {etiqueta.lower()}", w)
        lbl.setStyleSheet(f"color: {COLORES['texto_secundario']}; font-size: 13px; font-weight: 600;")
        h.addWidget(lbl)
        h.addStretch(1)
        w.setObjectName(f"grupo_{nivel}")
        return w

    # -- escaneo manual ------------------------------------------------------------------------------
    def escanear(self) -> None:
        api = self.ctx.api
        if api is None or self._escaneando:
            return
        self._escaneando = True
        self.btn_escanear.setEnabled(False)
        self.btn_escanear.setText("Escaneando…")
        self.ctx.ejecutar(api.forzar_escaneo, self._escaneo_ok, self._escaneo_error, self)

    def _fin_escaneo(self) -> None:
        self._escaneando = False
        self.btn_escanear.setEnabled(True)
        self.btn_escanear.setText("Escanear ahora")

    def _escaneo_ok(self, res) -> None:
        self._fin_escaneo()
        partes = [f"{res.evaluados} evaluados"]
        if res.descuentos_aplicados:
            partes.append(f"{len(res.descuentos_aplicados)} descuentos aplicados")
        if res.descuentos_removidos:
            partes.append(f"{len(res.descuentos_removidos)} descuentos removidos")
        if res.retirados:
            partes.append(f"{len(res.retirados)} retirados por vencimiento")
        if not res.cambios:
            partes.append("sin cambios")
        self.toast("Escaneo completado: " + ", ".join(partes), "exito" if not res.retirados else "aviso")
        self.recargar(silencioso=True)

    def _escaneo_error(self, exc: BaseException) -> None:
        self._fin_escaneo()
        self.toast(mensaje_api(exc), "error", 6000)

    # -- ayudas --------------------------------------------------------------------------------------
    def filas(self) -> list[FilaRiesgo]:
        return [w for i in range(self._lista.count())
                if isinstance((w := self._lista.itemAt(i).widget()), FilaRiesgo)]

    def grupos(self) -> list[str]:
        return [w.objectName()[6:] for i in range(self._lista.count())
                if (w := self._lista.itemAt(i).widget()) is not None
                and w.objectName().startswith("grupo_")]

    @property
    def pagina(self) -> int:
        return self.paginas.currentIndex()
