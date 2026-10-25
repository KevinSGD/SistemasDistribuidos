"""API de consulta/auditoria de facturas (solo lectura)."""
import pytest

from .conftest import COMP_PW, login

B = "/api/v1"


@pytest.fixture
def comprador2(client, admin):
    r = client.post(f"{B}/usuarios", headers=admin[0], json={
        "nombre": "Segundo Comprador", "usuario": "comp2", "password": "clave-segura-123"})
    assert r.status_code == 201, r.text
    d = login(client, "comp2", "clave-segura-123")
    return {"Authorization": f"Bearer {d['token']}"}, d


def comprar(client, headers, pid, cant, metodo="efectivo", nombre="Ana Pérez", doc="123"):
    pago = {"metodo": metodo}
    if metodo == "efectivo":
        pago["efectivo_recibido"] = 100000
    r = client.post(f"{B}/compras", headers=headers, json={
        "items": [{"producto_id": pid, "cantidad": cant}],
        "cliente": {"nombre": nombre, "documento": doc}, "pago": pago})
    assert r.status_code == 201, r.text
    return r.json()


@pytest.fixture
def facturas(client, admin, comprador, comprador2, crear_producto):
    a = crear_producto(nombre="Leche", precio_base=1000.0, stock=100)
    b = crear_producto(nombre="Pan", precio_base=500.0, stock=100)
    f1 = comprar(client, comprador[0], a["id"], 2)
    f2 = comprar(client, comprador2[0], b["id"], 5, "tarjeta_simulada", "José Núñez", "999")
    f3 = comprar(client, comprador[0], b["id"], 1, "tarjeta_simulada", "Luis", "555")
    return f1, f2, f3


def nums(r):
    assert r.status_code == 200, r.text
    return [f["numero"] for f in r.json()]


def test_admin_ve_todas_mas_recientes_primero_con_cuenta(client, admin, facturas):
    f1, f2, f3 = facturas
    r = client.get(f"{B}/facturas", headers=admin[0])
    assert nums(r) == [f3["numero"], f2["numero"], f1["numero"]]
    nombres = [f["usuario_nombre"] for f in r.json()]
    assert nombres[1] == "Segundo Comprador" and nombres[0] == nombres[2] != nombres[1]
    assert all(nombres)
    assert r.json()[1]["cliente"]["nombre"] == "José Núñez"


def test_comprador_solo_las_suyas_e_ignora_usuario_id(client, comprador, comprador2, facturas):
    f1, f2, f3 = facturas
    assert nums(client.get(f"{B}/facturas", headers=comprador[0])) == [f3["numero"], f1["numero"]]
    uid2 = f2["usuario_id"]
    r = client.get(f"{B}/facturas", params={"usuario_id": uid2}, headers=comprador[0])
    assert nums(r) == [f3["numero"], f1["numero"]]
    assert nums(client.get(f"{B}/facturas", headers=comprador2[0])) == [f2["numero"]]


def test_filtros_admin(client, admin, facturas):
    f1, f2, f3 = facturas
    h = admin[0]
    assert nums(client.get(f"{B}/facturas", params={"q": "nunez"}, headers=h)) == [f2["numero"]]
    assert nums(client.get(f"{B}/facturas", params={"q": "999"}, headers=h)) == [f2["numero"]]
    assert nums(client.get(f"{B}/facturas", params={"q": f1["numero"]}, headers=h)) \
        == [f1["numero"]]
    assert nums(client.get(f"{B}/facturas", params={"metodo_pago": "tarjeta_simulada"},
                           headers=h)) == [f3["numero"], f2["numero"]]
    assert nums(client.get(f"{B}/facturas", params={"usuario_id": f2["usuario_id"]},
                           headers=h)) == [f2["numero"]]
    assert nums(client.get(f"{B}/facturas", params={"limite": 1, "offset": 1}, headers=h)) \
        == [f2["numero"]]
    assert nums(client.get(f"{B}/facturas", params={"desde": "2999-01-01T00:00:00"},
                           headers=h)) == []
    assert len(nums(client.get(f"{B}/facturas", params={
        "desde": "2000-01-01", "hasta": "2999-01-01T00:00:00"}, headers=h))) == 3


@pytest.mark.parametrize("params", [{"limite": 0}, {"limite": 1001}, {"offset": -1},
                                    {"metodo_pago": "cheque"}, {"usuario_id": 0},
                                    {"desde": "no-es-fecha"}])
def test_validacion_de_parametros(client, admin, facturas, params):
    for ruta in ("/facturas", "/facturas/resumen"):
        if ruta == "/facturas/resumen" and set(params) & {"limite", "offset"}:
            continue
        r = client.get(f"{B}{ruta}", params=params, headers=admin[0])
        assert r.status_code == 422 and r.json()["codigo"] == "VALIDACION", (ruta, params)


