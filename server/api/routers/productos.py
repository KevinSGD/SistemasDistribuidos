from __future__ import annotations

from fastapi import APIRouter, Depends, Response

from server.application.errores import ROL_ADMIN, ROL_COMPRADOR
from server.security.sesiones import Contexto
from shared.schemas import ItemRiesgo, ProductoIn, ProductoOut, ProductoUpdate

from ..dependencias import requiere_rol, servicios
from ..servicios import Servicios

router = APIRouter(tags=["productos"])
_admin = requiere_rol(ROL_ADMIN)
_cualquiera = requiere_rol(ROL_ADMIN, ROL_COMPRADOR)


@router.get("/productos", response_model=list[ProductoOut])
def listar(activos: bool | None = True, ctx: Contexto = Depends(_cualquiera),
           srv: Servicios = Depends(servicios)):
    return srv.inventario.listar(ctx.rol, activos)


@router.post("/productos", response_model=ProductoOut, status_code=201)
def crear(datos: ProductoIn, ctx: Contexto = Depends(_admin), srv: Servicios = Depends(servicios)):
    return srv.inventario.crear(datos.model_dump(), ctx.rol)


@router.put("/productos/{id}", response_model=ProductoOut)
def editar(id: int, datos: ProductoUpdate, ctx: Contexto = Depends(_admin),
           srv: Servicios = Depends(servicios)):
    return srv.inventario.editar(id, datos.model_dump(exclude_unset=True), ctx.rol)


@router.delete("/productos/{id}", status_code=204)
def baja(id: int, ctx: Contexto = Depends(_admin), srv: Servicios = Depends(servicios)):
    srv.inventario.dar_de_baja(id, ctx.rol)
    return Response(status_code=204)


@router.get("/ofertas", response_model=list[ItemRiesgo])
def ofertas(ctx: Contexto = Depends(_cualquiera), srv: Servicios = Depends(servicios)):
    return srv.riesgo.ofertas(ctx.rol)
