import pytest

from server.domain.dinero import redondear


@pytest.mark.parametrize("valor,esperado", [(0.5, 1), (1.5, 2), (2.5, 3), (3.5, 4),
                                            (2.4, 2), (5380.8, 5381), (0, 0), (1234, 1234)])
def test_half_up_sin_decimales(valor, esperado):
    r = redondear(valor, 0)
    assert r == esperado and isinstance(r, int)


def test_half_up_con_decimales():
    assert redondear(2.675, 2) == 2.68      # round() daria 2.67
    assert redondear(0.125, 2) == 0.13
    assert redondear(1.005, 2) == 1.01


def test_decimales_por_defecto_cero():
    assert redondear(4.5) == 5
