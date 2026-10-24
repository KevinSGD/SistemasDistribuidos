from __future__ import annotations

from fastapi import APIRouter, Depends

from server.application.errores import ROL_ADMIN, ROL_COMPRADOR
from server.security.sesiones import Contexto
from shared.schemas import ConfigOut, ConfigPublicaOut, ConfigUpdate

from ..dependencias import requiere_rol, servicios
from ..servicios import Servicios

router = APIRouter(prefix="/config", tags=["config"])
_admin = requiere_rol(ROL_ADMIN)


@router.get("", response_model=ConfigOut)
def obtener(ctx: Contexto = Depends(_admin), srv: Servicios = Depends(servicios)):
    return srv.config.obtener_todo(ctx.rol)


@router.put("", response_model=ConfigOut)
def actualizar(datos: ConfigUpdate, ctx: Contexto = Depends(_admin),
               srv: Servicios = Depends(servicios)):
    return srv.config.actualizar(datos.model_dump(exclude_unset=True), ctx.rol)


@router.get("/publica", response_model=ConfigPublicaOut)
def publica(_: Contexto = Depends(requiere_rol(ROL_ADMIN, ROL_COMPRADOR)),
            srv: Servicios = Depends(servicios)):
    return srv.config.obtener_publica()
