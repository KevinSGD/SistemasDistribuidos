from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query

from server.application.errores import ROL_ADMIN, ROL_COMPRADOR
from server.security.sesiones import Contexto
from shared.schemas import CompraIn, FacturaOut, MetodoPago, ResumenFacturasOut

from ..dependencias import requiere_rol, servicios
from ..servicios import Servicios

router = APIRouter(tags=["ventas"])
_cualquiera = requiere_rol(ROL_ADMIN, ROL_COMPRADOR)
_solo_admin = requiere_rol(ROL_ADMIN)


@router.post("/compras", response_model=FacturaOut, status_code=201)
def comprar(datos: CompraIn, ctx: Contexto = Depends(_cualquiera),
            srv: Servicios = Depends(servicios)):
    return srv.ventas.comprar(
        ctx.usuario_id, [i.model_dump() for i in datos.items], datos.cliente.model_dump(),
        datos.pago.model_dump(), ctx.rol)


# Las facturas son de SOLO LECTURA: no hay rutas para anular, editar ni borrar.
@router.get("/facturas", response_model=list[FacturaOut])
def historial(desde: datetime | None = None, hasta: datetime | None = None,
              q: str | None = Query(default=None, max_length=100),
              metodo_pago: MetodoPago | None = None,
              usuario_id: int | None = Query(default=None, ge=1),
              limite: int = Query(default=200, ge=1, le=1000),
              offset: int = Query(default=0, ge=0),
              ctx: Contexto = Depends(_cualquiera), srv: Servicios = Depends(servicios)):
    return srv.ventas.listar_facturas(ctx.usuario_id, ctx.rol, desde, hasta, limite, offset,
                                      q, metodo_pago, usuario_id)


# Declarada ANTES de /facturas/{numero} para que "resumen" no se interprete como un numero.
@router.get("/facturas/resumen", response_model=ResumenFacturasOut)
def resumen(desde: datetime | None = None, hasta: datetime | None = None,
            q: str | None = Query(default=None, max_length=100),
            metodo_pago: MetodoPago | None = None,
            usuario_id: int | None = Query(default=None, ge=1),
            ctx: Contexto = Depends(_solo_admin), srv: Servicios = Depends(servicios)):
    return srv.ventas.resumen_facturas(ctx.rol, desde, hasta, q, metodo_pago, usuario_id)


@router.get("/facturas/{numero}", response_model=FacturaOut)
def obtener(numero: str, ctx: Contexto = Depends(_cualquiera),
            srv: Servicios = Depends(servicios)):
    return srv.ventas.obtener_factura(numero, ctx.usuario_id, ctx.rol)
