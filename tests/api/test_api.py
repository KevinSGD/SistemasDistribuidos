from datetime import datetime, timedelta

import jwt
import pytest
from starlette.websockets import WebSocketDisconnect

from .conftest import ADMIN_PW, COMP_PW, login

B = "/api/v1"


def compra(pid, cant=1, efectivo=1000.0):
    return {"items": [{"producto_id": pid, "cantidad": cant}],
            "cliente": {"nombre": "Ana", "documento": "123"},
            "pago": {"metodo": "efectivo", "efectivo_recibido": efectivo}}


# -- health / openapi -----------------------------------------------------------------------
def test_health_publico_y_openapi(client):
    r = client.get(f"{B}/health")
    assert r.status_code == 200
    j = r.json()
    assert j["estado"] == "ok" and j["version"] and j["so"]
    spec = client.get("/openapi.json")
    assert spec.status_code == 200 and f"{B}/compras" in spec.json()["paths"]


def test_ruta_inexistente_y_validacion_con_formato_de_error(client, admin):
    r = client.get(f"{B}/nada")
    assert r.status_code == 404 and r.json()["codigo"] == "NO_ENCONTRADO"
    r = client.post(f"{B}/auth/login", json={"usuario": "x"})
    assert r.status_code == 422
    j = r.json()
    assert j["codigo"] == "VALIDACION" and j["detalle"]["errores"]


# -- login ----------------------------------------------------------------------------------
def test_login_ok(client):
    d = login(client)
    assert d["usuario"]["rol"] == "admin" and d["token"]
    assert d["sesion"] == {"inactividad_segundos": 180, "aviso_segundos": 30}


def test_login_mal_y_bloqueo_429(client):
    for _ in range(5):
        r = client.post(f"{B}/auth/login", json={"usuario": "admin", "password": "mala"})
        assert r.status_code == 401 and r.json()["codigo"] == "CREDENCIALES_INVALIDAS"
    r = client.post(f"{B}/auth/login", json={"usuario": "admin", "password": ADMIN_PW})
    assert r.status_code == 429
    j = r.json()
    assert j["codigo"] == "TOO_MANY_ATTEMPTS" and j["detalle"]["reintentar_en_segundos"] > 0
    assert "retry-after" in r.headers


def test_sin_token_o_manipulado_401(client, admin):
    assert client.get(f"{B}/productos").json()["codigo"] == "TOKEN_INVALIDO"
    h = {"Authorization": admin[0]["Authorization"][:-3] + "abc"}
    r = client.get(f"{B}/productos", headers=h)
    assert r.status_code == 401 and r.json()["codigo"] == "TOKEN_INVALIDO"
    ajeno = jwt.encode({"sub": "1", "rol": "admin", "jti": "x", "exp": 9999999999},
                       "otro-secreto" * 4, "HS256")
    r = client.get(f"{B}/productos", headers={"Authorization": f"Bearer {ajeno}"})
    assert r.status_code == 401


# -- roles ----------------------------------------------------------------------------------
def test_comprador_no_accede_a_admin(client, comprador, crear_producto):
    h = comprador[0]
    assert client.get(f"{B}/config", headers=h).status_code == 403
    assert client.put(f"{B}/config", json={"moneda": "X"}, headers=h).status_code == 403
    r = client.post(f"{B}/productos", json={"nombre": "X", "precio_base": 1}, headers=h)
    assert r.status_code == 403 and r.json()["codigo"] == "ROL_NO_PERMITIDO"
    assert client.get(f"{B}/usuarios", headers=h).status_code == 403
    assert client.get(f"{B}/riesgo/resumen", headers=h).status_code == 403
    assert client.post(f"{B}/riesgo/escaneo", headers=h).status_code == 403
    # lo que si puede
    assert client.get(f"{B}/productos", headers=h).status_code == 200
    assert client.get(f"{B}/ofertas", headers=h).status_code == 200
    assert client.get(f"{B}/config/publica", headers=h).status_code == 200


