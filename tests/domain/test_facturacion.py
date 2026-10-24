import pytest

from server.domain.errors import CantidadInvalida, EfectivoInsuficiente
from server.domain.facturacion import calcular_pago, calcular_totales
from server.domain.ventas import LineaCalculada


def linea(orig, unit, cant, iva=0.0):
    return LineaCalculada(1, "x", cant, orig, 0, unit, round(unit * cant, 2),
                          round((orig - unit) * cant, 2), iva)


def test_totales_exentos():
    t = calcular_totales([linea(100, 50, 2), linea(10, 10, 1)])
    assert (t.subtotal_sin_descuento, t.ahorro, t.base, t.iva, t.total) == (210, 100, 110, 0, 110)
    assert t.iva_por_tasa == {}


def test_iva_desglosado():
    t = calcular_totales([linea(100, 100, 1, 19.0), linea(100, 100, 1, 5.0), linea(10, 10, 1)])
    assert t.iva_por_tasa == {5.0: 5.0, 19.0: 19.0}
    assert t.iva == 24.0 and t.total == 234.0


def test_iva_sobre_precio_con_descuento():
    t = calcular_totales([linea(100, 70, 1, 19.0)])
    assert t.iva == 13.3 and t.total == 83.3 and t.ahorro == 30


def test_decimales_cop():
    t = calcular_totales([linea(1000, 700, 1, 19.0)], decimales=0)
    assert t.iva == 133 and t.total == 833


def test_cambio():
    t = calcular_pago(calcular_totales([linea(100, 100, 1)]), 150)
    assert t.cambio == 50 and t.efectivo == 150


def test_efectivo_exacto():
    assert calcular_pago(calcular_totales([linea(100, 100, 1)]), 100).cambio == 0


def test_efectivo_insuficiente():
    with pytest.raises(EfectivoInsuficiente) as ei:
        calcular_pago(calcular_totales([linea(100, 100, 1)]), 99.5)
    assert ei.value.detalle["faltante"] == 0.5


def test_compra_vacia():
    with pytest.raises(CantidadInvalida):
        calcular_totales([])
