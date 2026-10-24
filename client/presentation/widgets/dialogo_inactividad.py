"""Aviso de cierre de sesion por inactividad con cuenta regresiva."""
from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QDialog, QLabel, QPushButton, QVBoxLayout

from ..styles.theme import COLORES, fuente


class DialogoInactividad(QDialog):
    """Modal para la UI pero sin bucle propio: usar ``open()``/``show()``
    (no ``exec()``) para que el hilo de red y los timers sigan corriendo.
    Cerrarlo con Esc/X cuenta como 'continuar' (hay actividad del usuario).
    """

    continuar = pyqtSignal()

    def __init__(self, segundos: int, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Sesión por expirar")
        self.setModal(True)
        self.setWindowFlag(Qt.WindowType.WindowContextHelpButtonHint, False)
        self.setMinimumWidth(380)
        self.setStyleSheet(f"QDialog {{ background: {COLORES['superficie']}; }}")
        self._programatico = False
        self.segundos = max(0, int(segundos))

        lay = QVBoxLayout(self)
        lay.setContentsMargins(32, 28, 32, 24)
        lay.setSpacing(12)

        self._mensaje = QLabel("Tu sesión se cerrará por inactividad", self)
        self._mensaje.setFont(fuente(14))
        self._mensaje.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._mensaje.setWordWrap(True)
        self._mensaje.setStyleSheet(f"color: {COLORES['texto']}; font-weight: 600;")

        self._cuenta = QLabel(self)
        self._cuenta.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._cuenta.setFont(fuente(56))
        self._cuenta.setAccessibleName("Segundos restantes")

        self._sub = QLabel("segundos restantes", self)
        self._sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._sub.setStyleSheet(f"color: {COLORES['texto_suave']}; font-size: 12px;")

        self._boton = QPushButton("Seguir conectado", self)
        self._boton.setProperty("variant", "primary")
        self._boton.setMinimumHeight(40)
        self._boton.setDefault(True)
        self._boton.setAutoDefault(True)
        self._boton.setCursor(Qt.CursorShape.PointingHandCursor)
        self._boton.clicked.connect(self._on_continuar)

        for w in (self._mensaje, self._cuenta, self._sub, self._boton):
            lay.addWidget(w)
        self._boton.setFocus()
        self.actualizar(self.segundos)

    @property
    def texto_cuenta(self) -> str:
        return self._cuenta.text()

    def actualizar(self, segundos: int) -> None:
        self.segundos = max(0, int(segundos))
        color = COLORES["peligro"] if self.segundos <= 10 else COLORES["aviso_texto"]
        self._cuenta.setStyleSheet(f"color: {color}; font-weight: 700; font-size: 56px;")
        self._cuenta.setText(str(self.segundos))
        self._sub.setText("segundo restante" if self.segundos == 1 else "segundos restantes")

    def cerrar_aviso(self) -> None:
        """Cierra sin emitir ``continuar`` (p. ej. la sesion ya fue renovada
        o ya expiro)."""
        self._programatico = True
        self.accept()

    def _on_continuar(self) -> None:
        self.continuar.emit()
        self._programatico = True
        self.accept()

    def reject(self) -> None:  # Esc o cerrar ventana
        if not self._programatico:
            self.continuar.emit()
            self._programatico = True
        super().reject()

    def showEvent(self, ev):  # noqa: N802
        self._programatico = False
        super().showEvent(ev)
        self._boton.setFocus()
