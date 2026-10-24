"""Totales de una compra. El precio NO incluye IVA: el IVA se suma sobre el precio con descuento."""
from dataclasses import dataclass, field
from typing import Sequence

from .dinero import dec, redondear
from .errors import CantidadInvalida, EfectivoInsuficiente
from .ventas import LineaCalculada


@dataclass(frozen=True)
class TotalesCompra:
    subtotal_sin_descuento: float
    ahorro: float
    base: float                                   # subtotal_sin_descuento - ahorro
    iva_por_tasa: dict[float, float] = field(default_factory=dict)  # {tasa%: monto}
    iva: float = 0.0
    total: float = 0.0
    efectivo: float | None = None
    cambio: float | None = None


def calcular_totales(lineas: Sequence[LineaCalculada], decimales: int = 0) -> TotalesCompra:
    if not lineas:
        raise CantidadInvalida("La compra no tiene líneas")
    sub = redondear(sum(l.precio_original * l.cantidad for l in lineas), decimales)
    ahorro = redondear(sum(l.ahorro for l in lineas), decimales)
    base = redondear(sum(l.subtotal for l in lineas), decimales)
    bases: dict[float, float] = {}
    for l in lineas:
        bases[l.tasa_iva] = bases.get(l.tasa_iva, 0.0) + l.subtotal
    iva_por_tasa = {t: redondear(dec(b) * dec(t) / 100, decimales) for t, b in sorted(bases.items()) if t > 0}
    iva = redondear(sum(iva_por_tasa.values()), decimales)
    return TotalesCompra(sub, ahorro, base, iva_por_tasa, iva, redondear(base + iva, decimales))


def calcular_pago(totales: TotalesCompra, efectivo: float, decimales: int = 0) -> TotalesCompra:
    efectivo = redondear(efectivo, decimales)
    if efectivo < totales.total:
        raise EfectivoInsuficiente(
            "El efectivo recibido es menor que el total",
            {"total": totales.total, "efectivo": efectivo,
             "faltante": redondear(totales.total - efectivo, decimales)})
    return TotalesCompra(totales.subtotal_sin_descuento, totales.ahorro, totales.base,
                         totales.iva_por_tasa, totales.iva, totales.total,
                         efectivo, redondear(efectivo - totales.total, decimales))
