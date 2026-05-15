from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton,
    QFrame
)
from PyQt6.QtCore import Qt, pyqtSignal
from models import Usuario
from database import get_session


class LoginWindow(QWidget):

    login_exitoso = pyqtSignal(object)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Inventario App — Acceso")
        self.setFixedSize(400, 460)
        self.session = get_session()
        self._construir_ui()
        self._aplicar_estilos()

    def _construir_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(48, 48, 48, 40)
        layout.setSpacing(0)

        # Marca superior
        marca = QFrame()
        marca.setFixedHeight(4)
        marca.setStyleSheet("background-color: #2563EB; border-radius: 2px;")
        layout.addWidget(marca)
        layout.addSpacing(28)

        # Título
        titulo = QLabel("Inventario App")
        titulo.setAlignment(Qt.AlignmentFlag.AlignLeft)
        titulo.setObjectName("titulo")
        layout.addWidget(titulo)

        subtitulo = QLabel("Gestión de descuentos dinámicos")
        subtitulo.setAlignment(Qt.AlignmentFlag.AlignLeft)
        subtitulo.setObjectName("subtitulo")
        layout.addWidget(subtitulo)
        layout.addSpacing(32)

        # Usuario
        lbl_usuario = QLabel("Usuario")
        lbl_usuario.setObjectName("campo_label")
        self.input_usuario = QLineEdit()
        self.input_usuario.setPlaceholderText("Nombre de usuario")
        self.input_usuario.setFixedHeight(42)
        layout.addWidget(lbl_usuario)
        layout.addSpacing(6)
        layout.addWidget(self.input_usuario)
        layout.addSpacing(16)

        # Contraseña
        lbl_password = QLabel("Contraseña")
        lbl_password.setObjectName("campo_label")
        self.input_password = QLineEdit()
        self.input_password.setPlaceholderText("Contraseña")
        self.input_password.setEchoMode(QLineEdit.EchoMode.Password)
        self.input_password.setFixedHeight(42)
        self.input_password.returnPressed.connect(self._iniciar_sesion)
        layout.addWidget(lbl_password)
        layout.addSpacing(6)
        layout.addWidget(self.input_password)
        layout.addSpacing(24)

        # Botón
        self.btn_login = QPushButton("Iniciar sesión")
        self.btn_login.setFixedHeight(44)
        self.btn_login.setObjectName("btn_login")
        self.btn_login.clicked.connect(self._iniciar_sesion)
        layout.addWidget(self.btn_login)
        layout.addSpacing(12)

        # Error
        self.lbl_error = QLabel("")
        self.lbl_error.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_error.setObjectName("lbl_error")
        layout.addWidget(self.lbl_error)

        layout.addStretch()

        # Footer
        footer = QLabel("v1.0.0")
        footer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        footer.setObjectName("footer")
        layout.addWidget(footer)

    def _iniciar_sesion(self):
        usuario_texto  = self.input_usuario.text().strip()
        password_texto = self.input_password.text().strip()

        if not usuario_texto or not password_texto:
            self.lbl_error.setText("Completa todos los campos")
            return

        usuario = self.session.query(Usuario).filter(
            Usuario.usuario == usuario_texto,
            Usuario.activo  == 1
        ).first()

        if usuario and usuario.verificar_password(password_texto):
            self.lbl_error.setText("")
            self.login_exitoso.emit(usuario)
            self.close()
        else:
            self.lbl_error.setText("Usuario o contraseña incorrectos")
            self.input_password.clear()

    def _aplicar_estilos(self):
        self.setStyleSheet("""
            QWidget {
                background-color: #FFFFFF;
                font-family: Segoe UI;
            }
            #titulo {
                font-size: 20px;
                font-weight: 700;
                color: #111827;
            }
            #subtitulo {
                font-size: 13px;
                color: #6B7280;
                margin-top: 2px;
            }
            #campo_label {
                font-size: 12px;
                font-weight: 600;
                color: #374151;
            }
            QLineEdit {
                background-color: #F9FAFB;
                color: #111827;
                border: 1px solid #D1D5DB;
                border-radius: 6px;
                padding: 8px 12px;
                font-size: 13px;
            }
            QLineEdit:focus {
                border: 1.5px solid #2563EB;
                background-color: #FFFFFF;
            }
            #btn_login {
                background-color: #2563EB;
                color: white;
                font-size: 13px;
                font-weight: 600;
                border-radius: 6px;
                border: none;
            }
            #btn_login:hover  { background-color: #1D4ED8; }
            #btn_login:pressed { background-color: #1E40AF; }
            #lbl_error {
                color: #DC2626;
                font-size: 12px;
            }
            #footer {
                color: #9CA3AF;
                font-size: 11px;
            }
        """)
