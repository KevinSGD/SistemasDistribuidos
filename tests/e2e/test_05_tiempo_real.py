"""Escenario 5: tiempo real por WebSocket (servidor Linux -> clientes Windows) y cierre remoto de sesion.

El admin crea/edita productos y el comprador ve el cambio de oferta/stock SIN refrescar (nadie llama
a `cargar` ni a "Actualizar": solo el evento WS). Luego el admin desactiva al comprador y su sesion
cae con el motivo correcto."""
import time
from datetime import datetime, timedelta

import pytest

from client.infrastructure.api_client import ApiClient, ApiError
from client.presentation.views.buyer_window import BuyerWindow
from shared.schemas import ProductoIn, ProductoUpdate, UsuarioIn, UsuarioUpdate
from tests.e2e.helpers import crear_oferta, entrar, esperar, esperar_ofertas

pytestmark = pytest.mark.e2e


def _medir(espera, condicion, timeout=8.0):
    t0 = time.monotonic()
    ok = espera(condicion, timeout)
    return ok, time.monotonic() - t0


def test_admin_crea_edita_y_el_comprador_lo_ve_por_websocket(servidor, crear_app, api_admin, espera):
    a = crear_app(servidor)
    entrar(a, "comprador", servidor.comp_pw)
    v = a.ventana
    assert isinstance(v, BuyerWindow)
    assert espera(lambda: v.estado in ("lista", "vacio") and a.eventos.esta_conectado, 15)
    # el refresco manual y el sondeo de respaldo no intervienen: se vigila que nadie los dispare
    llamadas_cargar = []
    orig = v.ctx.api.listar_ofertas
    v.ctx.api.listar_ofertas = lambda: (llamadas_cargar.append(time.monotonic()), orig())[1]
    lat = {}

    # 1. el admin CREA un producto en oferta -> aparece la tarjeta
    p = crear_oferta(api_admin, stock=10, precio=12000, nombre="Yogur tiempo real")
    ok, lat["crear"] = _medir(espera, lambda: p.id in v.tarjetas)
    assert ok, "la tarjeta del producto nuevo no aparecio"
    t = v.tarjetas[p.id]
    assert t.stock == 10 and t.lbl_descuento.text() == "-50%" and t.lbl_final.text() == "$6.000"

    # 2. el admin EDITA el stock -> la tarjeta cambia sin refrescar
    api_admin.actualizar_producto(p.id, ProductoUpdate(stock=4))
    ok, lat["stock"] = _medir(espera, lambda: v.tarjetas[p.id].stock == 4)
    assert ok and "<b>4</b>" in v.tarjetas[p.id].lbl_detalle.text()

    # 3. el admin cambia la regla de descuento -> cambia la oferta
    api_admin.actualizar_config({"descuento_critico": 30})
    ok, lat["descuento"] = _medir(espera, lambda: p.id in v.tarjetas and v.tarjetas[p.id].lbl_descuento.text() == "-30%")
    api_admin.actualizar_config({"descuento_critico": 50})
    assert ok and v.tarjetas[p.id].lbl_final.text() == "$8.400"       # 12.000 - 30 %
    ok, _ = _medir(espera, lambda: v.tarjetas[p.id].lbl_descuento.text() == "-50%")
    assert ok

    # 4. el admin DESACTIVA el producto -> la tarjeta desaparece
    api_admin.actualizar_producto(p.id, ProductoUpdate(activo=False))
    ok, lat["desactivar"] = _medir(espera, lambda: p.id not in v.tarjetas)
    assert ok

    # 5. un producto SIN oferta (vence en 60 dias) no genera tarjeta
    q = api_admin.crear_producto(ProductoIn(nombre="Arroz sin oferta", precio_base=3000, stock=50, stock_maximo=1000,
                                            fecha_vencimiento=datetime.now() + timedelta(days=60)))
    espera(lambda: False, 1.5)
    assert q.id not in v.tarjetas

    # el refresco que hubo fue disparado por eventos WS (debounce 300 ms), nunca por el usuario
    assert llamadas_cargar, "no hubo recargas del catalogo"
    print("\n[5] latencias servidor->pantalla (s): " + ", ".join(f"{k}={x:.2f}" for k, x in lat.items())
          + f"; recargas silenciosas disparadas por eventos: {len(llamadas_cargar)}")
    assert max(lat.values()) < 3.0