# -- productos / riesgo ---------------------------------------------------------------------
def test_crud_productos_y_riesgo(client, admin, crear_producto):
    h = admin[0]
    p = crear_producto(nombre="Yogur", stock=5, fecha_vencimiento=(datetime.now() + timedelta(days=1)).isoformat())
    assert p["id"] and p["stock"] == 5
    r = client.put(f"{B}/productos/{p['id']}", json={"precio_base": 12.5}, headers=h)
    assert r.status_code == 200 and r.json()["precio_base"] == 12.5
    assert client.put(f"{B}/productos/9999", json={"precio_base": 1}, headers=h).status_code == 404
    assert client.put(f"{B}/productos/{p['id']}", json={"precio_base": -1}, headers=h).status_code == 422
    esc = client.post(f"{B}/riesgo/escaneo", headers=h).json()
    assert esc["evaluados"] == 1 and esc["descuentos_aplicados"]
    ofertas = client.get(f"{B}/ofertas", headers=h).json()
    assert ofertas[0]["descuento"] == 50.0 and ofertas[0]["precio_final"] == 6.25
    assert client.get(f"{B}/riesgo/resumen", headers=h).json()["total_activos"] == 1
    assert "critico" in client.get(f"{B}/riesgo/alertas", headers=h).json()
    assert client.delete(f"{B}/productos/{p['id']}", headers=h).status_code == 204
    assert client.get(f"{B}/productos", headers=h).json() == []
    assert len(client.get(f"{B}/productos?activos=false", headers=h).json()) == 1


# -- compras --------------------------------------------------------------------------------
def test_compra_feliz_factura_completa(client, comprador, admin, crear_producto):
    p = crear_producto(precio_base=10.0, stock=20)
    r = client.post(f"{B}/compras", json=compra(p["id"], 3, 50.0), headers=comprador[0])
    assert r.status_code == 201, r.text
    f = r.json()
    assert f["numero"] and f["total"] == 30.0 and f["cambio"] == 20.0
    assert f["items"][0] == {"producto_id": p["id"], "nombre": "Leche", "cantidad": 3,
                             "precio_original": 10.0, "descuento_pct": 0.0, "precio_final": 10.0,
                             "subtotal": 30.0}
    assert f["negocio"]["nombre_negocio"] and f["cliente"]["nombre"] == "Ana"
    assert f["subtotal"] == 30.0 and f["ahorro"] == 0.0 and f["metodo_pago"] == "efectivo"
    stock = client.get(f"{B}/productos", headers=admin[0]).json()[0]["stock"]
    assert stock == 17
    assert client.get(f"{B}/facturas/{f['numero']}", headers=comprador[0]).json()["total"] == 30.0
    assert len(client.get(f"{B}/facturas", headers=comprador[0]).json()) == 1
    assert len(client.get(f"{B}/facturas", headers=admin[0]).json()) == 1


def test_compra_stock_insuficiente_sin_cambios(client, comprador, admin, crear_producto):
    a = crear_producto(nombre="A", stock=5)
    b = crear_producto(nombre="B", stock=1)
    body = {"items": [{"producto_id": a["id"], "cantidad": 2}, {"producto_id": b["id"], "cantidad": 3}],
            "pago": {"metodo": "tarjeta_simulada"}}
    r = client.post(f"{B}/compras", json=body, headers=comprador[0])
    assert r.status_code == 409 and r.json()["codigo"] == "STOCK_INSUFICIENTE"
    stocks = {p["nombre"]: p["stock"] for p in client.get(f"{B}/productos", headers=admin[0]).json()}
    assert stocks == {"A": 5, "B": 1}
    assert client.get(f"{B}/facturas", headers=admin[0]).json() == []


def test_compra_producto_vencido_409(client, comprador, crear_producto):
    p = crear_producto(fecha_vencimiento=(datetime.now() - timedelta(days=2)).isoformat())
    r = client.post(f"{B}/compras", json=compra(p["id"]), headers=comprador[0])
    assert r.status_code == 409 and r.json()["codigo"] == "PRODUCTO_VENCIDO"


