"""Logica pura del carrito del comprador (sin Qt, sin red): reglas de stock y totales.

El precio/stock de cada linea es una FOTO de lo ultimo que informo el servidor (`/ofertas` o un
evento WS). `sincronizar()` la actualiza y devuelve los `Cambio` que la vista debe avisar. El total
aqui es la base sin IVA; el IVA y la factura final los calcula siempre el servidor."""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Iterable

TIPO_NO_DISPONIBLE = "no_disponible"
TIPO_STOCK_REDUCIDO = "stock_reducido"
TIPO_PRECIO = "precio_cambiado"
TIPO_RECUPERADO = "disponible_de_nuevo"


def r2(valor: float) -> float:
    return round(float(valor) + 0.0, 2)


@dataclass
class LineaCarrito:
    producto_id: int
    nombre: str
    categoria: str
    precio_original: float
    precio_final: float
    descuento: float
    stock: int
    cantidad: int
    motivo: str = ""
    nivel: str = "normal"
    disponible: bool = True
    precio_anterior: float | None = None      # precio final previo, si cambio y no se reconocio
    cantidad_anterior: int | None = None      # cantidad previa, si se recorto por stock

    @property
    def subtotal_original(self) -> float:
        return r2(self.precio_original * self.cantidad)

    @property
    def subtotal_final(self) -> float:
        return r2(self.precio_final * self.cantidad)

    @property
    def ahorro(self) -> float:
        return r2(self.subtotal_original - self.subtotal_final)

    @property
    def con_aviso(self) -> bool:
        return (not self.disponible) or self.precio_anterior is not None \
            or self.cantidad_anterior is not None

    @property
    def texto_aviso(self) -> str:
        if not self.disponible:
            return "Ya no está disponible. Quítalo para continuar."
        partes = []
        if self.precio_anterior is not None:
            partes.append(f"Cambió el precio (antes {self.precio_anterior:g})")
        if self.cantidad_anterior is not None:
            partes.append(f"Solo quedan {self.stock} (pediste {self.cantidad_anterior})")
        return ". ".join(partes)


@dataclass(frozen=True)
class Resultado:
    ok: bool
    mensaje: str = ""


@dataclass(frozen=True)
class Cambio:
    producto_id: int
    nombre: str
    tipo: str
    mensaje: str


def _campo(o: Any, nombre: str, defecto=None):
    if isinstance(o, dict):
        return o.get(nombre, defecto)
    return getattr(o, nombre, defecto)


