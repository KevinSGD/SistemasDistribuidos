"""Validaciones y calculo de lineas de venta. Funciones puras."""
from dataclasses import dataclass
from datetime import datetime

from .entities import EvaluacionRiesgo, ProductoDominio
from .dinero import redondear
from .errors import CantidadInvalida, ProductoInactivo, ProductoVencido, StockInsuficiente
from .riesgo import esta_vencido


@dataclass(frozen=True)
class LineaCalculada:
    producto_id: int | None
    nombre: str
    cantidad: int
    precio_original: float
    descuento: float
    precio_unitario: float
    subtotal: float          # cantidad * precio_unitario (con descuento)
    ahorro: float            # cantidad * (precio_original - precio_unitario)
    tasa_iva: float = 0.0    # porcentaje 0-100; 0 = exento


def puede_venderse(producto: ProductoDominio, ahora: datetime) -> bool:
    return producto.activo and not esta_vencido(producto, ahora)


def validar_linea(producto: ProductoDominio, cantidad: int, ahora: datetime) -> None:
    if isinstance(cantidad, bool) or not isinstance(cantidad, int) or cantidad <= 0:
        raise CantidadInvalida("La cantidad debe ser un entero mayor que 0",
                               {"producto_id": producto.id, "solicitado": cantidad})
    if not producto.activo:
        raise ProductoInactivo(f"El producto '{producto.nombre}' está inactivo",
                               {"producto_id": producto.id})
    if esta_vencido(producto, ahora):
        raise ProductoVencido(f"El producto '{producto.nombre}' está vencido",
                              {"producto_id": producto.id,
                               "fecha_vencimiento": producto.fecha_vencimiento.isoformat()})
    if cantidad > producto.stock:
        raise StockInsuficiente(
            f"Stock insuficiente para '{producto.nombre}'",
            {"producto_id": producto.id, "disponible": producto.stock, "solicitado": cantidad})


def calcular_linea(producto: ProductoDominio, cantidad: int,
                   evaluacion: EvaluacionRiesgo, tasa_iva: float = 0.0,
                   decimales: int = 0) -> LineaCalculada:
    """El precio unitario final se redondea primero; subtotal y ahorro derivan de el."""
    unitario = redondear(evaluacion.precio_final, decimales)
    original = redondear(evaluacion.precio_original, decimales)
    return LineaCalculada(
        producto_id=producto.id, nombre=producto.nombre, cantidad=cantidad,
        precio_original=original, descuento=evaluacion.descuento,
        precio_unitario=unitario,
        subtotal=redondear(unitario * cantidad, decimales),
        ahorro=redondear((original - unitario) * cantidad, decimales),
        tasa_iva=tasa_iva,
    )
