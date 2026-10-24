from __future__ import annotations

from fastapi import APIRouter, Depends

from server.application.errores import ROL_ADMIN
from server.security.sesiones import Contexto
from shared.schemas import AlertasOut, EscaneoOut, ResumenRiesgoOut

from ..dependencias import requiere_rol, servicios
from ..servicios import Servicios

router = APIRouter(prefix="/riesgo", tags=["riesgo"])
_admin = requiere_rol(ROL_ADMIN)


@router.get("/resumen", response_model=ResumenRiesgoOut)
def resumen(ctx: Contexto = Depends(_admin), srv: Servicios = Depends(servicios)):
    return srv.riesgo.resumen_dashboard(ctx.rol)


@router.get("/alertas", response_model=AlertasOut)
def alertas(ctx: Contexto = Depends(_admin), srv: Servicios = Depends(servicios)):
    return srv.riesgo.alertas_por_severidad(ctx.rol)


@router.post("/escaneo", response_model=EscaneoOut)
def escaneo(ctx: Contexto = Depends(_admin), srv: Servicios = Depends(servicios)):
    return srv.riesgo.escanear_manual(ctx.rol)