class Carrito:
    """Orden de insercion estable. Nunca permite cantidad > stock conocido."""

    def __init__(self) -> None:
        self._lineas: dict[int, LineaCarrito] = {}

    # -- consulta -------------------------------------------------------------------------
    def __len__(self) -> int:
        return len(self._lineas)

    def __contains__(self, producto_id: int) -> bool:
        return producto_id in self._lineas

    @property
    def lineas(self) -> list[LineaCarrito]:
        return list(self._lineas.values())

    def linea(self, producto_id: int) -> LineaCarrito | None:
        return self._lineas.get(producto_id)

    def cantidad_de(self, producto_id: int) -> int:
        l = self._lineas.get(producto_id)
        return l.cantidad if l else 0

    @property
    def cantidad_total(self) -> int:
        return sum(l.cantidad for l in self._lineas.values())

    @property
    def subtotal(self) -> float:
        """Suma a precio original (sin descuento)."""
        return r2(sum(l.subtotal_original for l in self._lineas.values()))

    @property
    def total(self) -> float:
        """Suma a precio con descuento, antes de IVA."""
        return r2(sum(l.subtotal_final for l in self._lineas.values()))

    @property
    def ahorro(self) -> float:
        return r2(self.subtotal - self.total)

    @property
    def hay_problemas(self) -> bool:
        """Hay lineas que ya no se pueden comprar (impide pagar)."""
        return any(not l.disponible for l in self._lineas.values())

    @property
    def hay_avisos(self) -> bool:
        return any(l.con_aviso for l in self._lineas.values())

    def snapshot(self) -> list[LineaCarrito]:
        return [replace(l) for l in self._lineas.values()]

    def items_compra(self) -> list[dict]:
        return [{"producto_id": l.producto_id, "cantidad": l.cantidad}
                for l in self._lineas.values()]

    # -- edicion --------------------------------------------------------------------------
    def agregar(self, oferta: Any) -> Resultado:
        """Agrega una unidad de `oferta` (ItemRiesgo o dict). Falla si superaria el stock."""
        pid = int(_campo(oferta, "producto_id"))
        nombre = _campo(oferta, "nombre", "")
        stock = int(_campo(oferta, "stock", 0))
        if stock <= 0:
            return Resultado(False, f"{nombre} está agotado.")
        l = self._lineas.get(pid)
        if l is None:
            self._lineas[pid] = LineaCarrito(
                producto_id=pid, nombre=nombre, categoria=_campo(oferta, "categoria", ""),
                precio_original=float(_campo(oferta, "precio_original", 0)),
                precio_final=float(_campo(oferta, "precio_final", 0)),
                descuento=float(_campo(oferta, "descuento", 0)), stock=stock, cantidad=1,
                motivo=_campo(oferta, "motivo", ""), nivel=_campo(oferta, "nivel", "normal"))
            return Resultado(True)
        self._copiar_datos(l, oferta)          # la tarjeta trae lo mas reciente
        if l.cantidad >= l.stock:
            return Resultado(False, f"Solo hay {l.stock} unidades disponibles de {nombre}.")
        l.cantidad += 1
        return Resultado(True)

    def cambiar(self, producto_id: int, delta: int) -> Resultado:
        """Suma/resta unidades. Si llega a 0 la linea se elimina."""
        l = self._lineas.get(producto_id)
        if l is None:
            return Resultado(False, "El producto no está en el carrito.")
        nueva = l.cantidad + delta
        if nueva <= 0:
            del self._lineas[producto_id]
            return Resultado(True)
        if nueva > l.stock:
            return Resultado(False, f"Solo hay {l.stock} unidades disponibles de {l.nombre}.")
        l.cantidad = nueva
        l.cantidad_anterior = None             # el usuario ya vio el ajuste
        return Resultado(True)

    def quitar(self, producto_id: int) -> bool:
        return self._lineas.pop(producto_id, None) is not None

    def vaciar(self) -> None:
        self._lineas.clear()

    def reconocer(self) -> None:
        """El usuario ya vio los avisos de precio/cantidad (los no disponibles siguen)."""
        for l in self._lineas.values():
            l.precio_anterior = None
            l.cantidad_anterior = None

    # -- sincronizacion con el servidor ----------------------------------------------------
    @staticmethod
    def _copiar_datos(l: LineaCarrito, o: Any) -> None:
        l.nombre = _campo(o, "nombre", l.nombre)
        l.categoria = _campo(o, "categoria", l.categoria)
        l.precio_original = float(_campo(o, "precio_original", l.precio_original))
        l.precio_final = float(_campo(o, "precio_final", l.precio_final))
        l.descuento = float(_campo(o, "descuento", l.descuento))
        l.stock = int(_campo(o, "stock", l.stock))
        l.motivo = _campo(o, "motivo", l.motivo)
        l.nivel = _campo(o, "nivel", l.nivel)

    def _recortar(self, l: LineaCarrito, cambios: list[Cambio]) -> None:
        if l.disponible and l.cantidad > l.stock > 0:
            if l.cantidad_anterior is None:
                l.cantidad_anterior = l.cantidad
            pedida = l.cantidad
            l.cantidad = l.stock
            cambios.append(Cambio(l.producto_id, l.nombre, TIPO_STOCK_REDUCIDO,
                                  f"{l.nombre}: solo quedan {l.stock} (tenías {pedida}). "
                                  "Ajustamos la cantidad."))

    def sincronizar(self, ofertas: Iterable[Any]) -> list[Cambio]:
        """Ajusta las lineas a la lista vigente de ofertas. Una linea que ya no aparece queda
        marcada como no disponible (se agoto, vencio o perdio la oferta)."""
        por_id = {int(_campo(o, "producto_id")): o for o in ofertas}
        cambios: list[Cambio] = []
        for pid, l in self._lineas.items():
            o = por_id.get(pid)
            if o is None:
                if l.disponible:
                    l.disponible = False
                    l.stock = 0
                    cambios.append(Cambio(pid, l.nombre, TIPO_NO_DISPONIBLE,
                                          f"{l.nombre} ya no está disponible. Quítalo del carrito."))
                continue
            antes = l.precio_final
            volvio = not l.disponible
            self._copiar_datos(l, o)
            l.disponible = True
            if volvio:
                cambios.append(Cambio(pid, l.nombre, TIPO_RECUPERADO,
                                      f"{l.nombre} volvió a estar disponible."))
            if abs(l.precio_final - antes) > 0.004:
                if l.precio_anterior is None:
                    l.precio_anterior = antes
                cambios.append(Cambio(pid, l.nombre, TIPO_PRECIO,
                                      f"{l.nombre}: el precio cambió de {antes:g} a "
                                      f"{l.precio_final:g}."))
            self._recortar(l, cambios)
        return cambios

    def aplicar_stock(self, producto_id: int, stock: int, activo: bool = True) -> list[Cambio]:
        """Evento `stock_actualizado` de un producto."""
        l = self._lineas.get(producto_id)
        if l is None:
            return []
        cambios: list[Cambio] = []
        l.stock = max(0, int(stock))
        if l.stock == 0 or not activo:
            if l.disponible:
                l.disponible = False
                l.stock = 0
                cambios.append(Cambio(producto_id, l.nombre, TIPO_NO_DISPONIBLE,
                                      f"{l.nombre} se agotó. Quítalo del carrito."))
            return cambios
        self._recortar(l, cambios)
        return cambios

    def rechazo_servidor(self, producto_id: int | None, codigo: str,
                         disponible: int | None = None) -> list[Cambio]:
        """Ajusta el carrito tras un 409 de la compra (stock insuficiente / vencido / inactivo)."""
        l = self._lineas.get(producto_id) if producto_id is not None else None
        if l is None:
            return []
        if codigo == "STOCK_INSUFICIENTE" and disponible:
            return self.aplicar_stock(producto_id, disponible)
        l.disponible = False
        l.stock = 0
        return [Cambio(producto_id, l.nombre, TIPO_NO_DISPONIBLE,
                       f"{l.nombre} ya no se puede comprar. Quítalo del carrito.")]
