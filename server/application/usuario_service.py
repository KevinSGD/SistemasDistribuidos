"""UsuarioService: gestion de usuarios (solo admin). Sin FastAPI ni SQLAlchemy directo.

El hash de contrasenas y el cierre de sesiones se inyectan (los implementa `security`)."""
from __future__ import annotations

from typing import Callable

from server.domain.errors import ErrorDominio, NoEncontrado
from server.infrastructure.db.engine import sesion
from server.infrastructure.db.repos import UsuarioDTO, UsuarioRepo

from .errores import ROL_ADMIN, ROL_COMPRADOR, ErrorValidacion, exigir_admin

PASSWORD_MIN = 8


class UsuarioDuplicado(ErrorDominio):
    codigo, http = "USUARIO_DUPLICADO", 409


def _validar_password(pw) -> str:
    if not isinstance(pw, str) or len(pw) < PASSWORD_MIN:
        raise ErrorValidacion(f"La contraseña debe tener al menos {PASSWORD_MIN} caracteres",
                              {"campo": "password", "minimo": PASSWORD_MIN})
    return pw


class UsuarioService:
    def __init__(self, sesion_factory, hashear: Callable[[str], str],
                 cerrar_sesiones: Callable[[int, str], int]):
        self._factory = sesion_factory
        self._hashear = hashear
        self._cerrar = cerrar_sesiones

    def listar(self, rol: str | None) -> list[UsuarioDTO]:
        exigir_admin(rol)
        with sesion(self._factory) as s:
            return UsuarioRepo(s).listar()

    def crear(self, nombre: str, usuario: str, password: str, rol_nuevo: str,
              rol: str | None) -> UsuarioDTO:
        exigir_admin(rol)
        if rol_nuevo not in (ROL_ADMIN, ROL_COMPRADOR):
            raise ErrorValidacion("Rol inválido", {"validos": [ROL_ADMIN, ROL_COMPRADOR]})
        usuario = (usuario or "").strip()
        if len(usuario) < 3 or not (nombre or "").strip():
            raise ErrorValidacion("Nombre y usuario (mín. 3 caracteres) son obligatorios")
        h = self._hashear(_validar_password(password))
        with sesion(self._factory) as s:
            repo = UsuarioRepo(s)
            if repo.obtener_por_usuario(usuario) is not None:
                raise UsuarioDuplicado("Ya existe un usuario con ese nombre de usuario",
                                       {"usuario": usuario})
            return repo.crear(nombre.strip(), usuario, h, rol=rol_nuevo)

    def actualizar(self, id: int, cambios: dict, rol: str | None, actor_id: int) -> UsuarioDTO:
        """cambios admite: nombre, rol, activo, password. Un admin no puede desactivarse ni
        quitarse el rol a si mismo (evita quedarse sin acceso)."""
        exigir_admin(rol)
        if not cambios:
            raise ErrorValidacion("Sin cambios")
        if id == actor_id and (cambios.get("activo") is False
                               or cambios.get("rol", ROL_ADMIN) != ROL_ADMIN):
            raise ErrorValidacion("No puede desactivarse ni cambiar su propio rol",
                                  {"usuario_id": id})
        if "rol" in cambios and cambios["rol"] not in (ROL_ADMIN, ROL_COMPRADOR):
            raise ErrorValidacion("Rol inválido", {"validos": [ROL_ADMIN, ROL_COMPRADOR]})
        h = self._hashear(_validar_password(cambios["password"])) \
            if cambios.get("password") is not None else None
        with sesion(self._factory) as s:
            repo = UsuarioRepo(s)
            previo = repo.obtener(id)
            if previo is None:
                raise NoEncontrado("Usuario no encontrado", {"usuario_id": id})
            nuevo = repo.actualizar(id, nombre=cambios.get("nombre"), rol=cambios.get("rol"),
                                    activo=cambios.get("activo"), password_hash=h)
        if cambios.get("activo") is False and previo.activo:
            self._cerrar(id, "usuario_desactivado")
        elif h is not None and id != actor_id:
            self._cerrar(id, "password_cambiada")
        elif cambios.get("rol") and cambios["rol"] != previo.rol:
            self._cerrar(id, "rol_cambiado")  # el JWT lleva el rol: obliga a re-login
        return nuevo
