"""Redondeo monetario unico del sistema (servidor y cliente): mitad hacia arriba (ROUND_HALF_UP), no el 'banker's
rounding' de round(). Pesos colombianos: 0 decimales por defecto."""
from decimal import ROUND_HALF_UP, Decimal


def dec(valor: float | int | Decimal) -> Decimal:
    """Decimal exacto a partir de la representacion decimal corta del float."""
    return valor if isinstance(valor, Decimal) else Decimal(repr(float(valor)))


def redondear(valor: float | int | Decimal, decimales: int = 0) -> int | float:
    """Redondea `valor` a `decimales` con mitad hacia arriba. Devuelve int si decimales == 0.

    Se parte de repr() del float (la forma decimal mas corta) para que 2.675 se trate como
    2.675 y no como 2.67499999..., de modo que el resultado coincida con lo que ve el usuario.
    """
    d = dec(valor)
    if decimales <= 0:
        return int(d.quantize(Decimal(1), rounding=ROUND_HALF_UP))
    q = Decimal(1).scaleb(-decimales)
    return float(d.quantize(q, rounding=ROUND_HALF_UP))
