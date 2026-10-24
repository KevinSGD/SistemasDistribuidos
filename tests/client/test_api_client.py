import httpx
import pytest

from client.infrastructure.api_client import ApiClient, ApiError, ErrorConexion
from client.infrastructure.config import normalizar_url
from shared.schemas import (
    ClienteIn, CompraIn, ItemCompraIn, PagoIn, ProductoIn, ProductoUpdate, UsuarioIn,
)
from tests.client.conftest import ADMIN_PW, COMP_PW, puerto_libre


def test_health_y_login_ok(servidor):
    c = ApiClient(servidor.url)
    assert c.health().estado == "ok"
    out = c.login("admin", ADMIN_PW)
    assert out.usuario.rol == "admin" and c.token == out.token
    assert out.sesion.inactividad_segundos >= 30
    c.cerrar()


def test_login_mal_credenciales(servidor):
    c = ApiClient(servidor.url)
    with pytest.raises(ApiError) as e:
        c.login("comprador", "incorrecta-123")
    assert e.value.codigo == "CREDENCIALES_INVALIDAS" and e.value.http == 401
    assert c.token is None
    c.cerrar()


def test_bloqueo_429_con_segundos(servidor):
    c = ApiClient(servidor.url)
    err = None
    for _ in range(7):
        try:
            c.login("usuario-bloqueable", "mala-clave-123")
        except ApiError as e:
            err = e
            if e.http == 429:
                break
    assert err.codigo == "TOO_MANY_ATTEMPTS" and err.reintentar_en and err.reintentar_en > 0
    c.cerrar()


def test_error_conexion_servidor_apagado():
    c = ApiClient(f"http://127.0.0.1:{puerto_libre()}", timeout=1.0)
    with pytest.raises(ErrorConexion):
        c.health()
    with pytest.raises(ErrorConexion):
        c.login("admin", "x")
    c.cerrar()


def test_endpoints_principales(api_admin, api_comprador):
    p = api_admin.crear_producto(ProductoIn(nombre="Yogur cli", precio_base=5.0, stock=10,
                                            stock_maximo=100))
    assert p.id and p.nombre == "Yogur cli"
    p2 = api_admin.actualizar_producto(p.id, ProductoUpdate(precio_base=6.5))
    assert p2.precio_base == 6.5
    assert any(x.id == p.id for x in api_comprador.listar_productos())
    api_comprador.listar_ofertas()
    api_admin.resumen_riesgo()
    api_admin.alertas_riesgo()
    assert api_admin.obtener_config().inactividad_segundos >= 30
    assert api_comprador.config_publica().moneda
    api_admin.listar_usuarios()

    f = api_comprador.comprar(CompraIn(items=[ItemCompraIn(producto_id=p.id, cantidad=2)],
                                       cliente=ClienteIn(nombre="Ana", documento="1"),
                                       pago=PagoIn(metodo="efectivo", efectivo_recibido=100)))
    assert f.total > 0 and f.items[0].cantidad == 2 and f.cambio is not None
    assert api_comprador.obtener_factura(f.numero).numero == f.numero
    assert any(x.numero == f.numero for x in api_comprador.listar_facturas(limite=10))

    with pytest.raises(ApiError) as e:
        api_comprador.comprar(CompraIn(items=[ItemCompraIn(producto_id=p.id, cantidad=999)],
                                       pago=PagoIn(metodo="tarjeta_simulada")))
    assert e.value.codigo == "STOCK_INSUFICIENTE" and e.value.http == 409
    with pytest.raises(ApiError) as e:
        api_comprador.listar_usuarios()
    assert e.value.codigo == "ROL_NO_PERMITIDO"

    api_admin.eliminar_producto(p.id)
    u = api_admin.crear_usuario(UsuarioIn(nombre="Tmp", usuario="tmpuser", password="clave-larga-1"))
    assert u.rol == "comprador"


def test_sesion_invalida_notifica_una_sola_vez(servidor):
    llamadas = []
    c = ApiClient(servidor.url, on_sesion_invalida=llamadas.append)
    c.login("comprador", COMP_PW)
    # revocar la sesion con otro cliente que usa el mismo token
    otro = ApiClient(servidor.url, token=c.token)
    otro.logout()
    for _ in range(3):
        with pytest.raises(ApiError) as e:
            c.estado_sesion()
        assert e.value.http == 401
    assert llamadas == ["SESION_CERRADA"]
    c.cerrar()
    otro.cerrar()


def test_token_invalido_notifica(servidor):
    llamadas = []
    c = ApiClient(servidor.url, token="basura", on_sesion_invalida=llamadas.append)
    with pytest.raises(ApiError):
        c.listar_productos()
    assert llamadas == ["TOKEN_INVALIDO"]


def test_estado_sesion_no_renueva_y_actividad_si(api_comprador):
    a = api_comprador.estado_sesion().segundos_restantes
    b = api_comprador.registrar_actividad().segundos_restantes
    assert b >= a


def test_respuesta_no_json_es_api_error():
    def handler(request):
        return httpx.Response(502, text="<html>bad gateway</html>")
    c = ApiClient("http://x:1", transport=httpx.MockTransport(handler))
    with pytest.raises(ApiError) as e:
        c.health()
    assert e.value.codigo == "ERROR_HTTP" and e.value.http == 502


def test_normalizar_url():
    assert normalizar_url("localhost:8000/") == "http://localhost:8000"
    assert normalizar_url("https://a.b:9/api/v1") == "https://a.b:9"
    with pytest.raises(ValueError):
        normalizar_url("")
    with pytest.raises(ValueError):
        normalizar_url("ftp://x")


def test_cerrar_con_peticion_en_vuelo_no_la_corta_y_rechaza_nuevas():
    """cerrar() no cierra el transporte bajo una peticion en curso (crash nativo en Windows)."""
    import threading
    entro, soltar = threading.Event(), threading.Event()

    def handler(request):
        entro.set()
        soltar.wait(5)
        return httpx.Response(200, json={"estado": "ok", "version": "1", "so": "x"})

    api = ApiClient("http://localhost:9", transport=httpx.MockTransport(handler))
    resultado = {}

    def pedir():
        try:
            resultado["ok"] = api.health()
        except Exception as exc:     # noqa: BLE001
            resultado["error"] = exc

    hilo = threading.Thread(target=pedir)
    hilo.start()
    assert entro.wait(5)
    api.cerrar()                      # con la peticion en vuelo: no bloquea ni cierra aun
    assert api._http_cerrado is False
    with pytest.raises(ErrorConexion):
        api.health()                  # las nuevas se rechazan
    soltar.set()
    hilo.join(5)
    assert "error" not in resultado and resultado["ok"].estado == "ok"
    assert api._http_cerrado is True  # la ultima en vuelo hizo el cierre real


def test_cerrar_sin_peticiones_cierra_de_inmediato():
    api = ApiClient("http://localhost:9", transport=httpx.MockTransport(lambda r: httpx.Response(200)))
    api.cerrar()
    api.cerrar()                      # idempotente
    assert api._http_cerrado is True
