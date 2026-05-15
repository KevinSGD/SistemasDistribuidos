from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout,
    QHBoxLayout, QLabel, QPushButton,
    QStackedWidget, QFrame, QMessageBox
)
from PyQt6.QtCore import Qt, QTimer
from risk_engine import RiskEngine


class MainWindow(QMainWindow):

    def __init__(self, usuario):
        super().__init__()
        self.usuario = usuario
        self.setWindowTitle("Inventario App — Administrador")
        self.setMinimumSize(1100, 700)
        self.engine = RiskEngine()

        central = QWidget()
        self.setCentralWidget(central)
        layout_principal = QHBoxLayout(central)
        layout_principal.setContentsMargins(0, 0, 0, 0)
        layout_principal.setSpacing(0)

        self.sidebar   = self._crear_sidebar()
        self.contenido = QStackedWidget()
        self.contenido.setStyleSheet("background-color: #F9FAFB;")

        layout_principal.addWidget(self.sidebar)
        layout_principal.addWidget(self.contenido)

        self._cargar_vistas()
        self._aplicar_estilos()

        self.timer = QTimer()
        self.timer.timeout.connect(self._escanear_automatico)
        self.timer.start(60000)
        self._escanear_automatico()

    def _crear_sidebar(self) -> QFrame:
        sidebar = QFrame()
        sidebar.setFixedWidth(200)
        sidebar.setObjectName("sidebar")

        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Encabezado
        header = QFrame()
        header.setObjectName("sidebar_header")
        header.setFixedHeight(64)
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(20, 0, 20, 0)
        titulo = QLabel("Inventario App")
        titulo.setObjectName("sidebar_titulo")
        header_layout.addWidget(titulo)
        layout.addWidget(header)

        # Rol/usuario
        rol_frame = QFrame()
        rol_frame.setObjectName("rol_frame")
        rol_frame.setFixedHeight(48)
        rol_layout = QVBoxLayout(rol_frame)
        rol_layout.setContentsMargins(20, 6, 20, 6)
        rol_layout.setSpacing(1)
        lbl_nombre = QLabel(self.usuario.nombre)
        lbl_nombre.setObjectName("sidebar_nombre")
        lbl_rol = QLabel("Administrador")
        lbl_rol.setObjectName("sidebar_rol")
        rol_layout.addWidget(lbl_nombre)
        rol_layout.addWidget(lbl_rol)
        layout.addWidget(rol_frame)

        # Separador
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setObjectName("sidebar_sep")
        layout.addWidget(sep)
        layout.addSpacing(8)

        # Navegación
        self.botones_nav = []
        opciones = [
            ("Dashboard",      0),
            ("Inventario",     1),
            ("Alertas",        2),
            ("Configuración",  3),
        ]

        for texto, index in opciones:
            btn = QPushButton(texto)
            btn.setObjectName("nav_btn")
            btn.setFixedHeight(44)
            btn.clicked.connect(lambda checked, i=index: self._cambiar_vista(i))
            layout.addWidget(btn)
            self.botones_nav.append(btn)

        layout.addStretch()

        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.HLine)
        sep2.setObjectName("sidebar_sep")
        layout.addWidget(sep2)

        btn_cerrar = QPushButton("Cerrar sesión")
        btn_cerrar.setObjectName("btn_cerrar")
        btn_cerrar.setFixedHeight(40)
        btn_cerrar.clicked.connect(self._cerrar_sesion)
        layout.addWidget(btn_cerrar)

        btn_salir = QPushButton("Salir")
        btn_salir.setObjectName("btn_salir")
        btn_salir.setFixedHeight(40)
        btn_salir.clicked.connect(self._salir)
        layout.addWidget(btn_salir)

        version = QLabel("v1.0.0")
        version.setAlignment(Qt.AlignmentFlag.AlignCenter)
        version.setObjectName("version_label")
        version.setFixedHeight(28)
        layout.addWidget(version)

        return sidebar

    def _cargar_vistas(self):
        from ui.dashboard import DashboardView
        from ui.inventory_view import InventoryView
        from ui.alerts_view import AlertsView
        from ui.config_view import ConfigView

        self.dashboard_view = DashboardView(self.engine)
        self.inventory_view = InventoryView(self.engine)
        self.alerts_view    = AlertsView(self.engine)
        self.config_view    = ConfigView()

        self.contenido.addWidget(self.dashboard_view)
        self.contenido.addWidget(self.inventory_view)
        self.contenido.addWidget(self.alerts_view)
        self.contenido.addWidget(self.config_view)

        self._cambiar_vista(0)

    def _cambiar_vista(self, index: int):
        self.contenido.setCurrentIndex(index)
        for i, btn in enumerate(self.botones_nav):
            btn.setProperty("activo", i == index)
            btn.style().unpolish(btn)
            btn.style().polish(btn)

    def _escanear_automatico(self):
        resultados  = self.engine.escanear_inventario()
        eliminados  = getattr(self.engine, "ultimos_eliminados", [])
        self.engine.aplicar_descuentos(resultados)

        if hasattr(self, "dashboard_view"):
            self.dashboard_view.actualizar(resultados)
        if hasattr(self, "alerts_view"):
            self.alerts_view.actualizar(resultados)

        # Refrescar tabla de inventario si hay cambios por vencimiento
        if eliminados and hasattr(self, "inventory_view"):
            self.inventory_view.cargar_productos()
            lista = "\n".join(f"  • {n}" for n in eliminados)
            QMessageBox.warning(
                self,
                "Productos eliminados por vencimiento",
                f"Los siguientes productos han sido retirados del sistema "
                f"porque su fecha de vencimiento ya expiró:\n\n{lista}"
            )

    def _cerrar_sesion(self):
        resp = QMessageBox.question(
            self, "Cerrar sesión",
            "¿Deseas cerrar sesión?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if resp == QMessageBox.StandardButton.Yes:
            self.timer.stop()
            self.close()
            from ui.login import LoginWindow
            self._login = LoginWindow()
            self._login.login_exitoso.connect(self._reabrir)
            self._login.show()

    def _reabrir(self, usuario):
        import main as _main
        _main.abrir_ventana(usuario)

    def _salir(self):
        resp = QMessageBox.question(
            self, "Salir",
            "¿Estás seguro de que deseas salir?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if resp == QMessageBox.StandardButton.Yes:
            import sys
            sys.exit(0)

    def _aplicar_estilos(self):
        self.setStyleSheet("""
            QMainWindow, QWidget { background-color: #F9FAFB; font-family: Segoe UI; color: #111827; }

            #sidebar {
                background-color: #FFFFFF;
                border-right: 1px solid #E5E7EB;
            }
            #sidebar_header {
                background-color: #FFFFFF;
                border-bottom: 1px solid #E5E7EB;
            }
            #sidebar_titulo {
                color: #1E40AF;
                font-size: 15px;
                font-weight: 700;
            }
            #rol_frame {
                background-color: #F9FAFB;
                border-bottom: 1px solid #E5E7EB;
            }
            #sidebar_nombre {
                color: #111827;
                font-size: 12px;
                font-weight: 600;
                background-color: transparent;
            }
            #sidebar_rol {
                color: #6B7280;
                font-size: 11px;
                background-color: transparent;
            }
            #sidebar_sep {
                color: #E5E7EB;
                margin: 0px 16px;
                background-color: #FFFFFF;
            }
            #nav_btn {
                background-color: transparent;
                color: #6B7280;
                font-size: 13px;
                font-weight: 500;
                text-align: left;
                padding-left: 20px;
                border: none;
                border-radius: 0px;
            }
            #nav_btn:hover {
                background-color: #F3F4F6;
                color: #111827;
            }
            #nav_btn[activo=true] {
                background-color: #EFF6FF;
                color: #1D4ED8;
                border-left: 3px solid #2563EB;
                font-weight: 600;
            }
            #btn_cerrar {
                background-color: #FFFFFF;
                color: #6B7280;
                font-size: 12px;
                font-weight: 500;
                text-align: left;
                padding-left: 20px;
                border: none;
                border-top: 1px solid #F3F4F6;
            }
            #btn_cerrar:hover { background-color: #F9FAFB; color: #374151; }
            #btn_salir {
                background-color: #FFFFFF;
                color: #DC2626;
                font-size: 12px;
                font-weight: 500;
                text-align: left;
                padding-left: 20px;
                border: none;
            }
            #btn_salir:hover { background-color: #FEF2F2; }
            #version_label {
                color: #9CA3AF;
                font-size: 11px;
                background-color: #FFFFFF;
                border-top: 1px solid #F3F4F6;
            }
            QScrollArea { background-color: transparent; border: none; }
            QScrollBar:vertical {
                background-color: #F3F4F6;
                width: 5px;
                border-radius: 3px;
            }
            QScrollBar::handle:vertical {
                background-color: #D1D5DB;
                border-radius: 3px;
            }
        """)
