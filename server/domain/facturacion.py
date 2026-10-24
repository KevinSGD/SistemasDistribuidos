"""Totales de una compra. El precio NO incluye IVA: el IVA se suma sobre el precio con descuento."""
from dataclasses import dataclass, field
from typing import Sequence

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


def calcular_totales(lineas: Sequence[LineaCalculada], decimales: int = 2) -> TotalesCompra:
    if not lineas:
        raise CantidadInvalida("La compra no tiene líneas")
    sub = round(sum(l.precio_original * l.cantidad for l in lineas), decimales)
    ahorro = round(sum(l.ahorro for l in lineas), decimales)
    base = round(sum(l.subtotal for l in lineas), decimales)
    bases: dict[float, float] = {}
    for l in lineas:
        bases[l.tasa_iva] = bases.get(l.tasa_iva, 0.0) + l.subtotal
    iva_por_tasa = {t: round(b * t / 100, decimales) for t, b in sorted(bases.items()) if t > 0}
    iva = round(sum(iva_por_tasa.values()), decimales)
    return TotalesCompra(sub, ahorro, base, iva_por_tasa, iva, round(base + iva, decimales))


def calcular_pago(totales: TotalesCompra, efectivo: float, decimales: int = 2) -> TotalesCompra:
    efectivo = round(efectivo, decimales)
    if efectivo < totales.total:
        raise EfectivoInsuficiente(
            "El efectivo recibido es menor que el total",
            {"total": totales.total, "efectivo": efectivo,
             "faltante": round(totales.total - efectivo, decimales)})
    return TotalesCompra(totales.subtotal_sin_descuento, totales.ahorro, totales.base,
                         totales.iva_por_tasa, totales.iva, totales.total,
                         efectivo, round(efectivo - totales.total, decimales))
