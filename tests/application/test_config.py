import pytest

from server.application.errores import ErrorValidacion, RolNoPermitido


def test_lectura_tipada_y_publica(config):
    t = config.obtener_todo("admin")
    assert t["inactividad_segundos"] == 180 and isinstance(t["iva_pct"], float)
    assert t["descuento_critico"] == 50.0
    assert set(config.obtener_publica()) >= {"moneda", "nombre_negocio"}
    assert "inactividad_segundos" not in config.obtener_publica()
    with pytest.raises(RolNoPermitido):
        config.obtener_todo("comprador")


def test_actualizar_persiste_y_publica_evento(config, eventos):
    r = config.actualizar({"inactividad_segundos": 300, "iva_pct": "19", "moneda": "COP"},
                          "admin")
    assert r["inactividad_segundos"] == 300 and r["iva_pct"] == 19.0
    assert config.obtener_todo("admin")["moneda"] == "COP"
    assert len(eventos) == 1 and eventos[0]["tipo"] == "config_cambiada"
    assert set(eventos[0]["payload"]["claves"]) == {"iva_pct", "inactividad_segundos", "moneda"}


def test_sin_cambio_real_no_publica(config, eventos):
    config.actualizar({"iva_pct": 0}, "admin")
    assert eventos == []


@pytest.mark.parametrize("cambio", [
    {"inactividad_segundos": 29}, {"inactividad_segundos": 3601},
    {"aviso_segundos": 4}, {"aviso_segundos": 180},        # >= inactividad vigente
    {"descuento_alto": -1}, {"descuento_alto": 100.5},
    {"dias_alerta_vencimiento": -1},
    {"dias_critico_vencimiento": 8},                       # > alerta (7)
    {"dias_alerta_vencimiento": 2},                        # < critico (3)
    {"intervalo_escaneo_segundos": 9}, {"intervalo_escaneo_segundos": 3601},
    {"iva_pct": 101}, {"iva_pct": "abc"}, {"iva_pct": True},
    {"nombre_negocio": "   "}, {"moneda": ""},
    {"clave_inventada": 1},
    {"inactividad_segundos": 30.5},
    {"inactividad_segundos": 30},                          # aviso vigente 30 no es < 30
])
def test_rangos_invalidos(config, cambio):
    with pytest.raises(ErrorValidacion):
        config.actualizar(cambio, "admin")


def test_limites_validos(config):
    config.actualizar({"inactividad_segundos": 3600, "aviso_segundos": 5,
                       "intervalo_escaneo_segundos": 10, "descuento_alto": 100,
                       "dias_critico_vencimiento": 7, "iva_pct": 100}, "admin")


def test_aviso_se_valida_contra_valor_resultante(config):
    config.actualizar({"inactividad_segundos": 600, "aviso_segundos": 500}, "admin")
    with pytest.raises(ErrorValidacion):
        config.actualizar({"inactividad_segundos": 400}, "admin")  # aviso 500 >= 400
    config.actualizar({"inactividad_segundos": 400, "aviso_segundos": 60}, "admin")


def test_atomico_si_una_falla_no_se_guarda_ninguna(config, eventos):
    antes = config.obtener_todo("admin")
    with pytest.raises(ErrorValidacion):
        config.actualizar({"moneda": "EUR", "iva_pct": 5, "descuento_alto": 300}, "admin")
    with pytest.raises(ErrorValidacion):  # falla la regla cruzada, con otras claves validas
        config.actualizar({"moneda": "EUR", "aviso_segundos": 999}, "admin")
    assert config.obtener_todo("admin") == antes and eventos == []


def test_solo_admin_escribe(config):
    with pytest.raises(RolNoPermitido):
        config.actualizar({"iva_pct": 5}, "comprador")


def test_politica_riesgo_refleja_config(config):
    config.actualizar({"dias_alerta_vencimiento": 10, "descuento_critico": 60}, "admin")
    p = config.politica_riesgo()
    assert p.dias_alerta == 10 and p.descuento_critico == 60.0 and p.dias_critico == 3


def test_decimales_moneda_defecto_publico_y_rango(config):
    assert config.obtener_publica()["decimales_moneda"] == 0
    assert config.politica_riesgo().decimales_moneda == 0
    config.actualizar({"decimales_moneda": 2}, "admin")
    assert config.politica_riesgo().decimales_moneda == 2
    for malo in (-1, 3, 1.5, "x"):
        with pytest.raises(ErrorValidacion):
            config.actualizar({"decimales_moneda": malo}, "admin")


def test_descuento_medio_es_clave_desconocida(config):
    with pytest.raises(ErrorValidacion):
        config.actualizar({"descuento_medio": 20}, "admin")
    assert "descuento_medio" not in config.obtener_todo("admin")


def test_fila_huerfana_descuento_medio_se_ignora(config, factory):
    from server.infrastructure.db.engine import sesion
    from server.infrastructure.db.repos import ConfigRepo
    with sesion(factory) as s:
        ConfigRepo(s).set("descuento_medio", "15")
    assert "descuento_medio" not in config.obtener_todo("admin")
    config.politica_riesgo()                        # no depende de la clave
    config.actualizar({"iva_pct": 5}, "admin")      # y no rompe escrituras
