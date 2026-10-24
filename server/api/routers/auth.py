from __future__ import annotations

from fastapi import APIRouter, Depends

from server.application.eventos import SESION_CERRADA, evento
from server.security.sesiones import Contexto
from shared.schemas import ActividadOut, LoginIn, LoginOut, MensajeOut, SesionOut

from ..dependencias import servicios, usuario_actual
from ..servicios import Servicios

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=LoginOut)
def login(datos: LoginIn, srv: Servicios = Depends(servicios)):
    return srv.auth.login(datos.usuario, datos.password)


@router.post("/actividad", response_model=ActividadOut)
def actividad(ctx: Contexto = Depends(usuario_actual), srv: Servicios = Depends(servicios)):
    """Unico endpoint (junto con el login) que renueva la actividad."""
    return {"segundos_restantes": srv.auth.registrar_actividad(ctx)}


@router.get("/sesion", response_model=SesionOut)
def sesion(ctx: Contexto = Depends(usuario_actual), srv: Servicios = Depends(servicios)):
    """Estado sin renovar."""
    return srv.auth.estado_sesion(ctx).__dict__


@router.post("/logout", response_model=MensajeOut)
def logout(ctx: Contexto = Depends(usuario_actual), srv: Servicios = Depends(servicios)):
    srv.auth.logout(ctx)
    # AuthService.logout no publica; se avisa al usuario para que sus sockets lo noten al instante
    srv.bus.publicar(evento(SESION_CERRADA, {"motivo": "logout"}, {"usuario_id": ctx.usuario_id}))
    return MensajeOut()
