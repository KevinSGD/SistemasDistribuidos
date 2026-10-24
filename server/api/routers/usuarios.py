from __future__ import annotations

from fastapi import APIRouter, Depends

from server.application.errores import ROL_ADMIN
from server.security.sesiones import Contexto
from shared.schemas import UsuarioIn, UsuarioOut, UsuarioUpdate

from ..dependencias import requiere_rol, servicios
from ..servicios import Servicios

router = APIRouter(prefix="/usuarios", tags=["usuarios"])
_admin = requiere_rol(ROL_ADMIN)


@router.get("", response_model=list[UsuarioOut])
def listar(ctx: Contexto = Depends(_admin), srv: Servicios = Depends(servicios)):
    return srv.usuarios.listar(ctx.rol)


@router.post("", response_model=UsuarioOut, status_code=201)
def crear(datos: UsuarioIn, ctx: Contexto = Depends(_admin), srv: Servicios = Depends(servicios)):
    return srv.usuarios.crear(datos.nombre, datos.usuario, datos.password, datos.rol, ctx.rol)


@router.put("/{id}", response_model=UsuarioOut)
def actualizar(id: int, datos: UsuarioUpdate, ctx: Contexto = Depends(_admin),
               srv: Servicios = Depends(servicios)):
    return srv.usuarios.actualizar(id, datos.model_dump(exclude_unset=True), ctx.rol,
                                   ctx.usuario_id)