def test_compra_efectivo_insuficiente_y_validacion(client, comprador, crear_producto):
    p = crear_producto(precio_base=10.0)
    r = client.post(f"{B}/compras", json=compra(p["id"], 2, 5.0), headers=comprador[0])
    assert r.status_code == 422 and r.json()["codigo"] == "EFECTIVO_INSUFICIENTE"
    r = client.post(f"{B}/compras", json=compra(p["id"], 0), headers=comprador[0])
    assert r.status_code == 422 and r.json()["codigo"] == "VALIDACION"
    r = client.post(f"{B}/compras", json={"items": [], "pago": {"metodo": "efectivo"}},
                    headers=comprador[0])
    assert r.status_code == 422


# -- inactividad ----------------------------------------------------------------------------
def test_inactividad_sin_actividad_expira(client, comprador, reloj):
    h = comprador[0]
    reloj.avanzar(181)
    r = client.get(f"{B}/productos", headers=h)
    assert r.status_code == 401 and r.json()["codigo"] == "SESION_INACTIVA"
    assert client.get(f"{B}/productos", headers=h).json()["codigo"] == "SESION_CERRADA"


def test_lectura_no_renueva_y_actividad_si(client, comprador, reloj):
    h = comprador[0]
    for _ in range(3):                       # 3 x 100 s de lecturas: no renuevan
        reloj.avanzar(100)
        if _ < 1:
            assert client.get(f"{B}/productos", headers=h).status_code == 200
            assert client.get(f"{B}/auth/sesion", headers=h).status_code == 200
    r = client.get(f"{B}/productos", headers=h)
    assert r.status_code == 401 and r.json()["codigo"] == "SESION_INACTIVA"


def test_actividad_renueva(client, comprador, reloj):
    h = comprador[0]
    for _ in range(4):                       # 4 x 100 s = 400 s > 180 s, pero con actividad
        reloj.avanzar(100)
        r = client.post(f"{B}/auth/actividad", headers=h)
        assert r.status_code == 200 and r.json()["segundos_restantes"] == 180
        assert client.get(f"{B}/productos", headers=h).status_code == 200
    s = client.get(f"{B}/auth/sesion", headers=h).json()
    assert s["segundos_restantes"] == 180


def test_actividad_de_sesion_caducada_no_revive(client, comprador, reloj):
    reloj.avanzar(500)
    r = client.post(f"{B}/auth/actividad", headers=comprador[0])
    assert r.status_code == 401 and r.json()["codigo"] == "SESION_INACTIVA"


def test_cambio_de_inactividad_por_admin_aplica_a_sesion_abierta(client, admin, comprador, reloj):
    reloj.avanzar(60)                        # con 180 s la sesion del comprador seguiria viva
    r = client.put(f"{B}/config", json={"inactividad_segundos": 30, "aviso_segundos": 10},
                   headers=admin[0])
    assert r.status_code == 200 and r.json()["inactividad_segundos"] == 30
    r = client.get(f"{B}/productos", headers=comprador[0])
    assert r.status_code == 401 and r.json()["codigo"] == "SESION_INACTIVA"


def test_logout_revoca(client, comprador):
    assert client.post(f"{B}/auth/logout", headers=comprador[0]).status_code == 200
    r = client.get(f"{B}/productos", headers=comprador[0])
    assert r.status_code == 401 and r.json()["codigo"] == "SESION_CERRADA"


