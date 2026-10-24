from client.infrastructure.api_client import ApiClient
from client.infrastructure.event_client import EventClient
from shared.schemas import CompraIn, ItemCompraIn, PagoIn, ProductoIn
from tests.client.conftest import ADMIN_PW, COMP_PW


def _recolectar(ec):
    reg = {"eventos": [], "estados": [], "sondeos": 0, "invalida": 0}
    ec.evento.connect(lambda n, p: reg["eventos"].append((n, p)))
    ec.conectado.connect(reg["estados"].append)
    ec.sondeo.connect(lambda: reg.__setitem__("sondeos", reg["sondeos"] + 1))
    ec.sesion_invalida.connect(lambda: reg.__setitem__("invalida", reg["invalida"] + 1))
    return reg


def test_recibe_evento_real_tras_compra(qapp, espera, servidor, api_admin, api_comprador):
    ec = EventClient(api_admin.url_websocket(), api_admin.token, sondeo_ms=60000)
    reg = _recolectar(ec)
    ec.iniciar()
    try:
        assert espera(lambda: ec.esta_conectado)
        p = api_admin.crear_producto(ProductoIn(nombre="Pan ws", precio_base=3.0, stock=10,
                                                stock_maximo=100))
        api_comprador.comprar(CompraIn(items=[ItemCompraIn(producto_id=p.id, cantidad=3)],
                                       pago=PagoIn(metodo="tarjeta_simulada")))
        assert espera(lambda: any(n == "stock_actualizado" and pl.get("producto_id") == p.id
                                  and pl.get("stock") == 7 for n, pl in reg["eventos"]))
    finally:
        ec.detener()
    assert reg["estados"][-1] is False


def test_token_invalido_emite_sesion_invalida_y_no_reintenta(qapp, espera, servidor):
    ec = EventClient(servidor.url.replace("http", "ws") + "/ws", "token-falso",
                     backoff=(0.05,), sondeo_ms=60000)
    reg = _recolectar(ec)
    ec.iniciar()
    assert espera(lambda: reg["invalida"] == 1)
    espera(lambda: False, timeout=0.5)
    assert reg["invalida"] == 1                 # no reintenta
    assert reg["estados"].count(True) <= 1
    ec.detener()


def test_mensajes_mal_formados_se_ignoran(qapp):
    ec = EventClient("ws://127.0.0.1:1/ws", "t")
    reg = _recolectar(ec)
    for basura in ("no es json", "[1,2]", "{}", '{"evento": 5}', '{"evento": "inventado", "payload": {}}',
                   '{"evento": "stock_actualizado", "payload": "x"}', ""):
        ec._al_mensaje(basura)
    assert reg["eventos"] == []
    ec._al_mensaje('{"evento": "config_cambiada", "payload": {"claves": ["iva_pct"]}}')
    assert reg["eventos"] == [("config_cambiada", {"claves": ["iva_pct"]})]


def test_reconexion_con_backoff_y_sondeo_mientras_cae(qapp, espera, servidor_propio):
    s = servidor_propio
    api = ApiClient(s.url)
    api.login("admin", ADMIN_PW)
    ec = EventClient(api.url_websocket(), api.token, backoff=(0.1, 0.2), sondeo_ms=300,
                     ping_ms=60000)
    reg = _recolectar(ec)
    ec.iniciar()
    try:
        assert espera(lambda: ec.esta_conectado)
        s.detener()
        assert espera(lambda: ec.esta_conectado is False, timeout=10)
        assert espera(lambda: reg["sondeos"] >= 2, timeout=5)      # respaldo de polling
        antes = reg["sondeos"]
        from tests.client.conftest import Servidor
        s2 = Servidor(s.dir, s.puerto).iniciar()
        try:
            assert espera(lambda: ec.esta_conectado, timeout=15)   # reconecta solo
            assert reg["invalida"] == 0
            assert reg["sondeos"] > antes                          # resincroniza al volver
            sondeos = reg["sondeos"]
            espera(lambda: False, timeout=0.8)
            assert reg["sondeos"] == sondeos                       # conectado: sin polling
        finally:
            s2.detener()
    finally:
        ec.detener()
        api.cerrar()
