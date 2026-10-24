from datetime import datetime, timedelta

from server.domain.entities import NivelRiesgo as N, PoliticaRiesgo, ProductoDominio
from server.domain.riesgo import dias_para_vencer, esta_vencido, evaluar_producto

AHORA = datetime(2026, 5, 10, 12, 0)
POL = PoliticaRiesgo()


def prod(venc=None, stock=50, maximo=100, precio=100.0, **kw):
    return ProductoDominio(1, "Leche", "Lacteos", precio, stock, maximo, venc, **kw)


def en_dias(n):
    return AHORA + timedelta(days=n)


def test_sin_fecha():
    p = prod()
    assert dias_para_vencer(p, AHORA) is None
    assert not esta_vencido(p, AHORA)
    e = evaluar_producto(p, POL, AHORA)
    assert (e.nivel, e.descuento, e.motivo, e.dias_para_vencer) == (N.NORMAL, 0, "Sin riesgo", None)


def test_dias_calendario():
    assert dias_para_vencer(prod(datetime(2026, 5, 11, 0, 0)), AHORA) == 1   # manana
    assert dias_para_vencer(prod(datetime(2026, 5, 10, 18, 0)), AHORA) == 0  # hoy
    assert dias_para_vencer(prod(datetime(2026, 5, 9, 8, 0)), AHORA) == -1


def test_hoy_mas_tarde_no_vencido():
    p = prod(datetime(2026, 5, 10, 18, 0))
    assert not esta_vencido(p, AHORA)
    e = evaluar_producto(p, POL, AHORA)
    assert e.nivel == N.CRITICO and not e.vencido and e.descuento == 50 and e.precio_final == 50


def test_justo_vencido():
    assert not esta_vencido(prod(AHORA), AHORA)  # instante exacto: aun no
    assert esta_vencido(prod(AHORA - timedelta(seconds=1)), AHORA)


def test_vencido_sin_descuento():
    e = evaluar_producto(prod(en_dias(-2)), POL, AHORA)
    assert e.vencido and e.nivel == N.CRITICO and e.motivo == "Vencido"
    assert e.descuento == 0 and e.precio_final == e.precio_original == 100.0


def test_borde_3_dias_critico():
    e = evaluar_producto(prod(en_dias(3)), POL, AHORA)
    assert e.nivel == N.CRITICO and e.descuento == 50 and e.dias_para_vencer == 3


def test_borde_4_dias_alto():
    e = evaluar_producto(prod(en_dias(4)), POL, AHORA)
    assert e.nivel == N.ALTO and e.descuento == 30 and e.precio_final == 70


def test_borde_7_dias_alto():
    assert evaluar_producto(prod(en_dias(7)), POL, AHORA).nivel == N.ALTO


def test_8_dias_normal():
    e = evaluar_producto(prod(en_dias(8)), POL, AHORA)
    assert e.nivel == N.NORMAL and e.descuento == 0


def test_sobrestock_exacto_90():
    e = evaluar_producto(prod(stock=90, maximo=100), POL, AHORA)
    assert e.nivel == N.MEDIO and e.descuento == 10 and "Sobrestock" in e.motivo
    assert evaluar_producto(prod(stock=89, maximo=100), POL, AHORA).nivel == N.NORMAL


def test_stock_bajo_umbral_exacto():
    e = evaluar_producto(prod(stock=10), POL, AHORA)
    assert e.nivel == N.MEDIO and e.descuento == 0 and "Stock bajo" in e.motivo
    assert "Sobrestock" not in e.motivo
    assert evaluar_producto(prod(stock=11), POL, AHORA).nivel == N.NORMAL


def test_stock_cero_sin_alerta_de_stock_bajo():
    assert evaluar_producto(prod(stock=0), POL, AHORA).nivel == N.NORMAL


def test_stock_bajo_y_sobrestock_no_se_mezclan():
    e = evaluar_producto(prod(stock=5, maximo=5), POL, AHORA)
    assert "Sobrestock" in e.motivo and "Stock bajo" not in e.motivo and e.descuento == 10


def test_stock_maximo_cero_no_es_sobrestock():
    assert evaluar_producto(prod(stock=50, maximo=0), POL, AHORA).nivel == N.NORMAL


def test_combinacion_vencimiento_y_sobrestock():
    e = evaluar_producto(prod(en_dias(5), stock=95), POL, AHORA)
    assert e.nivel == N.ALTO and e.descuento == 30
    assert e.motivo == "Vence en 5 día(s) | Sobrestock: 95/100 unidades"


def test_sobrestock_mayor_descuento_que_vencimiento():
    pol = PoliticaRiesgo(descuento_sobrestock=40.0)
    e = evaluar_producto(prod(en_dias(5), stock=95), pol, AHORA)
    assert e.nivel == N.ALTO and e.descuento == 40


def test_vencido_y_sobrestock_sin_descuento():
    e = evaluar_producto(prod(en_dias(-1), stock=95), POL, AHORA)
    assert e.vencido and e.descuento == 0 and e.motivo.startswith("Vencido | Sobrestock")


def test_politica_parametrizable_y_redondeo():
    pol = PoliticaRiesgo(dias_critico=1, dias_alerta=2, descuento_alto=33.0)
    e = evaluar_producto(prod(en_dias(2), precio=10.0), pol, AHORA)
    assert e.nivel == N.ALTO and e.precio_final == 6.7
