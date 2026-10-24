"""Errores propios de la capa de aplicacion (mismo contrato que domain.errors)."""
from server.domain.errors import ErrorDominio

ROL_ADMIN = "admin"
ROL_COMPRADOR = "comprador"


class RolNoPermitido(ErrorDominio):
    codigo, http = "ROL_NO_PERMITIDO", 403


class ErrorValidacion(ErrorDominio):
    codigo, http = "VALIDACION", 422


def exigir_admin(rol: str | None) -> None:
    if rol != ROL_ADMIN:
        raise RolNoPermitido("Se requiere rol administrador", {"rol": rol})


def exigir_autenticado(rol: str | None) -> None:
    if rol not in (ROL_ADMIN, ROL_COMPRADOR):
        raise RolNoPermitido("Rol no permitido", {"rol": rol})
