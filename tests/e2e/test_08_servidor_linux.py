"""Escenarios obligatorios del servidor, ejecutados desde Windows contra el servidor REAL en Ubuntu:
stock insuficiente, producto vencido, rollback, login, migracion SHA-256 -> argon2id, tokens
manipulados/expirados, FK y CHECK en la BD de Linux, WebSocket entre dos clientes y flujo de admin."""
import json
import re
import time
from datetime import datetime, timedelta

import pytest
import websockets.sync.client as wsc

from client.infrastructure.api_client import ApiClient, ApiError
from client.presentation.views.main_window import MainWindow
from shared.schemas import (ClienteIn, CompraIn, ItemCompraIn, PagoIn, ProductoIn, UsuarioIn,
                            UsuarioUpdate)
from tests.e2e.helpers import compra_tarjeta, crear_oferta, entrar, esperar

pytestmark = pytest.mark.e2e


def error_de(fn):
    with pytest.raises(ApiError) as e:
        fn()
    return e.value


def stock_de(api, pid):
    return next(p.stock for p in api.listar_productos() if p.id == pid)


def n_facturas(api):
    return len(api.listar_facturas())


# -- compras --------------------------------------------------------------------------------------
def test_comprar_mas_que_el_stock_da_409_y_el_stock_queda_intacto(api_admin, api_comprador):
    p = crear_oferta(api_admin, stock=2, precio=10000)
    antes = n_facturas(api_admin)
    e = error_de(lambda: api_comprador.comprar(compra_tarjeta(p.id, 3)))
    assert (e.http, e.codigo) == (409, "STOCK_INSUFICIENTE")
    assert e.detalle["disponible"] == 2 and e.detalle["solicitado"] == 3
    assert stock_de(api_admin, p.id) == 2 and n_facturas(api_admin) == antes
    print(f"\n[8a] 409 {e.codigo} {e.detalle}; stock intacto 2; facturas sin cambio ({antes})")


def test_comprar_producto_vencido_es_rechazado(api_admin, api_comprador):
    p = api_admin.crear_producto(ProductoIn(nombre="Leche vencida E2E", precio_base=5000, stock=5,
                                            stock_maximo=100,
                                            fecha_vencimiento=datetime.now() - timedelta(days=1)))
    e = error_de(lambda: api_comprador.comprar(compra_tarjeta(p.id, 1)))
    assert e.http == 409 and e.codigo == "PRODUCTO_VENCIDO"
    assert stock_de(api_admin, p.id) == 5
    print(f"\n[8b] {e.http} {e.codigo}: {e.mensaje}")


def test_rollback_total_si_falla_un_item(api_admin, api_comprador):
    a = crear_oferta(api_admin, stock=5, precio=10000, nombre="Rollback A")
    b = crear_oferta(api_admin, stock=1, precio=10000, nombre="Rollback B")
    antes = n_facturas(api_admin)
    ultimo = max((int(f.numero.split("-")[1]) for f in api_admin.listar_facturas()), default=0)
    compra = CompraIn(items=[ItemCompraIn(producto_id=a.id, cantidad=2), ItemCompraIn(producto_id=b.id, cantidad=2)],
                      cliente=ClienteIn(nombre="Rollback", documento="123456"), pago=PagoIn(metodo="tarjeta_simulada"))
    e = error_de(lambda: api_comprador.comprar(compra))
    assert (e.http, e.codigo, e.detalle["producto_id"]) == (409, "STOCK_INSUFICIENTE", b.id)
    assert stock_de(api_admin, a.id) == 5 and stock_de(api_admin, b.id) == 1     # A no se desconto
    assert n_facturas(api_admin) == antes
    ok = api_comprador.comprar(compra_tarjeta(a.id, 1))                          # y el consecutivo no se consumio
    assert int(ok.numero.split("-")[1]) == ultimo + 1
    print(f"\n[8c] item B falla (409) -> A conserva stock 5, sin factura, consecutivo intacto (siguiente {ok.numero})")


