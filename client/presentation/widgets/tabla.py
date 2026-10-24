"""Tabla estandar preconfigurada."""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QAbstractItemView, QHeaderView, QTableWidget, QTableWidgetItem

_IZQ = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
_DER = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter


class _ItemNumerico(QTableWidgetItem):
    """Ordena por valor numerico aunque el texto lleve formato."""

    def __lt__(self, otro):  # noqa: D105
        a = self.data(Qt.ItemDataRole.UserRole)
        b = otro.data(Qt.ItemDataRole.UserRole)
        if isinstance(a, (int, float)) and isinstance(b, (int, float)):
            return a < b
        return super().__lt__(otro)


class TablaEstandar(QTableWidget):
    def __init__(self, columnas: list[str] | None = None, parent=None):
        super().__init__(0, 0, parent)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setAlternatingRowColors(True)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setSortingEnabled(True)
        self.setShowGrid(False)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.verticalHeader().setVisible(False)
        self.verticalHeader().setDefaultSectionSize(40)
        h = self.horizontalHeader()
        h.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        h.setStretchLastSection(True)
        h.setSortIndicatorShown(True)
        h.setMinimumHeight(40)
        h.setDefaultAlignment(_IZQ)
        if columnas:
            self.set_columnas(columnas)

    def set_columnas(self, columnas: list[str]) -> None:
        self.setColumnCount(len(columnas))
        self.setHorizontalHeaderLabels(columnas)
        for c in range(len(columnas)):
            self._alinear_encabezado(c, _IZQ)

    def _alinear_encabezado(self, col: int, alineacion) -> None:
        it = self.horizontalHeaderItem(col)
        if it is not None:
            it.setTextAlignment(alineacion)

    def set_filas(self, filas: list[list], formateador=None, formateadores: dict | None = None) -> None:
        """Reemplaza el contenido. Los int/float se ordenan numericamente y se
        alinean a la derecha (encabezado incluido); el texto, a la izquierda.
        ``formateador(valor)`` aplica a todas las columnas numericas;
        ``formateadores={col: fn}`` lo sobreescribe por columna."""
        formateadores = formateadores or {}
        self.setSortingEnabled(False)
        self.setRowCount(len(filas))
        numericas: set[int] = set()
        for r, fila in enumerate(filas):
            for c, v in enumerate(fila):
                if isinstance(v, (int, float)) and not isinstance(v, bool):
                    fmt = formateadores.get(c) or formateador or str
                    it = _ItemNumerico(fmt(v))
                    it.setData(Qt.ItemDataRole.UserRole, v)
                    it.setTextAlignment(_DER)
                    numericas.add(c)
                else:
                    it = QTableWidgetItem("" if v is None else str(v))
                    it.setTextAlignment(_IZQ)
                self.setItem(r, c, it)
        for c in range(self.columnCount()):
            self._alinear_encabezado(c, _DER if c in numericas else _IZQ)
        self.setSortingEnabled(True)

    def texto(self, fila: int, columna: int) -> str:
        it = self.item(fila, columna)
        return it.text() if it else ""
