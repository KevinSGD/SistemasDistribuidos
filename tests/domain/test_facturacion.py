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
    t = calcular_totales([linea(100, 70, 1, 19.0)], decimales=2)  # centavos: capacidad explicita
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
        calcular_pago(calcular_totales([linea(100, 100, 1)], decimales=2), 99.5, decimales=2)
    assert ei.value.detalle["faltante"] == 0.5


def test_efectivo_insuficiente_pesos_enteros():
    with pytest.raises(EfectivoInsuficiente) as ei:
        calcular_pago(calcular_totales([linea(100, 100, 1)]), 99.4)
    assert ei.value.detalle["faltante"] == 1 and isinstance(ei.value.detalle["faltante"], int)


def test_compra_vacia():
    with pytest.raises(CantidadInvalida):
        calcular_totales([])


def test_iva_19_de_28320_pesos_enteros():
    # 28.320 * 19 % = 5.380,8 -> 5.381 (mitad hacia arriba, sin centavos)
    t = calcular_totales([linea(28320, 28320, 1, 19.0)])
    assert t.iva == 5381 and t.total == 33701 and t.base + t.iva == t.total
    assert all(isinstance(v, int) for v in (t.subtotal_sin_descuento, t.ahorro, t.base, t.iva, t.total))


def test_iva_mitad_hacia_arriba_no_al_par():
    # 50 * 5 % = 2,5 -> 3 (round() de Python daria 2)
    assert calcular_totales([linea(50, 50, 1, 5.0)]).iva == 3
