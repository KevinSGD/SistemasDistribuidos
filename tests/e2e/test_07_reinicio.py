"""Escenario 7: reinicio del servidor Linux (stop/start con la MISMA base de datos).

Comprueba persistencia (productos, facturas, consecutivo), el destino de los tokens emitidos antes del
reinicio (resultado REAL documentado), que el cliente reconecta su WebSocket solo y sigue recibiendo
eventos, y que el bloqueo de intentos de login (en memoria) se reinicia."""
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from client.infrastructure.api_client import ApiClient, ApiError
from shared.schemas import ProductoUpdate, UsuarioIn
from tests.e2e.helpers import compra_tarjeta, crear_oferta, entrar, esperar, esperar_ofertas

pytestmark = pytest.mark.e2e


def test_reinicio_persistencia_token_y_reconexion_ws(servidor_propio, crear_app, espera):
    srv = servidor_propio("reinicio")
    adm = ApiClient(srv.url)
    adm.login("admin", srv.admin_pw)
    token_admin = adm.token
    p = crear_oferta(adm, stock=10, precio=10000, nombre="Producto persistente")
    f1 = adm.comprar(compra_tarjeta(p.id, 2))
    pid_antes = srv.pid

    # comprador conectado por la UI real, con su WebSocket
    a = crear_app(srv)
    entrar(a, "comprador", srv.comp_pw)
    v = a.ventana
    assert esperar_ofertas(v, p) and esperar(lambda: a.eventos.esta_conectado, 15)
    assert v.tarjetas[p.id].stock == 8
    token_comprador = a.sesion.token
    eventos_ws = []
    a.conexion_cambiada.connect(lambda c: eventos_ws.append((time.monotonic(), c)))
    sondeos = []
    a.sondeo.connect(lambda: sondeos.append(time.monotonic()))
    ws_id = id(a.eventos)

    # (bonus) el limitador de intentos esta en memoria: se agota y se pierde al reiniciar
    adm.crear_usuario(UsuarioIn(nombre="Bloqueable", usuario="bloqueable", password="clave-correcta-1"))
    usuarios_antes = {u.usuario: u.id for u in adm.listar_usuarios()}
    c_mal = ApiClient(srv.url)
    codigos = []
    for _ in range(7):
        try:
            c_mal.login("bloqueable", "incorrecta-xx")
        except ApiError as e:
            codigos.append(e.codigo)
    c_mal.cerrar()
    assert codigos[-1] == "TOO_MANY_ATTEMPTS", codigos

    # ---- reinicio (en un hilo, para que la GUI siga viva y se mida la reconexion) ----
    with ThreadPoolExecutor(1) as pool:
        t_stop = time.monotonic()
        fut = pool.submit(srv.reiniciar)
        assert esperar(lambda: any(not c for _, c in eventos_ws), 15), "el cliente no noto la caida"
        t_caida = next(t for t, c in eventos_ws if not c)
        fut.result(timeout=60)
        t_arriba = time.monotonic()
        assert esperar(lambda: any(c for t, c in eventos_ws if t > t_caida), 30), "el WS no reconecto"
    t_ws = next(t for t, c in eventos_ws if c and t > t_caida)
    assert srv.pid != pid_antes                                       # proceso nuevo
    assert id(a.eventos) == ws_id and a.sesion is not None            # mismo EventClient, sesion intacta
    assert any(s > t_caida for s in sondeos), "al reconectar debia resincronizar (sondeo)"
    assert esperar(lambda: a.ventana.barra.conexion.conectado
                   and a.ventana.barra.conexion._texto.text() == "Servidor en línea · Linux", 20)

    # ---- persistencia ----
    adm2 = ApiClient(srv.url)
    adm2.login("admin", srv.admin_pw)
    productos = {x.id: x for x in adm2.listar_productos()}
    assert productos[p.id].stock == 8 and productos[p.id].nombre == "Producto persistente"
    assert {u.usuario: u.id for u in adm2.listar_usuarios()} == usuarios_antes
    assert adm2.obtener_factura(f1.numero).total == f1.total
    f2 = adm2.comprar(compra_tarjeta(p.id, 1))
    assert int(f2.numero.split("-")[1]) == int(f1.numero.split("-")[1]) + 1     # el consecutivo sigue

    # ---- tokens anteriores al reinicio: resultado REAL ----
    # Diseno: el secreto JWT se persiste en el directorio de datos y las sesiones estan en la BD, por
    # lo que un token emitido antes del reinicio SIGUE siendo valido (si no excede inactividad/maxima).
    viejo = ApiClient(srv.url, token=token_admin)
    try:
        resultado_token = ("valido", viejo.estado_sesion().segundos_restantes)
        viejo.actualizar_config({"nombre_negocio": "Tras reinicio"})     # y permite operar
    except ApiError as e:
        resultado_token = ("rechazado", e.http, e.codigo)
    viejo.cerrar()
    assert resultado_token[0] == "valido", resultado_token

    # ---- el WS reconectado sigue entregando eventos en vivo ----
    adm2.registrar_actividad()
    adm2.actualizar_producto(p.id, ProductoUpdate(stock=3))
    assert espera(lambda: v.tarjetas[p.id].stock == 3, 8), "el WS reconectado no entrega eventos"

    # ---- el bloqueo de login (memoria) se reinicio ----
    c_ok = ApiClient(srv.url)
    try:
        out = c_ok.login("bloqueable", "clave-correcta-1")
        bloqueo = "reiniciado: login permitido"
    except ApiError as e:
        bloqueo = f"persiste: {e.codigo}"
        out = None
    c_ok.cerrar()
    adm2.cerrar()
    adm.cerrar()
    print(f"\n[7] reinicio PID {pid_antes} -> {srv.pid}; WS cae +{t_caida - t_stop:.2f} s, servidor arriba "
          f"+{t_arriba - t_stop:.2f} s, WS reconectado +{t_ws - t_stop:.2f} s ({t_ws - t_arriba:.2f} s tras arrancar); "
          f"sondeo de resincronizacion al reconectar: {len([s for s in sondeos if s > t_caida])}; "
          f"datos: stock/usuarios/factura {f1.numero} persisten, siguiente {f2.numero}; "
          f"token previo al reinicio: {resultado_token}; bloqueo de login tras reinicio: {bloqueo}")
    assert out is not None, bloqueo
