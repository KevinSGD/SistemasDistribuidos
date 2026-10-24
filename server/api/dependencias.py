"""Dependencias FastAPI. `usuario_actual` NO renueva actividad (solo /auth/actividad y login)."""
from __future__ import annotations

from fastapi import Depends, Header, Request

from server.security.dependencias import extraer_bearer, requiere_rol as _verificador_rol
from server.security.sesiones import Contexto

from .servicios import Servicios


def servicios(request: Request) -> Servicios:
    return request.app.state.servicios


def token_actual(authorization: str | None = Header(default=None)) -> str:
    return extraer_bearer(authorization)


def usuario_actual(token: str = Depends(token_actual),
                   srv: Servicios = Depends(servicios)) -> Contexto:
    return srv.auth.validar_token(token)


def requiere_rol(*roles: str):
    """Dependencia: autenticado y con uno de `roles` (403 ROL_NO_PERMITIDO si no)."""
    verificar = _verificador_rol(*roles)

    def dependencia(ctx: Contexto = Depends(usuario_actual)) -> Contexto:
        return verificar(ctx)

    return dependencia
