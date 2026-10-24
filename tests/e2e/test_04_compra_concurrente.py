"""Escenario 4: compra concurrente del ULTIMO item entre dos clientes (stock 1).

Dos clientes Windows reales (ventanas de comprador) pagan casi a la vez contra el servidor Linux.
Solo una compra gana; la otra recibe STOCK_INSUFICIENTE, lo maneja la UI sin cerrar la app y el
segundo cliente ve por WebSocket el stock actualizado. Ademas, carreras a nivel API (hilos + barrera)
con varias rondas y con N compradores sobre stock > 1 (sin sobreventa)."""
import threading
import time

import pytest

from client.infrastructure.api_client import ApiClient, ApiError
from client.presentation.views.buyer_window import BuyerWindow
from client.presentation.widgets import Toast
from shared.schemas import UsuarioIn
from tests.e2e.helpers import compra_tarjeta, crear_oferta, entrar, esperar, esperar_ofertas, llenar_pago

pytestmark = pytest.mark.e2e


def test_dos_clientes_pagan_el_ultimo_item_solo_uno_gana(servidor, crear_app, api_admin):
    api_admin.crear_usuario(UsuarioIn(nombre="Comprador Dos", usuario="comprador2", password="clave-dos-123"))
    p = crear_oferta(api_admin, stock=1, precio=10000, nombre="Ultima unidad E2E")
    A = crear_app(servidor)
    B = crear_app(servidor)
    entrar(A, "comprador", servidor.comp_pw)
    entrar(B, "comprador2", "clave-dos-123")
    va, vb = A.ventana, B.ventana
    assert isinstance(va, BuyerWindow) and isinstance(vb, BuyerWindow)
    assert esperar_ofertas(va, p) and esperar_ofertas(vb, p)
    assert va.tarjetas[p.id].stock == 1 and vb.tarjetas[p.id].stock == 1
    assert esperar(lambda: A.eventos.esta_conectado and B.eventos.esta_conectado, 15)

    # ambos meten la unidad en el carrito y abren el dialogo de pago
    for v in (va, vb):
        v.tarjetas[p.id].btn_agregar.click()
        v.panel_carrito.btn_pagar.click()
        assert v.dialogo_pago is not None
        llenar_pago(v.dialogo_pago)
        v.dialogo_pago.radio_tarjeta.setChecked(True)
        assert v.dialogo_pago.btn_confirmar.isEnabled()

    # registrar cuando sale y vuelve cada peticion de compra (para demostrar el solape real)
    tramos = {}
    for nombre, app in (("A", A), ("B", B)):
        orig = app.api.comprar

        def espia(compra, orig=orig, nombre=nombre):
            t0 = time.perf_counter()
            try:
                return orig(compra)
            finally:
                tramos[nombre] = (t0, time.perf_counter())
        app.api.comprar = espia
    eventos_b = []
    eventos_a = []
    A.evento_ws.connect(lambda n, pl: eventos_a.append((n, pl)))
    B.evento_ws.connect(lambda n, pl: eventos_b.append((n, pl)))

    va.dialogo_pago.btn_confirmar.click()       # "casi a la vez": dos clics seguidos en el mismo bucle
    vb.dialogo_pago.btn_confirmar.click()

    assert esperar(lambda: (va.dialogo_factura is not None or va.dialogo_pago is None)
                   and (vb.dialogo_factura is not None or vb.dialogo_pago is None), 20)
    ganadores = [n for n, v in (("A", va), ("B", vb)) if v.dialogo_factura is not None]
    perdedores = [n for n, v in (("A", va), ("B", vb)) if v.dialogo_factura is None]
    assert len(ganadores) == 1 and len(perdedores) == 1, (ganadores, perdedores)
    ventanas = {"A": (A, va, eventos_a), "B": (B, vb, eventos_b)}
    gana, pierde = ventanas[ganadores[0]], ventanas[perdedores[0]]

    # el que pierde: STOCK_INSUFICIENTE manejado en la UI, app viva, nada cobrado
    ctx_p, v_p, ev_p = pierde
    assert ctx_p.sesion is not None and v_p.isVisible() and ctx_p.ventana is v_p
    assert v_p.dialogo_pago is None and v_p.dialogo_factura is None
    assert esperar(lambda: any("Stock insuficiente" in t.text() for t in Toast.activos(v_p)), 5), \
        [t.text() for t in Toast.activos(v_p)]
    texto = next(t.text() for t in Toast.activos(v_p) if "Stock insuficiente" in t.text())
    # el que gana: factura valida
    f = gana[1].dialogo_factura.factura
    assert f.items[0].cantidad == 1 and f.items[0].producto_id == p.id
    # el perdedor recibe por WS el stock actualizado (0) sin refrescar a mano
    assert esperar(lambda: any(n == "stock_actualizado" and pl.get("producto_id") == p.id
                               and pl.get("stock") == 0 for n, pl in ev_p), 10), ev_p
    assert esperar(lambda: p.id not in v_p.tarjetas or v_p.tarjetas[p.id].stock == 0, 10)
    # servidor: stock 0 exacto y UNA sola factura con ese producto
    prod = next(x for x in api_admin.listar_productos() if x.id == p.id)
    assert prod.stock == 0
    con_producto = [x for x in api_admin.listar_facturas() if any(i.producto_id == p.id for i in x.items)]
    assert [x.numero for x in con_producto] == [f.numero]
    # solape real de las dos peticiones HTTP
    ini = max(tramos["A"][0], tramos["B"][0])
    fin = min(tramos["A"][1], tramos["B"][1])
    solape_ms = (fin - ini) * 1000
    assert solape_ms > 0, tramos
    print(f"\n[4] ganador {ganadores[0]} factura {f.numero}; perdedor {perdedores[0]}: toast '{texto}'; "
          f"peticiones A {1000 * (tramos['A'][1] - tramos['A'][0]):.0f} ms y B "
          f"{1000 * (tramos['B'][1] - tramos['B'][0]):.0f} ms, solape {solape_ms:.0f} ms; "
          f"stock final {prod.stock}; WS al perdedor: {[(n, pl) for n, pl in ev_p if n == 'stock_actualizado']}")
    for v in (va, vb):
        if v.dialogo_factura is not None:
            v.dialogo_factura.btn_cerrar.click()


