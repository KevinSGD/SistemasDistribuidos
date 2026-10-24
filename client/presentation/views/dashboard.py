"""Dashboard: conteos por nivel y productos que requieren atencion (GET /riesgo/resumen)."""
from __future__ import annotations


from PyQt6.QtWidgets import (
    QHBoxLayout, QLabel, QScrollArea, QStackedWidget, QVBoxLayout, QWidget,
)

from client.infrastructure.api_client import ErrorConexion

from ..styles.theme import COLORES
from ..widgets import EstadoVacio, TarjetaResumen
from ._comunes import (
    FilaRiesgo, VistaBase, mensaje_api, moneda_publica, mostrar_estado, titulo_vista,
)

LISTA, VACIO, ERROR = 0, 1, 2


class DashboardView(VistaBase):
    def __init__(self, app_ctx, parent: QWidget | None = None):
        super().__init__(app_ctx, parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(32, 28, 32, 28)
        lay.setSpacing(20)
        lay.addWidget(titulo_vista("Dashboard"))

        fila = QHBoxLayout()
        fila.setSpacing(12)
        self.tarjeta_total = TarjetaResumen("Total", "–", "texto_secundario", self)
        self.tarjeta_criticos = TarjetaResumen("Críticos", "–", "nivel_critico", self)
        self.tarjeta_altos = TarjetaResumen("Riesgo alto", "–", "nivel_alto", self)
        self.tarjeta_medios = TarjetaResumen("Riesgo medio", "–", "nivel_medio", self)
        for t in (self.tarjeta_total, self.tarjeta_criticos, self.tarjeta_altos, self.tarjeta_medios):
            fila.addWidget(t, 1)
        lay.addLayout(fila)

        self.lbl_subtitulo = QLabel("Productos que requieren atención", self)
        self.lbl_subtitulo.setStyleSheet(
            f"font-size: 13px; font-weight: 600; color: {COLORES['texto_suave']}; padding-top: 4px;")
        lay.addWidget(self.lbl_subtitulo)

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

        self.estado_vacio = EstadoVacio("✓", "Sin alertas",
                                        "Todo el inventario está en estado normal.", None, self)
        mostrar_estado(self.estado_vacio)
        self.paginas.addWidget(self.estado_vacio)

        self.estado_error = EstadoVacio.error_conexion(self)
        mostrar_estado(self.estado_error)
        self.estado_error.accion.connect(lambda: self.recargar())
        self.paginas.addWidget(self.estado_error)

    # -- datos -------------------------------------------------------------------------------------
    def recargar(self, silencioso: bool = False) -> None:
        api = self.ctx.api
        if api is None:
            return

        def trabajo():
            return api.resumen_riesgo(), moneda_publica(api)

        self.consultar(trabajo, self._pintar, lambda exc: self._error(exc, silencioso), silencioso)

    def _error(self, exc: BaseException, silencioso: bool) -> None:
        if silencioso and self.paginas.currentIndex() != ERROR and self.cargada:
            return                                  # se conservan los ultimos datos buenos
        conexion = isinstance(exc, ErrorConexion)
        mostrar_estado(self.estado_error, "Sin conexión con el servidor" if conexion else "No se pudieron cargar los datos", mensaje_api(exc))
        self.paginas.setCurrentIndex(ERROR)
        for t in (self.tarjeta_total, self.tarjeta_criticos, self.tarjeta_altos, self.tarjeta_medios):
            t.set_valor("–")

    def _pintar(self, datos) -> None:
        resumen, moneda = datos
        c = resumen.conteos
        self.tarjeta_total.set_valor(resumen.total_activos)
        self.tarjeta_criticos.set_valor(c.get("critico", 0))
        self.tarjeta_altos.set_valor(c.get("alto", 0))
        self.tarjeta_medios.set_valor(c.get("medio", 0))

        while self._lista.count() > 1:
            it = self._lista.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        for pos, item in enumerate(resumen.atencion):
            self._lista.insertWidget(pos, FilaRiesgo(item, moneda, parent=self._contenedor))
        self.paginas.setCurrentIndex(LISTA if resumen.atencion else VACIO)

    # -- ayudas para pruebas / consulta ------------------------------------------------------------
    def filas(self) -> list[FilaRiesgo]:
        out = []
        for i in range(self._lista.count()):
            w = self._lista.itemAt(i).widget()
            if isinstance(w, FilaRiesgo):
                out.append(w)
        return out

    @property
    def pagina(self) -> int:
        return self.paginas.currentIndex()