# -- config ---------------------------------------------------------------------------------
def test_put_config_valida_rangos(client, admin, comprador):
    h = admin[0]
    for cuerpo in ({"inactividad_segundos": 5}, {"inactividad_segundos": 99999},
                   {"descuento_alto": 150}, {"aviso_segundos": 500},
                   {"inactividad_segundos": "abc"}, {"clave_inventada": 1}, {}):
        r = client.put(f"{B}/config", json=cuerpo, headers=h)
        assert r.status_code == 422 and r.json()["codigo"] == "VALIDACION", cuerpo
    cfg = client.get(f"{B}/config", headers=h).json()
    assert cfg["inactividad_segundos"] == 180
    r = client.put(f"{B}/config", json={"nombre_negocio": "Tienda Z", "iva_pct": 19}, headers=h)
    assert r.status_code == 200 and r.json()["nombre_negocio"] == "Tienda Z"
    assert client.get(f"{B}/config/publica", headers=comprador[0]).json()["nombre_negocio"] == "Tienda Z"


# -- usuarios -------------------------------------------------------------------------------
def test_usuarios_crud(client, admin):
    h = admin[0]
    r = client.post(f"{B}/usuarios", json={"nombre": "Luis", "usuario": "luis",
                                           "password": "corta"}, headers=h)
    assert r.status_code == 422 and r.json()["codigo"] == "VALIDACION"
    r = client.post(f"{B}/usuarios", json={"nombre": "Luis", "usuario": "luis",
                                           "password": "clave-larga-1"}, headers=h)
    assert r.status_code == 201 and "password" not in r.text and "hash" not in r.text
    uid = r.json()["id"]
    assert client.post(f"{B}/usuarios", json={"nombre": "L", "usuario": "luis",
                                              "password": "clave-larga-1"},
                       headers=h).json()["codigo"] == "USUARIO_DUPLICADO"
    assert {u["usuario"] for u in client.get(f"{B}/usuarios", headers=h).json()} == \
        {"admin", "comprador", "luis"}
    login(client, "luis", "clave-larga-1")
    r = client.put(f"{B}/usuarios/{uid}", json={"password": "nueva-clave-9"}, headers=h)
    assert r.status_code == 200
    assert client.post(f"{B}/auth/login", json={"usuario": "luis", "password": "clave-larga-1"}
                       ).status_code == 401
    login(client, "luis", "nueva-clave-9")
    assert client.put(f"{B}/usuarios/9999", json={"activo": False}, headers=h).status_code == 404
    yo = admin[1]["usuario"]["id"]
    assert client.put(f"{B}/usuarios/{yo}", json={"activo": False}, headers=h).status_code == 422


def test_desactivar_usuario_cierra_sesiones_y_bloquea_login(client, admin, comprador):
    uid = comprador[1]["usuario"]["id"]
    r = client.put(f"{B}/usuarios/{uid}", json={"activo": False}, headers=admin[0])
    assert r.status_code == 200 and r.json()["activo"] is False
    assert client.get(f"{B}/productos", headers=comprador[0]).status_code == 401
    assert client.post(f"{B}/auth/login", json={"usuario": "comprador", "password": COMP_PW}
                       ).status_code == 401


# -- websocket ------------------------------------------------------------------------------
def test_ws_token_invalido_cierra_4401(client):
    with client.websocket_connect("/ws?token=basura") as ws:
        with pytest.raises(WebSocketDisconnect) as e:
            ws.receive_json()
    assert e.value.code == 4401
    with client.websocket_connect("/ws") as ws:
        with pytest.raises(WebSocketDisconnect) as e:
            ws.receive_json()
    assert e.value.code == 4401


def test_ws_recibe_stock_actualizado_por_compra_de_otro(client, admin, comprador, crear_producto):
    p = crear_producto(stock=10)
    with client.websocket_connect(f"/ws?token={admin[1]['token']}") as ws:
        r = client.post(f"{B}/compras", json=compra(p["id"], 4), headers=comprador[0])
        assert r.status_code == 201
        ev = ws.receive_json()
        assert ev["evento"] == "stock_actualizado"
        assert ev["payload"]["producto_id"] == p["id"] and ev["payload"]["stock"] == 6


