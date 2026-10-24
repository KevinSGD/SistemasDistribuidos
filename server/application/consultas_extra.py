"""Consultas que faltan en los repos de infraestructura (no se modifica infrastructure).
Adaptador minimo; si se migra a ProductoRepo, borrar este modulo."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from server.domain.entities import ProductoDominio
from server.infrastructure.db.orm import ProductoORM
from server.infrastructure.db.repos import ProductoRepo, _producto


def listar_productos(s: Session, activos: bool | None = None) -> list[ProductoDominio]:
    """activos: True solo activos, False solo inactivos, None todos."""
    if activos is True:
        return ProductoRepo(s).listar_activos()
    q = select(ProductoORM).order_by(ProductoORM.nombre)
    if activos is False:
        q = q.where(ProductoORM.activo.is_(False))
    return [_producto(o) for o in s.scalars(q)]


def stock_fresco(s: Session, producto_id: int) -> int | None:
    """Lee el stock directo de la BD (evita el identity map tras un UPDATE masivo)."""
    return s.scalar(select(ProductoORM.stock).where(ProductoORM.id == producto_id))
