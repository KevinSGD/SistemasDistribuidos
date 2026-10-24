"""Pantalla de login (vista pasiva). Tipografia y paleta de contexto.md, seccion Interfaz: Login.

No hace red: emite `login_solicitado(url, usuario, password)` y `probar_solicitado(url)`; el
controlador (Aplicacion) responde con `mostrar_error`, `mostrar_estado_servidor` o `restablecer`."""
from __future__ import annotations

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QCloseEvent
from PyQt6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget,
)

VERSION = "v1.0.0"


class LoginView(QWidget):
    login_solicitado = pyqtSignal(str, str, str)      # url, usuario, password
    probar_solicitado = pyqtSignal(str)               # url
    cerrada = pyqtSignal()

    def __init__(self, url: str, url_editable: bool = True):
        super().__init__()
        self.setWindowTitle("Inventario App — Acceso")
        self.setFixedWidth(400)
        self._cargando = False
        self._bloqueo_restante = 0
        self._timer_bloqueo = QTimer(self)
        self._timer_bloqueo.setInterval(1000)
        self._timer_bloqueo.timeout.connect(self._tick_bloqueo)
        self._construir_ui(url, url_editable)
        self._aplicar_estilos()
        self.input_usuario.setFocus()

    # -- construccion ---------------------------------------------------------------------
    def _construir_ui(self, url: str, url_editable: bool) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(48, 48, 48, 32)
        layout.setSpacing(0)

        marca = QFrame()
        marca.setFixedHeight(4)
        marca.setStyleSheet("background-color: #2563EB; border-radius: 2px;")
        layout.addWidget(marca)
        layout.addSpacing(28)

        titulo = QLabel("Inventario App")
        titulo.setObjectName("titulo")
        layout.addWidget(titulo)
        subtitulo = QLabel("Gestión de descuentos dinámicos")
        subtitulo.setObjectName("subtitulo")
        layout.addWidget(subtitulo)
        layout.addSpacing(24)

        # Mensaje informativo (p. ej. "Sesión cerrada por inactividad")
        self.lbl_aviso = QLabel("")
        self.lbl_aviso.setObjectName("lbl_aviso")
        self.lbl_aviso.setWordWrap(True)
        self.lbl_aviso.setAccessibleName("Aviso")
        self.lbl_aviso.hide()
        layout.addWidget(self.lbl_aviso)

        lbl_usuario = QLabel("Usuario")
        lbl_usuario.setObjectName("campo_label")
        self.input_usuario = QLineEdit()
        self.input_usuario.setPlaceholderText("Nombre de usuario")
        self.input_usuario.setFixedHeight(42)
        self.input_usuario.returnPressed.connect(self._enviar)
        layout.addWidget(lbl_usuario)
        layout.addSpacing(6)
        layout.addWidget(self.input_usuario)
        layout.addSpacing(16)

        lbl_password = QLabel("Contraseña")
        lbl_password.setObjectName("campo_label")
        self.input_password = QLineEdit()
        self.input_password.setPlaceholderText("Contraseña")
        self.input_password.setEchoMode(QLineEdit.EchoMode.Password)
        self.input_password.setFixedHeight(42)
        self.input_password.returnPressed.connect(self._enviar)
        layout.addWidget(lbl_password)
        layout.addSpacing(6)
        layout.addWidget(self.input_password)
        layout.addSpacing(24)

        self.btn_login = QPushButton("Iniciar sesión")
        self.btn_login.setFixedHeight(44)
        self.btn_login.setObjectName("btn_login")
        self.btn_login.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_login.clicked.connect(self._enviar)
        layout.addWidget(self.btn_login)
        layout.addSpacing(12)

        self.lbl_error = QLabel("")
        self.lbl_error.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_error.setObjectName("lbl_error")
        self.lbl_error.setWordWrap(True)
        self.lbl_error.setAccessibleName("Error")
        layout.addWidget(self.lbl_error)

        layout.addStretch()

        # Campo discreto "Servidor": enlace que despliega URL + Probar
        self.btn_servidor = QPushButton(f"Servidor: {url}")
        self.btn_servidor.setObjectName("btn_servidor")
        self.btn_servidor.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_servidor.setFlat(True)
        self.btn_servidor.setEnabled(url_editable)
        self.btn_servidor.setToolTip("Cambiar la dirección del servidor" if url_editable
                                     else "Fijada por la variable INVENTARIO_URL")
        self.btn_servidor.clicked.connect(self._alternar_servidor)
        layout.addWidget(self.btn_servidor, alignment=Qt.AlignmentFlag.AlignCenter)

        self.panel_servidor = QWidget()
        pl = QVBoxLayout(self.panel_servidor)
        pl.setContentsMargins(0, 6, 0, 0)
        pl.setSpacing(6)
        fila = QHBoxLayout()
        fila.setSpacing(6)
        self.input_servidor = QLineEdit(url)
        self.input_servidor.setObjectName("input_servidor")
        self.input_servidor.setPlaceholderText("http://host:8000")
        self.input_servidor.setFixedHeight(32)
        self.input_servidor.setAccessibleName("Servidor")
        self.input_servidor.returnPressed.connect(self._probar)
        self.input_servidor.textChanged.connect(self._url_editada)
        self.btn_probar = QPushButton("Probar")
        self.btn_probar.setObjectName("btn_probar")
        self.btn_probar.setFixedHeight(32)
        self.btn_probar.clicked.connect(self._probar)
        fila.addWidget(self.input_servidor, 1)
        fila.addWidget(self.btn_probar)
        pl.addLayout(fila)
        self.lbl_servidor = QLabel("")
        self.lbl_servidor.setObjectName("lbl_servidor")
        self.lbl_servidor.setWordWrap(True)
        pl.addWidget(self.lbl_servidor)
        self.panel_servidor.hide()
        layout.addWidget(self.panel_servidor)

        layout.addSpacing(8)
        footer = QLabel(VERSION)
        footer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        footer.setObjectName("footer")
        layout.addWidget(footer)

    # -- interaccion ----------------------------------------------------------------------
    @property
    def url(self) -> str:
        return self.input_servidor.text().strip()

    def _alternar_servidor(self) -> None:
        visible = not self.panel_servidor.isVisible()
        self.panel_servidor.setVisible(visible)
        if visible:
            self.input_servidor.setFocus()
        self.adjustSize()

    def _url_editada(self, texto: str) -> None:
        self.btn_servidor.setText(f"Servidor: {texto.strip()}")
        self.lbl_servidor.setText("")

    def _probar(self) -> None:
        self.lbl_servidor.setStyleSheet("")
        self.lbl_servidor.setText("Probando…")
        self.probar_solicitado.emit(self.url)

    def _enviar(self) -> None:
        if self._cargando or self._bloqueo_restante > 0:
            return
        usuario = self.input_usuario.text().strip()
        password = self.input_password.text()
        if not usuario or not password:
            self.mostrar_error("Completa todos los campos")
            (self.input_usuario if not usuario else self.input_password).setFocus()
            return
        self.lbl_error.setText("")
        self.lbl_aviso.hide()
        self.set_cargando(True)
        self.login_solicitado.emit(self.url, usuario, password)

    # -- API para el controlador ----------------------------------------------------------
    def set_cargando(self, cargando: bool) -> None:
        self._cargando = cargando
        for w in (self.input_usuario, self.input_password):
            w.setEnabled(not cargando)
        self.btn_login.setEnabled(not cargando and self._bloqueo_restante == 0)
        self.btn_login.setText("Ingresando…" if cargando else "Iniciar sesión")

    def mostrar_error(self, texto: str, bloquear_segundos: int | None = None) -> None:
        self.set_cargando(False)
        self.lbl_error.setText(texto)
        self.input_password.clear()
        if bloquear_segundos and bloquear_segundos > 0:
            self._bloqueo_restante = int(bloquear_segundos)
            self.btn_login.setEnabled(False)
            self._mostrar_bloqueo()
            self._timer_bloqueo.start()
        else:
            self.input_password.setFocus()

    def _mostrar_bloqueo(self) -> None:
        self.btn_login.setText(f"Reintentar en {self._bloqueo_restante} s")

    def _tick_bloqueo(self) -> None:
        self._bloqueo_restante -= 1
        if self._bloqueo_restante <= 0:
            self._bloqueo_restante = 0
            self._timer_bloqueo.stop()
            self.btn_login.setText("Iniciar sesión")
            self.btn_login.setEnabled(True)
            self.lbl_error.setText("")
        else:
            self._mostrar_bloqueo()

    def mostrar_estado_servidor(self, ok: bool, texto: str) -> None:
        color = "#15803D" if ok else "#DC2626"
        self.lbl_servidor.setStyleSheet(f"color: {color};")
        self.lbl_servidor.setText(texto)

    def restablecer(self, mensaje: str | None = None) -> None:
        """Deja el formulario listo para un nuevo ingreso, con un mensaje opcional."""
        self._timer_bloqueo.stop()
        self._bloqueo_restante = 0
        self.set_cargando(False)
        self.input_password.clear()
        self.lbl_error.setText("")
        self.lbl_aviso.setText(mensaje or "")
        self.lbl_aviso.setVisible(bool(mensaje))
        self.input_usuario.setFocus()

    def closeEvent(self, ev: QCloseEvent) -> None:  # noqa: N802
        self.cerrada.emit()
        super().closeEvent(ev)

    # -- estilos --------------------------------------------------------------------------
    def _aplicar_estilos(self) -> None:
        self.setStyleSheet("""
            QWidget {
                background-color: #FFFFFF;
                font-family: "Segoe UI";
            }
            #titulo { font-size: 20px; font-weight: 700; color: #111827; }
            #subtitulo { font-size: 13px; color: #6B7280; margin-top: 2px; }
            #campo_label { font-size: 12px; font-weight: 600; color: #374151; }
            QLineEdit {
                background-color: #F9FAFB;
                color: #111827;
                border: 1px solid #D1D5DB;
                border-radius: 6px;
                padding: 8px 12px;
                font-size: 13px;
            }
            QLineEdit:focus { border: 1.5px solid #2563EB; background-color: #FFFFFF; }
            #btn_login {
                background-color: #2563EB; color: white; font-size: 13px;
                font-weight: 600; border-radius: 6px; border: none;
            }
            #btn_login:hover { background-color: #1D4ED8; }
            #btn_login:pressed { background-color: #1E40AF; }
            #btn_login:disabled { background-color: #93B4F5; color: #FFFFFF; }
            #lbl_error { color: #DC2626; font-size: 12px; }
            #lbl_aviso {
                background-color: #FEF3C7; color: #92400E; font-size: 12px;
                border-radius: 6px; padding: 8px 12px; margin-bottom: 16px;
            }
            #btn_servidor {
                color: #9CA3AF; font-size: 11px; border: none; background: transparent;
                padding: 2px 6px;
            }
            #btn_servidor:hover:enabled { color: #6B7280; text-decoration: underline; }
            #input_servidor { padding: 4px 8px; font-size: 12px; }
            #btn_probar {
                background-color: #FFFFFF; color: #374151; border: 1px solid #D1D5DB;
                border-radius: 6px; padding: 0 12px; font-size: 12px; font-weight: 600;
            }
            #btn_probar:hover { background-color: #F9FAFB; }
            #lbl_servidor { font-size: 11px; color: #6B7280; }
            #footer { color: #9CA3AF; font-size: 11px; }
        """)