# -- login --------------------------------------------------------------------------------------------
def test_login_correcto_incorrecto_e_inactivo(servidor, api_admin):
    u = api_admin.crear_usuario(UsuarioIn(nombre="Login E2E", usuario="login_e2e", password="clave-login-1"))
    c = ApiClient(servidor.url)
    try:
        out = c.login("login_e2e", "clave-login-1")
        assert out.usuario.rol == "comprador" and out.token and (out.sesion.inactividad_segundos, out.sesion.aviso_segundos) == (180, 30)
        mal = error_de(lambda: ApiClient(servidor.url).login("login_e2e", "otra-clave-xx"))
        desconocido = error_de(lambda: ApiClient(servidor.url).login("no_existe_e2e", "otra-clave-xx"))
        assert (mal.http, mal.codigo) == (401, "CREDENCIALES_INVALIDAS")
        assert (desconocido.http, desconocido.codigo, desconocido.mensaje) == (401, "CREDENCIALES_INVALIDAS", mal.mensaje)  # sin enumeracion
        api_admin.actualizar_usuario(u.id, UsuarioUpdate(activo=False))
        inactivo = error_de(lambda: ApiClient(servidor.url).login("login_e2e", "clave-login-1"))
        assert (inactivo.http, inactivo.codigo, inactivo.mensaje) == (401, "CREDENCIALES_INVALIDAS", mal.mensaje)
        # bloqueo temporal tras 5 fallos
        for _ in range(5):
            error_de(lambda: ApiClient(servidor.url).login("bloqueo_e2e", "x" * 8))
        bloq = error_de(lambda: ApiClient(servidor.url).login("bloqueo_e2e", "x" * 8))
        assert bloq.http == 429 and bloq.codigo == "TOO_MANY_ATTEMPTS" and bloq.reintentar_en
        print(f"\n[8d] login ok; incorrecto/desconocido/inactivo -> 401 {mal.codigo} con el mismo mensaje; "
              f"6 fallos -> 429 reintentar en {bloq.reintentar_en} s")
    finally:
        c.cerrar()


def test_migracion_hash_sha256_a_argon2id(servidor, api_admin):
    api_admin.crear_usuario(UsuarioIn(nombre="Legacy", usuario="legacy_e2e", password="clave-legacy-1"))
    db = f"{servidor.dir}/data/inventario.db"
    leer = ("import sqlite3,sys\nc=sqlite3.connect(sys.argv[1]);"
            "print(c.execute(\"select password_hash from usuarios where usuario='legacy_e2e'\").fetchone()[0])\n")
    hash_en_bd = lambda: servidor.python_en_linux(leer.replace("sys.argv[1]", repr(db))).strip()
    assert hash_en_bd().startswith("$argon2id$")
    # se degrada al formato legacy sha256$<hex> directamente en la BD de Linux
    servidor.python_en_linux(
        "import sqlite3,hashlib\n"
        f"c=sqlite3.connect({db!r})\n"
        "h='sha256$'+hashlib.sha256('clave-legacy-1'.encode()).hexdigest()\n"
        "c.execute(\"update usuarios set password_hash=? where usuario='legacy_e2e'\",(h,));c.commit()\n")
    legacy = hash_en_bd()
    assert legacy.startswith("sha256$")
    mal = error_de(lambda: ApiClient(servidor.url).login("legacy_e2e", "clave-incorrecta"))
    assert mal.http == 401 and hash_en_bd() == legacy                    # un fallo no migra
    c = ApiClient(servidor.url)
    c.login("legacy_e2e", "clave-legacy-1")                              # el login correcto migra
    migrado = hash_en_bd()
    assert migrado.startswith("$argon2id$") and migrado != legacy
    c.login("legacy_e2e", "clave-legacy-1")                              # y sigue funcionando
    assert hash_en_bd() == migrado                                       # sin re-hashear de nuevo
    c.cerrar()
    print(f"\n[8e] hash en BD Linux: {legacy[:16]}... -> {migrado[:30]}... tras login correcto")


