from datetime import datetime, timedelta

import pytest

from server.domain.entities import PoliticaRiesgo, ProductoDominio
from server.domain.errors import (CantidadInvalida, ProductoInactivo, ProductoVencido,
                                  StockInsuficiente)
from server.domain.riesgo import evaluar_producto
from server.domain.ventas import calcular_linea, puede_venderse, validar_linea

AHORA = datetime(2026, 5, 10, 12, 0)


def prod(**kw):
    base = dict(id=1, nombre="Leche", categoria="L", precio_base=100.0, stock=5,
                stock_maximo=100, fecha_vencimiento=None, activo=True)
    base.update(kw)
    return ProductoDominio(**base)


@pytest.mark.parametrize("cant", [0, -1, 1.5, None, True])
def test_cantidad_invalida(cant):
    with pytest.raises(CantidadInvalida):
        validar_linea(prod(), cant, AHORA)


def test_stock_insuficiente_detalle():
    with pytest.raises(StockInsuficiente) as ei:
        validar_linea(prod(stock=5), 6, AHORA)
    assert ei.value.detalle == {"producto_id": 1, "disponible": 5, "solicitado": 6}
    assert ei.value.codigo == "STOCK_INSUFICIENTE"


def test_cantidad_igual_al_stock_ok():
    validar_linea(prod(stock=5), 5, AHORA)


def test_vencido():
    with pytest.raises(ProductoVencido):
        validar_linea(prod(fecha_vencimiento=AHORA - timedelta(minutes=1)), 1, AHORA)


def test_vence_hoy_mas_tarde_se_vende():
    p = prod(fecha_vencimiento=AHORA + timedelta(hours=3))
    validar_linea(p, 1, AHORA)
    assert puede_venderse(p, AHORA)


def test_inactivo():
    with pytest.raises(ProductoInactivo):
        validar_linea(prod(activo=False), 1, AHORA)


def test_puede_venderse():
    assert puede_venderse(prod(), AHORA)
    assert not puede_venderse(prod(activo=False), AHORA)
    assert not puede_venderse(prod(fecha_vencimiento=AHORA - timedelta(days=1)), AHORA)


def test_calcular_linea_con_descuento():
    p = prod(fecha_vencimiento=AHORA + timedelta(days=2), precio_base=19.99)
    # Centavos: capacidad explicita (decimales=2). 19,99 * 50 % = 9,995 -> 10,00 con redondeo
    # half-up (antes 9,99 por el redondeo al par/representacion binaria de round()).
    ev = evaluar_producto(p, PoliticaRiesgo(decimales_moneda=2), AHORA)
    l = calcular_linea(p, 3, ev, decimales=2)
    assert l.precio_unitario == 10.0 and l.subtotal == 30.0
    assert l.ahorro == 29.97


def test_calcular_linea_pesos_enteros_por_defecto():
    p = prod(fecha_vencimiento=AHORA + timedelta(days=2), precio_base=4500)
    ev = evaluar_producto(p, PoliticaRiesgo(descuento_critico=15.0), AHORA)
    l = calcular_linea(p, 3, ev)
    assert (l.precio_original, l.precio_unitario, l.subtotal, l.ahorro) == (4500, 3825, 11475, 2025)
    assert all(isinstance(v, int) for v in (l.precio_unitario, l.subtotal, l.ahorro))


def test_calcular_linea_sin_descuento():
    p = prod(stock=50)
    l = calcular_linea(p, 2, evaluar_producto(p, PoliticaRiesgo(), AHORA))
    assert (l.precio_unitario, l.subtotal, l.ahorro) == (100.0, 200.0, 0.0)