def test_admin_desactiva_al_comprador_y_su_sesion_cae_con_el_motivo(servidor, crear_app, api_admin, espera):
    u = api_admin.crear_usuario(UsuarioIn(nombre="Victima E2E", usuario="victima_e2e", password="clave-victima-1"))
    a = crear_app(servidor)
    entrar(a, "victima_e2e", "clave-victima-1")
    token = a.sesion.token
    assert espera(lambda: a.eventos.esta_conectado, 15)
    t0 = time.monotonic()
    api_admin.actualizar_usuario(u.id, UsuarioUpdate(activo=False))
    assert espera(lambda: a.sesion is None, 10), "la sesion siguio abierta tras desactivar al usuario"
    dt = time.monotonic() - t0
    assert a.login.isVisible()
    assert a.login.lbl_aviso.text() == "Tu usuario fue desactivado por un administrador"
    # el token viejo ya no sirve y el usuario no puede volver a entrar
    c = ApiClient(servidor.url, token=token)
    with pytest.raises(ApiError) as e:
        c.estado_sesion()
    assert e.value.http == 401 and e.value.codigo == "SESION_CERRADA"
    assert e.value.detalle.get("motivo") == "usuario_desactivado"
    c.cerrar()
    c2 = ApiClient(servidor.url)
    with pytest.raises(ApiError) as e2:
        c2.login("victima_e2e", "clave-victima-1")
    assert e2.value.http == 401
    c2.cerrar()
    print(f"\n[5b] sesion cerrada {dt:.2f} s despues de desactivar; login muestra "
          f"'{a.login.lbl_aviso.text()}'; token viejo -> {e.value.http} {e.value.codigo} "
          f"motivo={e.value.detalle.get('motivo')}; relogin -> {e2.value.http} {e2.value.codigo}")


@pytest.mark.xfail(strict=False, reason=(
    "BUG servidor (server/application/inventario_service.py, InventarioService.editar): solo publica "
    "stock_actualizado si cambian stock o activo. Editar precio_base, fecha_vencimiento, nombre, categoria "
    "o stock_maximo NO emite ningun evento WS, y el sondeo de respaldo del cliente solo corre con el "
    "socket caido: el comprador conectado ve datos obsoletos hasta el siguiente evento no relacionado."))
def test_bug_editar_precio_o_vencimiento_no_notifica_por_ws(servidor, crear_app, api_admin, espera):
    a = crear_app(servidor)
    entrar(a, "comprador", servidor.comp_pw)
    v = a.ventana
    p = crear_oferta(api_admin, stock=10, precio=12000, nombre="Producto precio obsoleto")
    assert espera(lambda: p.id in v.tarjetas, 8)
    espera(lambda: False, 2.0)                       # deja drenar el refresco del evento de alta
    vistos = []
    a.evento_ws.connect(lambda n, pl: vistos.append(n))
    api_admin.actualizar_producto(p.id, ProductoUpdate(precio_base=20000))
    assert next(x for x in api_admin.listar_productos() if x.id == p.id).precio_base == 20000   # el servidor SI cambio
    ok = espera(lambda: v.tarjetas[p.id].lbl_original.text() == "$20.000", 6)
    print(f"\n[bug] eventos WS recibidos tras editar precio: {vistos}; tarjeta muestra {v.tarjetas[p.id].lbl_original.text()}")
    assert ok, f"precio obsoleto en el comprador tras 6 s; eventos WS: {vistos}"
