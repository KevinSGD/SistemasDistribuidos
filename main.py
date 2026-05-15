import sys
from PyQt6.QtWidgets import QApplication
from database import inicializar_bd
from ui.login import LoginWindow

_app_ventana = None


def abrir_ventana(usuario):
    global _app_ventana
    if usuario.rol == "admin":
        from ui.main_window import MainWindow
        _app_ventana = MainWindow(usuario)
    else:
        from ui.buyer_window import BuyerWindow
        _app_ventana = BuyerWindow(usuario)
    _app_ventana.show()


def main():
    inicializar_bd()
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    login = LoginWindow()
    login.login_exitoso.connect(abrir_ventana)
    login.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