# -- tokens ---------------------------------------------------------------------------------------------
def _token_expirado(servidor) -> str:
    return servidor.python_en_linux(
        "from datetime import datetime, timedelta\n"
        "from server.security import tokens\n"
        "print(tokens.emitir(2, 'comprador', 'jti-expirado-e2e', datetime.now() - timedelta(minutes=5)))\n").strip()


def test_token_manipulado_o_expirado_es_401(servidor, api_comprador):
    bueno = api_comprador.token
    cab, cuerpo, firma = bueno.split(".")
    # misma firma, otra carga util (rol admin)
    import base64
    carga = json.loads(base64.urlsafe_b64decode(cuerpo + "=" * (-len(cuerpo) % 4)))
    carga["rol"] = "admin"
    nuevo = base64.urlsafe_b64encode(json.dumps(carga).encode()).rstrip(b"=").decode()
    sin_alg = (base64.urlsafe_b64encode(b'{"alg":"none","typ":"JWT"}').rstrip(b"=").decode() + "." + cuerpo + ".")
    casos = {
        "firma alterada": f"{cab}.{cuerpo}.{firma[:-3]}AAA",
        "payload alterado (rol=admin)": f"{cab}.{nuevo}.{firma}",
        "alg=none": sin_alg,
        "basura": "esto-no-es-un-jwt",
        "expirado": _token_expirado(servidor),
    }
    resumen = {}
    for nombre, tk in casos.items():
        c = ApiClient(servidor.url, token=tk)
        e = error_de(c.estado_sesion)
        c.cerrar()
        assert (e.http, e.codigo) == (401, "TOKEN_INVALIDO"), (nombre, e.http, e.codigo)
        resumen[nombre] = f"{e.http} {e.codigo}" + (f" ({e.detalle})" if e.detalle else "")
        # y tampoco abre el WebSocket (cierre 4401)
        with wsc.connect(f"ws://127.0.0.1:{servidor.puerto}/ws?token={tk}") as ws:
            try:
                ws.recv(timeout=5)
                raise AssertionError("el WS entrego datos con un token invalido")
            except Exception as ex:      # noqa: BLE001
                assert getattr(getattr(ex, "rcvd", None), "code", None) == 4401, repr(ex)
    sin_header = ApiClient(servidor.url)
    e = error_de(sin_header.estado_sesion)
    sin_header.cerrar()
    assert e.http == 401
    assert api_comprador.estado_sesion().segundos_restantes > 0         # el token bueno sigue sirviendo
    print(f"\n[8f] tokens invalidos: {resumen}; sin cabecera -> {e.http} {e.codigo}; WS cierra con 4401")


