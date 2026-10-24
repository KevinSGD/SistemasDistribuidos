"""Utilidades puras (sin FastAPI) para la capa API."""
from __future__ import annotations

from typing import Callable

from .errores import RolNoPermitido, TokenInvalido
from .sesiones import Contexto


def extraer_bearer(header: str | None) -> str:
    """Parsea `Authorization: Bearer <token>`. Lanza TokenInvalido si falta o esta mal formado."""
    if not header:
        raise TokenInvalido("Falta el encabezado Authorization")
    partes = header.strip().split()
    if len(partes) != 2 or partes[0].lower() != "bearer" or not partes[1]:
        raise TokenInvalido("Encabezado Authorization mal formado")
    return partes[1]


def requiere_rol(*roles: str) -> Callable[[Contexto], Contexto]:
    """Devuelve un verificador: contexto -> contexto o RolNoPermitido (403)."""
    permitidos = frozenset(roles)

    def verificar(ctx: Contexto) -> Contexto:
        if ctx.rol not in permitidos:
            raise RolNoPermitido("Rol no permitido para esta operacion",
                                 {"requerido": sorted(permitidos)})
        return ctx

    return verificar
