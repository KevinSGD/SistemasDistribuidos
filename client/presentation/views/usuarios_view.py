"""Usuarios (admin): listar, crear, activar/desactivar y cambiar contrasena (/usuarios)."""
from __future__ import annotations

import re


from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QComboBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QPushButton, QStackedWidget,
    QVBoxLayout, QWidget,
)

from client.infrastructure.api_client import ErrorConexion
from shared.schemas import PASSWORD_MIN, UsuarioIn, UsuarioOut, UsuarioUpdate

from ..styles.theme import COLORES
from ..widgets import EstadoVacio, TablaEstandar
from . import _comunes as c

TABLA, ERROR = 0, 1
COLUMNAS = ["ID", "Nombre", "Usuario", "Rol", "Estado"]
ROLES = {"admin": "Administrador", "comprador": "Comprador"}


def _campo_password(padre: QWidget) -> QLineEdit:
    e = QLineEdit(padre)
    e.setEchoMode(QLineEdit.EchoMode.Password)
    return e


class UsuarioDialog(c.DialogoFormulario):
    """Alta de usuario: nombre, usuario (>= 3, sin espacios), rol y contrasena (>= 8)."""

    def __init__(self, app_ctx, parent: QWidget | None = None):
        super().__init__(app_ctx, "Nuevo usuario", "Crear usuario", parent)
        self.nombre = QLineEdit(self)
        self.nombre.setMaxLength(100)
        self.usuario = QLineEdit(self)
        self.usuario.setMaxLength(50)
        self.rol = QComboBox(self)
        for clave, etiqueta in ROLES.items():
            self.rol.addItem(etiqueta, clave)
        self.rol.setCurrentIndex(1)
        self.password = _campo_password(self)
        self.confirmacion = _campo_password(self)
        self.agregar_campo("nombre", "Nombre completo *", self.nombre)
        self.agregar_campo("usuario", "Nombre de usuario *", self.usuario,
                           "Mínimo 3 caracteres, sin espacios")
        self.agregar_campo("rol", "Rol", self.rol)
        self.agregar_campo("password", "Contraseña *", self.password,
                           f"Mínimo {PASSWORD_MIN} caracteres")
        self.agregar_campo("confirmacion", "Repetir contraseña *", self.confirmacion)

    def validar(self):
        ok = True
        nombre, usuario = self.nombre.text().strip(), self.usuario.text().strip()
        if not nombre:
            self.error_campo("nombre", "El nombre es obligatorio")
            ok = False
        if len(usuario) < 3 or re.search(r"\s", usuario):
            self.error_campo("usuario", "Mínimo 3 caracteres y sin espacios")
            ok = False
        pw = self.password.text()
        if len(pw) < PASSWORD_MIN:
            self.error_campo("password", f"Mínimo {PASSWORD_MIN} caracteres")
            ok = False
        if self.confirmacion.text() != pw:
            self.error_campo("confirmacion", "Las contraseñas no coinciden")
            ok = False
        if not ok:
            return None
        return UsuarioIn(nombre=nombre, usuario=usuario, password=pw, rol=self.rol.currentData())

    def llamar(self, datos):
        return self.ctx.api.crear_usuario(datos)


class PasswordDialog(c.DialogoFormulario):
    def __init__(self, app_ctx, usuario: UsuarioOut, parent: QWidget | None = None):
        super().__init__(app_ctx, f"Cambiar contraseña de {usuario.usuario}", "Cambiar contraseña",
                         parent)
        self._usuario = usuario
        self.password = _campo_password(self)
        self.confirmacion = _campo_password(self)
        self.agregar_campo("password", "Nueva contraseña *", self.password,
                           f"Mínimo {PASSWORD_MIN} caracteres. Se cerrarán las sesiones abiertas de "
                           "este usuario.")
        self.agregar_campo("confirmacion", "Repetir contraseña *", self.confirmacion)

    def validar(self):
        ok = True
        pw = self.password.text()
        if len(pw) < PASSWORD_MIN:
            self.error_campo("password", f"Mínimo {PASSWORD_MIN} caracteres")
            ok = False
        if self.confirmacion.text() != pw:
            self.error_campo("confirmacion", "Las contraseñas no coinciden")
            ok = False
        return UsuarioUpdate(password=pw) if ok else None

    def llamar(self, datos):
        return self.ctx.api.actualizar_usuario(self._usuario.id, datos)