def test_limite_maximo_1000_aceptado(client, admin, facturas):
    assert len(nums(client.get(f"{B}/facturas", params={"limite": 1000}, headers=admin[0]))) == 3


def test_resumen_admin(client, admin, facturas):
    f1, f2, f3 = facturas
    r = client.get(f"{B}/facturas/resumen", headers=admin[0])
    assert r.status_code == 200, r.text
    j = r.json()
    lista = client.get(f"{B}/facturas", headers=admin[0]).json()
    assert j["cantidad"] == 3 and j["total"] == round(sum(f["total"] for f in lista))
    assert j["ahorro"] == round(sum(f["ahorro"] for f in lista))
    assert j["iva"] == round(sum(f["iva"] for f in lista))
    assert j["ticket_promedio"] == round(j["total"] / 3)
    assert {m["metodo"]: m["cantidad"] for m in j["por_metodo"]} == {
        "efectivo": 1, "tarjeta_simulada": 2}
    assert j["top_productos"][0]["nombre"] == "Pan" and j["top_productos"][0]["unidades"] == 6
    assert j["desde"] and j["hasta"] and j["desde"] <= j["hasta"]
    assert all(isinstance(j[k], int) for k in ("subtotal", "ahorro", "iva", "total"))
    # mismos filtros que la lista
    r = client.get(f"{B}/facturas/resumen", params={"metodo_pago": "efectivo"}, headers=admin[0])
    assert r.json()["cantidad"] == 1
    r = client.get(f"{B}/facturas/resumen", params={"q": "nunez"}, headers=admin[0])
    assert r.json()["cantidad"] == 1 and r.json()["total"] == f2["total"]


def test_resumen_vacio(client, admin):
    j = client.get(f"{B}/facturas/resumen", headers=admin[0]).json()
    assert j["cantidad"] == 0 and j["total"] == 0 and j["desde"] is None
    assert j["por_metodo"] == [] and j["top_productos"] == []


def test_resumen_403_comprador_y_401_sin_token(client, comprador, facturas):
    r = client.get(f"{B}/facturas/resumen", headers=comprador[0])
    assert r.status_code == 403 and r.json()["codigo"] == "ROL_NO_PERMITIDO"
    assert client.get(f"{B}/facturas/resumen").status_code == 401


def test_resumen_no_se_confunde_con_numero(client, admin, comprador, facturas):
    # /facturas/{numero} sigue funcionando y un numero inexistente da 404 (no 200 del resumen)
    f1 = facturas[0]
    assert client.get(f"{B}/facturas/{f1['numero']}", headers=admin[0]).json()["numero"] \
        == f1["numero"]
    assert client.get(f"{B}/facturas/FAC-999999", headers=admin[0]).status_code == 404
    j = client.get(f"{B}/facturas/resumen", headers=admin[0]).json()
    assert "cantidad" in j and "numero" not in j


def test_detalle_incluye_cuenta_y_comprador_no_ve_ajena(client, admin, comprador, facturas):
    f2 = facturas[1]
    d = client.get(f"{B}/facturas/{f2['numero']}", headers=admin[0]).json()
    assert d["usuario_nombre"] == "Segundo Comprador"
    assert client.get(f"{B}/facturas/{f2['numero']}", headers=comprador[0]).status_code == 404


@pytest.mark.parametrize("metodo", ["put", "patch", "delete", "post"])
def test_facturas_son_inmutables_sin_rutas_de_escritura(client, admin, facturas, metodo):
    f = facturas[0]["numero"]
    for ruta in (f"{B}/facturas/{f}", f"{B}/facturas", f"{B}/facturas/{f}/anular",
                 f"{B}/facturas/resumen"):
        r = getattr(client, metodo)(ruta, headers=admin[0])
        assert r.status_code in (404, 405), (metodo, ruta, r.status_code)


def test_ws_factura_creada_solo_para_admin(client, admin, comprador, comprador2, crear_producto):
    p = crear_producto(stock=10, precio_base=100.0)
    with client.websocket_connect(f"/ws?token={comprador2[1]['token']}") as wc, \
            client.websocket_connect(f"/ws?token={admin[1]['token']}") as wa:
        f = comprar(client, comprador[0], p["id"], 1)
        eventos_admin = [wa.receive_json() for _ in range(2)]
        assert {e["evento"] for e in eventos_admin} == {"stock_actualizado", "factura_creada"}
        fc = next(e for e in eventos_admin if e["evento"] == "factura_creada")
        assert fc["payload"] == {"numero": f["numero"], "total": f["total"],
                                 "metodo_pago": "efectivo"}
        # el otro comprador solo recibe stock_actualizado, nunca factura_creada
        assert wc.receive_json()["evento"] == "stock_actualizado"
        client.put(f"{B}/config", json={"moneda": "COP"}, headers=admin[0])
        assert wc.receive_json()["evento"] == "config_cambiada"