def _carrera(servidor, api_admin, compradores: int, stock: int):
    """N sesiones compran 1 unidad a la vez (barrera). Devuelve (exitos, errores, stock_final)."""
    p = crear_oferta(api_admin, stock=stock, precio=5000)
    apis = []
    for _ in range(compradores):
        c = ApiClient(servidor.url)
        c.login("comprador", servidor.comp_pw)
        c.health()
        apis.append(c)
    barrera = threading.Barrier(compradores)
    res = []

    def comprar(c):
        barrera.wait(10)
        try:
            res.append(("ok", c.comprar(compra_tarjeta(p.id)).numero))
        except ApiError as e:
            res.append((e.codigo, e.http, e.detalle))
    hilos = [threading.Thread(target=comprar, args=(c,)) for c in apis]
    [h.start() for h in hilos]
    [h.join(30) for h in hilos]
    for c in apis:
        c.cerrar()
    stock_final = next(x for x in api_admin.listar_productos() if x.id == p.id).stock
    return res, stock_final


def test_carreras_api_rondas_ultimo_item(servidor, api_admin):
    rondas = []
    for _ in range(8):
        res, stock = _carrera(servidor, api_admin, compradores=2, stock=1)
        exitos = [r for r in res if r[0] == "ok"]
        fallos = [r for r in res if r[0] != "ok"]
        assert len(exitos) == 1 and len(fallos) == 1, res
        assert fallos[0][0] == "STOCK_INSUFICIENTE" and fallos[0][1] == 409
        assert fallos[0][2]["disponible"] == 0
        assert stock == 0
        rondas.append(stock)
    print(f"\n[4b] 8 rondas de 2 compradores sobre stock 1: siempre 1 exito + 1 STOCK_INSUFICIENTE/409; stocks finales {rondas}")


def test_carrera_seis_compradores_stock_tres(servidor, api_admin):
    res, stock = _carrera(servidor, api_admin, compradores=6, stock=3)
    exitos = [r for r in res if r[0] == "ok"]
    fallos = [r for r in res if r[0] != "ok"]
    assert len(exitos) == 3 and len(fallos) == 3 and stock == 0, res
    assert {f[0] for f in fallos} == {"STOCK_INSUFICIENTE"}
    assert len({e[1] for e in exitos}) == 3                       # tres numeros de factura distintos
    print(f"\n[4c] 6 compradores simultaneos sobre stock 3: {len(exitos)} exitos, {len(fallos)} rechazos, stock final {stock}")
