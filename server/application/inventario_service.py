"""InventarioService: CRUD de productos. Mutaciones solo admin; lectura admin y comprador."""
from __future__ import annotations

import math
from dataclasses import replace
from datetime import datetime

from server.domain.entities import ProductoDominio
from server.domain.errors import NoEncontrado
from server.infrastructure.db.engine import sesion
from server.infrastructure.db.repos import DescuentoRepo, ProductoRepo

from . import consultas_extra
from .errores import ErrorValidacion, exigir_admin, exigir_autenticado
from .eventos import STOCK_ACTUALIZADO, EventBus, evento

CAMPOS = {"nombre", "categoria", "precio_base", "stock", "stock_maximo",
          "fecha_vencimiento", "activo"}


def _entero(campo: str, v, minimo: int = 0) -> int:
    if isinstance(v, bool) or not isinstance(v, (int, float, str)):
        raise ErrorValidacion(f"'{campo}' debe ser un entero", {"campo": campo})
    try:
        f = float(v)
    except ValueError:
        raise ErrorValidacion(f"'{campo}' debe ser un entero", {"campo": campo}) from None
    if not math.isfinite(f) or f != int(f) or int(f) < minimo:
        raise ErrorValidacion(f"'{campo}' debe ser un entero >= {minimo}", {"campo": campo})
    return int(f)


def _fecha(v) -> datetime | None:
    if v is None or v == "":
        return None
    if isinstance(v, datetime):
        return v.replace(tzinfo=None) if v.tzinfo else v
    if isinstance(v, str):
        try:
            d = datetime.fromisoformat(v)
            return d.replace(tzinfo=None) if d.tzinfo else d
        except ValueError:
            pass
    raise ErrorValidacion("fecha_vencimiento inválida (use ISO 8601)", {"campo": "fecha_vencimiento"})


def _normalizar(datos: dict) -> dict:
    out: dict = {}
    desconocidos = sorted(set(datos) - CAMPOS)
    if desconocidos:
        raise ErrorValidacion("Campos desconocidos", {"campos": desconocidos})
    if "nombre" in datos:
        n = datos["nombre"]
        if not isinstance(n, str) or not n.strip() or len(n.strip()) > 100:
            raise ErrorValidacion("El nombre es obligatorio (máx. 100)", {"campo": "nombre"})
        out["nombre"] = n.strip()
    if "categoria" in datos:
        c = datos["categoria"]
        if not isinstance(c, str) or len(c.strip()) > 50:
            raise ErrorValidacion("Categoría inválida (máx. 50)", {"campo": "categoria"})
        out["categoria"] = c.strip() or "General"
    if "precio_base" in datos:
        p = datos["precio_base"]
        if isinstance(p, bool) or not isinstance(p, (int, float)) or not math.isfinite(p) or p < 0:
            raise ErrorValidacion("precio_base debe ser un número >= 0", {"campo": "precio_base"})
        out["precio_base"] = round(float(p), 2)
    if "stock" in datos:
        out["stock"] = _entero("stock", datos["stock"])
    if "stock_maximo" in datos:
        out["stock_maximo"] = _entero("stock_maximo", datos["stock_maximo"])
    if "fecha_vencimiento" in datos:
        out["fecha_vencimiento"] = _fecha(datos["fecha_vencimiento"])
    if "activo" in datos:
        if not isinstance(datos["activo"], bool):
            raise ErrorValidacion("activo debe ser booleano", {"campo": "activo"})
        out["activo"] = datos["activo"]
    return out


class InventarioService:
    def __init__(self, sesion_factory, bus: EventBus | None = None):
        self._factory = sesion_factory
        self._bus = bus

    def _publicar_stock(self, p: ProductoDominio) -> None:
        if self._bus is not None:
            self._bus.publicar(evento(STOCK_ACTUALIZADO, {
                "producto_id": p.id, "stock": p.stock, "activo": p.activo}))

    def listar(self, rol: str | None, activos: bool | None = True) -> list[ProductoDominio]:
        exigir_autenticado(rol)
        with sesion(self._factory) as s:
            return consultas_extra.listar_productos(s, activos)

    def obtener(self, id: int, rol: str | None) -> ProductoDominio:
        exigir_autenticado(rol)
        with sesion(self._factory) as s:
            p = ProductoRepo(s).obtener(id)
        if p is None:
            raise NoEncontrado("Producto no encontrado", {"producto_id": id})
        return p

    def crear(self, datos: dict, rol: str | None) -> ProductoDominio:
        exigir_admin(rol)
        faltan = [c for c in ("nombre", "precio_base") if c not in datos]
        if faltan:
            raise ErrorValidacion("Faltan campos obligatorios", {"campos": faltan})
        v = _normalizar(datos)
        p = ProductoDominio(
            id=None, nombre=v["nombre"], categoria=v.get("categoria", "General"),
            precio_base=v["precio_base"], stock=v.get("stock", 0),
            stock_maximo=v.get("stock_maximo", 100),
            fecha_vencimiento=v.get("fecha_vencimiento"), activo=v.get("activo", True))
        with sesion(self._factory) as s:
            creado = ProductoRepo(s).crear(p)
        self._publicar_stock(creado)
        return creado

    def editar(self, id: int, cambios: dict, rol: str | None) -> ProductoDominio:
        exigir_admin(rol)
        if not cambios:
            raise ErrorValidacion("Sin cambios")
        v = _normalizar(cambios)
        with sesion(self._factory) as s:
            repo = ProductoRepo(s)
            actual = repo.obtener(id)
            if actual is None:
                raise NoEncontrado("Producto no encontrado", {"producto_id": id})
            nuevo = replace(actual, **v)
            guardado = repo.actualizar(nuevo)
            if not nuevo.activo:
                DescuentoRepo(s).desactivar(id)
        if guardado.stock != actual.stock or guardado.activo != actual.activo:
            self._publicar_stock(guardado)
        return guardado

    def dar_de_baja(self, id: int, rol: str | None) -> None:
        exigir_admin(rol)
        with sesion(self._factory) as s:
            repo = ProductoRepo(s)
            if repo.obtener(id) is None:
                raise NoEncontrado("Producto no encontrado", {"producto_id": id})
            repo.baja_logica(id)
            DescuentoRepo(s).desactivar(id)
            stock = consultas_extra.stock_fresco(s, id)
        self._publicar_stock(ProductoDominio(id, "", "", 0.0, stock or 0, 0, None, False))