def test_ws_filtra_por_destinatario(client, admin, comprador, crear_producto):
    with client.websocket_connect(f"/ws?token={comprador[1]['token']}") as wc, \
            client.websocket_connect(f"/ws?token={admin[1]['token']}") as wa:
        client.put(f"{B}/config", json={"moneda": "COP"}, headers=admin[0])
        assert wc.receive_json() == {"evento": "config_cambiada", "payload": {"claves": ["moneda"]}}
        assert wa.receive_json()["evento"] == "config_cambiada"
        # productos_retirados es solo para admin
        crear_producto(nombre="Viejo", fecha_vencimiento=(datetime.now() - timedelta(days=1)).isoformat())
        wa.receive_json()      # stock_actualizado de la creacion
        wc.receive_json()
        client.post(f"{B}/riesgo/escaneo", headers=admin[0])
        ev = wa.receive_json()
        assert ev == {"evento": "productos_retirados", "payload": {"nombres": ["Viejo"]}}
        client.put(f"{B}/config", json={"moneda": "USD"}, headers=admin[0])
        # el comprador NO recibio productos_retirados: su siguiente evento es la config
        assert wc.receive_json()["evento"] == "config_cambiada"
        assert wa.receive_json()["evento"] == "config_cambiada"


def test_ws_recibe_sesion_cerrada_al_logout(client, comprador):
    with client.websocket_connect(f"/ws?token={comprador[1]['token']}") as ws:
        client.post(f"{B}/auth/logout", headers=comprador[0])
        ev = ws.receive_json()
        assert ev == {"evento": "sesion_cerrada", "payload": {"motivo": "logout"}}
        with pytest.raises(WebSocketDisconnect) as e:
            ws.receive_json()
    assert e.value.code == 4401


def test_ws_recibe_sesion_cerrada_al_desactivar(client, admin, comprador):
    uid = comprador[1]["usuario"]["id"]
    with client.websocket_connect(f"/ws?token={comprador[1]['token']}") as ws:
        client.put(f"{B}/usuarios/{uid}", json={"activo": False}, headers=admin[0])
        ev = ws.receive_json()
        assert ev["evento"] == "sesion_cerrada" and ev["payload"]["motivo"] == "usuario_desactivado"
        with pytest.raises(WebSocketDisconnect) as e:
            ws.receive_json()
    assert e.value.code == 4401


def test_ws_detecta_caducidad_por_inactividad_sin_renovar(client, comprador, reloj):
    with client.websocket_connect(f"/ws?token={comprador[1]['token']}") as ws:
        ws.send_text("hola")                  # lo que envie el cliente no cuenta como actividad
        reloj.avanzar(500)
        ev = ws.receive_json()                # el chequeo periodico (0.2 s en tests) la detecta
        assert ev == {"evento": "sesion_cerrada", "payload": {"motivo": "inactividad"}}
        with pytest.raises(WebSocketDisconnect) as e:
            ws.receive_json()
    assert e.value.code == 4401


def test_ws_logout_de_otra_sesion_no_cierra_esta(client, comprador):
    otra = login(client, "comprador", COMP_PW)
    with client.websocket_connect(f"/ws?token={comprador[1]['token']}") as ws:
        client.post(f"{B}/auth/logout", headers={"Authorization": f"Bearer {otra['token']}"})
        client.put(f"{B}/config", json={"moneda": "X"},
                   headers={"Authorization": f"Bearer {login(client)['token']}"})
        assert ws.receive_json()["evento"] == "config_cambiada"   # sigue conectado


def test_ws_desconexion_no_deja_suscriptores(client, comprador):
    bus = client.app.state.servicios.bus
    base = len(bus._subs)
    for _ in range(3):
        with client.websocket_connect(f"/ws?token={comprador[1]['token']}"):
            pass
    import time
    for _ in range(50):
        if len(bus._subs) == base:
            break
        time.sleep(0.05)
    assert len(bus._subs) == base


def test_scheduler_arranca_y_se_detiene(tmp_path):
    from fastapi.testclient import TestClient
    from server.api.app import crear_app
    app = crear_app(tmp_path / "s.db", iniciar_scheduler=True)
    with TestClient(app):
        sch = app.state.servicios.scheduler
        assert sch.activo
    assert not sch.activo