# -- BD en Linux ---------------------------------------------------------------------------------------------
def test_fk_y_check_activos_en_la_bd_de_linux(servidor, api_admin):
    p = crear_oferta(api_admin, stock=3)
    salida = servidor.python_en_linux(f'''
import json
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from server.infrastructure.db.engine import crear_engine
eng = crear_engine({servidor.dir + "/data/inventario.db"!r})
res = {{}}
with eng.connect() as c:
    res["foreign_keys"] = c.execute(text("PRAGMA foreign_keys")).scalar()
    res["journal_mode"] = c.execute(text("PRAGMA journal_mode")).scalar()
def intento(nombre, sql):
    try:
        with eng.begin() as c:
            c.execute(text(sql))
        res[nombre] = "PERMITIDO (mal)"
    except IntegrityError as e:
        res[nombre] = str(e.orig)
intento("fk_descuento_producto_inexistente", "insert into descuentos (producto_id, porcentaje, motivo, activo, fecha_inicio) values (999999, 10, 'x', 1, '2026-01-01')")
intento("fk_detalle_sin_factura", "insert into detalle_factura (factura_id, producto_id, nombre_producto, cantidad, precio_unitario, descuento_pct, precio_final, subtotal) values (999999, {p.id}, 'x', 1, 1, 0, 1, 1)")
intento("check_stock_negativo", "update productos set stock = -1 where id = {p.id}")
intento("check_precio_negativo", "update productos set precio_base = -5 where id = {p.id}")
intento("check_descuento_150", "insert into descuentos (producto_id, porcentaje, motivo, activo, fecha_inicio) values ({p.id}, 150, 'x', 1, '2026-01-01')")
intento("check_cantidad_cero", "insert into detalle_factura (factura_id, producto_id, nombre_producto, cantidad, precio_unitario, descuento_pct, precio_final, subtotal) values (1, {p.id}, 'x', 0, 1, 0, 1, 1)")
print(json.dumps(res))
''')
    res = json.loads(salida.strip().splitlines()[-1])
    assert res["foreign_keys"] == 1 and res["journal_mode"] == "wal"
    for k, v in res.items():
        if k.startswith("fk_"):
            assert "FOREIGN KEY" in v, (k, v)
        elif k.startswith("check_"):
            assert "CHECK constraint failed" in v, (k, v)
    assert stock_de(api_admin, p.id) == 3                               # nada se modifico
    # y por API: el servidor valida antes de llegar a la BD
    e = error_de(lambda: api_admin.crear_producto.__self__._pedir(
        "POST", "/productos", json={"nombre": "neg", "precio_base": 10, "stock": -1}))
    assert e.http == 422
    print(f"\n[8g] BD de Linux: {res}")


# -- WebSocket entre dos clientes ---------------------------------------------------------------------------
def test_websocket_entrega_el_evento_al_otro_cliente(servidor, api_admin, api_comprador):
    p = crear_oferta(api_admin, stock=5, precio=10000)
    with wsc.connect(f"ws://127.0.0.1:{servidor.puerto}/ws?token={api_comprador.token}") as ws_otro:
        t0 = time.monotonic()
        api_admin.comprar(compra_tarjeta(p.id, 2))                       # el admin compra desde otro cliente
        visto = None
        fin = time.monotonic() + 5
        while time.monotonic() < fin:
            msg = json.loads(ws_otro.recv(timeout=5))
            if msg["evento"] == "stock_actualizado" and msg["payload"]["producto_id"] == p.id:
                visto = msg
                break
        dt = time.monotonic() - t0
    assert visto and visto["payload"] == {"producto_id": p.id, "stock": 3, "activo": True}
    print(f"\n[8h] el otro cliente recibio {visto} en {dt * 1000:.0f} ms")


# -- flujo del administrador por la UI -------------------------------------------------------------------------
def test_flujo_admin_por_la_ui_recorre_todas_las_vistas(servidor, crear_app, api_admin, espera):
    p = crear_oferta(api_admin, stock=4, precio=9000, nombre="Producto para el admin")
    a = crear_app(servidor)
    entrar(a, "admin", servidor.admin_pw)
    w = a.ventana
    assert isinstance(w, MainWindow)
    assert espera(lambda: w.barra.conexion._texto.text() == "Servidor en línea · Linux", 15)
    cargadas = {}
    for clave in ("dashboard", "inventario", "alertas", "usuarios", "configuracion"):
        w.ir_a(clave)
        assert espera(lambda: w.vistas[clave].cargada, 10), f"la vista {clave} no cargo"
        cargadas[clave] = True
    assert w.vista_actual() == "configuracion"
    # el stock que cambia otro cliente se refleja en el admin sin refrescar (evento WS)
    api_admin.comprar(compra_tarjeta(p.id, 1))
    w.ir_a("inventario")
    assert espera(lambda: w.vistas["inventario"].cargada, 5)
    a.api.listar_productos()                                              # el ApiClient del admin responde
    print(f"\n[8i] admin Windows vs servidor Linux: vistas cargadas {list(cargadas)}; barra: "
          f"'{w.barra.conexion._texto.text()}'; usuario '{w.barra.lbl_usuario.text()}'")