class UsuariosView(c.VistaBase):
    def __init__(self, app_ctx, parent: QWidget | None = None):
        super().__init__(app_ctx, parent)
        self._usuarios: list[UsuarioOut] = []
        self._dialogo: c.DialogoFormulario | None = None

        lay = QVBoxLayout(self)
        lay.setContentsMargins(32, 28, 32, 28)
        lay.setSpacing(14)
        cab = QHBoxLayout()
        cab.addWidget(c.titulo_vista("Usuarios"))
        cab.addStretch(1)
        self.btn_nuevo = QPushButton("Nuevo usuario", self)
        self.btn_nuevo.setProperty("variant", "primary")
        self.btn_nuevo.clicked.connect(self.nuevo)
        cab.addWidget(self.btn_nuevo)
        lay.addLayout(cab)

        self.paginas = QStackedWidget(self)
        lay.addWidget(self.paginas, 1)
        self.tabla = TablaEstandar(COLUMNAS, self)
        self.tabla.setAccessibleName("Tabla de usuarios")
        h = self.tabla.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.tabla.itemSelectionChanged.connect(self._actualizar_botones)
        self.paginas.addWidget(self.tabla)
        self.estado_error = EstadoVacio.error_conexion(self)
        c.mostrar_estado(self.estado_error)
        self.estado_error.accion.connect(lambda: self.recargar())
        self.paginas.addWidget(self.estado_error)

        pie = QHBoxLayout()
        pie.setSpacing(8)
        self.btn_estado = QPushButton("Desactivar", self)
        self.btn_password = QPushButton("Cambiar contraseña", self)
        self.btn_actualizar = QPushButton("Actualizar", self)
        self.btn_estado.clicked.connect(self.alternar_estado)
        self.btn_password.clicked.connect(self.cambiar_password)
        self.btn_actualizar.clicked.connect(lambda: self.recargar())
        self.lbl_ayuda = QLabel("Desactivar a un usuario o cambiar su contraseña cierra sus sesiones abiertas.",
                                self)
        self.lbl_ayuda.setStyleSheet(f"color: {COLORES['texto_suave']}; font-size: 12px;")
        pie.addWidget(self.btn_estado)
        pie.addWidget(self.btn_password)
        pie.addSpacing(8)
        pie.addWidget(self.lbl_ayuda, 1)
        pie.addWidget(self.btn_actualizar)
        lay.addLayout(pie)
        self._actualizar_botones()

    # -- carga ---------------------------------------------------------------------------------------
    def recargar(self, silencioso: bool = False) -> None:
        api = self.ctx.api
        if api is None:
            return
        self.consultar(api.listar_usuarios, self._pintar, lambda e: self._error(e, silencioso),
                       silencioso)

    def _error(self, exc: BaseException, silencioso: bool) -> None:
        if silencioso and self.cargada and self.paginas.currentIndex() != ERROR:
            return
        c.mostrar_estado(self.estado_error, "Sin conexión con el servidor" if isinstance(exc, ErrorConexion)
            else "No se pudo cargar la lista de usuarios", c.mensaje_api(exc))
        self.paginas.setCurrentIndex(ERROR)

    def _pintar(self, usuarios: list[UsuarioOut]) -> None:
        sel = self.seleccionado()
        sel_id = sel.id if sel else None
        self._usuarios = usuarios
        yo = self.ctx.sesion.usuario_id if self.ctx.sesion else None
        self.tabla.blockSignals(True)
        self.tabla.set_filas([
            [u.id, u.nombre + (" (tú)" if u.id == yo else ""), u.usuario, ROLES.get(u.rol, u.rol),
             "Activo" if u.activo else "Inactivo"] for u in usuarios])
        fila_sel = -1
        for r in range(self.tabla.rowCount()):
            uid = int(self.tabla.texto(r, 0))
            it = self.tabla.item(r, 4)
            inactivo = it.text() == "Inactivo"
            it.setForeground(QColor(COLORES["peligro"] if inactivo else COLORES["exito_texto"]))
            if inactivo:
                for col in range(4):
                    self.tabla.item(r, col).setForeground(QColor(COLORES["texto_suave"]))
            if uid == sel_id:
                fila_sel = r
        self.tabla.blockSignals(False)
        if fila_sel >= 0:
            self.tabla.selectRow(fila_sel)
        else:
            self.tabla.clearSelection()
        self.paginas.setCurrentIndex(TABLA)
        self._actualizar_botones()

    def seleccionado(self) -> UsuarioOut | None:
        fila = self.tabla.currentRow()
        if fila < 0 or not self.tabla.selectionModel().hasSelection():
            return None
        it = self.tabla.item(fila, 0)
        if it is None:
            return None
        uid = int(it.text())
        return next((u for u in self._usuarios if u.id == uid), None)

    def seleccionar(self, usuario_id: int) -> bool:
        for r in range(self.tabla.rowCount()):
            if int(self.tabla.texto(r, 0)) == usuario_id:
                self.tabla.selectRow(r)
                return True
        return False

    def _actualizar_botones(self) -> None:
        u = self.seleccionado()
        self.btn_estado.setEnabled(u is not None)
        self.btn_password.setEnabled(u is not None)
        self.btn_estado.setText("Activar" if u is not None and not u.activo else "Desactivar")

    # -- acciones --------------------------------------------------------------------------------------
    def nuevo(self) -> None:
        dlg = UsuarioDialog(self.ctx, self.window())
        dlg.guardado.connect(lambda u: self._creado(u))
        self._abrir(dlg)

    def _creado(self, u: UsuarioOut) -> None:
        self.toast(f"Usuario «{u.usuario}» creado ({ROLES.get(u.rol, u.rol)})", "exito")
        self.recargar(silencioso=True)

    def _abrir(self, dlg: c.DialogoFormulario) -> None:
        self._dialogo = dlg
        dlg.finished.connect(lambda _=0: setattr(self, "_dialogo", None))
        dlg.open()

    def cambiar_password(self) -> None:
        u = self.seleccionado()
        if u is None:
            return
        dlg = PasswordDialog(self.ctx, u, self.window())
        dlg.guardado.connect(lambda _r, nombre=u.usuario: self._password_ok(nombre))
        self._abrir(dlg)

    def _password_ok(self, usuario: str) -> None:
        self.toast(f"Contraseña de «{usuario}» actualizada", "exito")
        self.recargar(silencioso=True)

    def alternar_estado(self) -> None:
        u = self.seleccionado()
        api = self.ctx.api
        if u is None or api is None:
            return
        activar = not u.activo
        if activar:
            texto = f"¿Activar al usuario «{u.usuario}»? Podrá volver a iniciar sesión."
        else:
            texto = (f"¿Desactivar al usuario «{u.usuario}»?\n\nNo podrá iniciar sesión y se cerrarán "
                     "sus sesiones abiertas.")
        if not c.confirmar(self.window(), "Activar usuario" if activar else "Desactivar usuario", texto,
                           "Activar" if activar else "Desactivar", peligro=not activar):
            return
        self.ctx.ejecutar(lambda: api.actualizar_usuario(u.id, UsuarioUpdate(activo=activar)),
                          lambda r: self._estado_ok(r), self._estado_error, self)

    def _estado_ok(self, u: UsuarioOut) -> None:
        self.toast(f"Usuario «{u.usuario}» {'activado' if u.activo else 'desactivado'}", "exito")
        self.recargar(silencioso=True)

    def _estado_error(self, exc: BaseException) -> None:
        self.toast(c.mensaje_api(exc), "error", 6000)
        self.recargar(silencioso=True)
