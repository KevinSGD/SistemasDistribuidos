from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query

from server.application.errores import ROL_ADMIN, ROL_COMPRADOR
from server.security.sesiones import Contexto
from shared.schemas import CompraIn, FacturaOut

from ..dependencias import requiere_rol, servicios
from ..servicios import Servicios

router = APIRouter(tags=["ventas"])
_cualquiera = requiere_rol(ROL_ADMIN, ROL_COMPRADOR)


@router.post("/compras", response_model=FacturaOut, status_code=201)
def comprar(datos: CompraIn, ctx: Contexto = Depends(_cualquiera),
            srv: Servicios = Depends(servicios)):
    return srv.ventas.comprar(
        ctx.usuario_id, [i.model_dump() for i in datos.items], datos.cliente.model_dump(),
        datos.pago.model_dump(), ctx.rol)


@router.get("/facturas", response_model=list[FacturaOut])
def historial(desde: datetime | None = None, hasta: datetime | None = None,
              limite: int | None = Query(default=None, ge=1, le=1000),
              ctx: Contexto = Depends(_cualquiera), srv: Servicios = Depends(servicios)):
    return srv.ventas.listar_facturas(ctx.usuario_id, ctx.rol, desde, hasta, limite)


@router.get("/facturas/{numero}", response_model=FacturaOut)
def obtener(numero: str, ctx: Contexto = Depends(_cualquiera),
            srv: Servicios = Depends(servicios)):
    return srv.ventas.obtener_factura(numero, ctx.usuario_id, ctx.rol)
