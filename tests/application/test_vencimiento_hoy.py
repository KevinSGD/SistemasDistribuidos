"""Regresion: una fecha de vencimiento SIN hora (medianoche) vale hasta el final de ese dia.

Bug original: un producto que vence HOY, guardado a las 00:00, aparecia ya vencido, salia de las
ofertas y el siguiente escaneo lo daba de baja."""
from datetime import datetime, timedelta

import pytest

from server.application.errores import ErrorValidacion
from server.domain.errors import ProductoInactivo, ProductoVencido
from server.infrastructure.db.engine import sesion
from server.infrastructure.db.orm import ProductoORM
from server.infrastructure.db.repos import ProductoRepo
from server.infrastructure.db.seed import normalizar_vencimientos

from .conftest import AHORA

HOY_00 = AHORA.replace(hour=0, minute=0, second=0)
HOY_FIN = AHORA.replace(hour=23, minute=59, second=59)
CLI = {"nombre": "Ana", "documento": "123"}
TARJ = {"metodo": "tarjeta_simulada"}
DATOS = {"nombre": "Leche", "categoria": "Lacteos", "precio_base": 10.0, "stock": 20,
         "stock_maximo": 1000}


def _crear(inventario, **extra):
    return inventario.crear({**DATOS, **extra}, "admin")


# -- normalizacion en el servicio -------------------------------------------------------------
def test_medianoche_se_guarda_como_fin_de_dia(inventario):
    p = _crear(inventario, fecha_vencimiento=HOY_00)
    assert p.fecha_vencimiento == HOY_FIN
    q = _crear(inventario, nombre="B", fecha_vencimiento="2030-01-05")
    assert q.fecha_vencimiento == datetime(2030, 1, 5, 23, 59, 59)
    r = _crear(inventario, nombre="C", fecha_vencimiento="2030-01-05T00:00:00+00:00")
    assert r.fecha_vencimiento == datetime(2030, 1, 5, 23, 59, 59)


def test_hora_explicita_se_respeta(inventario):
    h = AHORA.replace(hour=15, minute=30)
    assert _crear(inventario, fecha_vencimiento=h).fecha_vencimiento == h
    assert _crear(inventario, nombre="B", fecha_vencimiento=AHORA.replace(
        hour=0, minute=0, second=1)).fecha_vencimiento.second == 1


def test_editar_normaliza_y_es_idempotente(inventario):
    p = _crear(inventario)
    e = inventario.editar(p.id, {"fecha_vencimiento": "2030-03-01T00:00:00"}, "admin")
    assert e.fecha_vencimiento == datetime(2030, 3, 1, 23, 59, 59)
    e2 = inventario.editar(p.id, {"fecha_vencimiento": e.fecha_vencimiento.isoformat()}, "admin")
    assert e2.fecha_vencimiento == e.fecha_vencimiento


# -- el caso del bug: vence HOY -----------------------------------------------------------------
def test_vence_hoy_aparece_en_ofertas_no_se_retira_y_se_puede_comprar(
        inventario, riesgo, ventas, usuarios, factory):
    _, c1, _ = usuarios
    p = _crear(inventario, fecha_vencimiento=HOY_00)          # AHORA = 12:00, medianoche ya paso
    of = riesgo.ofertas("comprador")
    assert [o["producto_id"] for o in of] == [p.id]
    assert of[0]["nivel"] == "critico" and of[0]["descuento"] == 50.0
    assert "Vence hoy" in of[0]["motivo"]
    esc = riesgo.escanear()
    assert esc["retirados"] == []
    with sesion(factory) as s:
        assert ProductoRepo(s).obtener(p.id).activo is True
    f = ventas.comprar(c1, [{"producto_id": p.id, "cantidad": 2}], CLI, TARJ)
    assert f["numero"]


def test_ayer_es_retirado_y_rechazado(inventario, riesgo, ventas, usuarios, crear_producto, factory):
    _, c1, _ = usuarios
    ayer = crear_producto("Ayer", venc=HOY_00 - timedelta(days=1))
    assert riesgo.escanear()["retirados"] == ["Ayer"]
    assert riesgo.ofertas("comprador") == []
    with pytest.raises((ProductoInactivo, ProductoVencido)):
        ventas.comprar(c1, [{"producto_id": ayer.id, "cantidad": 1}], CLI, TARJ)


def test_hora_explicita_pasada_es_retirada_y_rechazada(inventario, riesgo, ventas, usuarios):
    _, c1, _ = usuarios
    p = _crear(inventario, fecha_vencimiento=AHORA - timedelta(minutes=5))
    with pytest.raises(ProductoVencido):
        ventas.comprar(c1, [{"producto_id": p.id, "cantidad": 1}], CLI, TARJ)
    assert riesgo.ofertas("comprador") == []
    assert riesgo.escanear()["retirados"] == ["Leche"]


def test_se_retira_cuando_pasa_el_fin_del_dia(inventario, factory, config, bus):
    from server.application.riesgo_service import RiesgoService
    _crear(inventario, fecha_vencimiento=HOY_00)
    tarde = RiesgoService(factory, config, bus, reloj=lambda: HOY_FIN + timedelta(seconds=1))
    assert tarde.escanear()["retirados"] == ["Leche"]


# -- reactivacion -------------------------------------------------------------------------------
def test_reactivar_vencido_exige_fecha_nueva(inventario, crear_producto):
    from server.application.inventario_service import InventarioService
    p = crear_producto("Viejo", venc=HOY_00 - timedelta(days=3), activo=False)
    inv = InventarioService(inventario._factory, reloj=lambda: AHORA)
    with pytest.raises(ErrorValidacion):
        inv.editar(p.id, {"activo": True}, "admin")
    r = inv.editar(p.id, {"activo": True, "fecha_vencimiento": HOY_00 + timedelta(days=10)}, "admin")
    assert r.activo and r.fecha_vencimiento == (HOY_FIN + timedelta(days=10))


def test_reactivar_producto_retirado_por_el_bug_de_hoy(inventario, crear_producto):
    from server.application.inventario_service import InventarioService
    p = crear_producto("DeHoy", venc=HOY_00, activo=False)     # tal como lo dejo el bug
    inv = InventarioService(inventario._factory, reloj=lambda: AHORA)
    r = inv.editar(p.id, {"activo": True}, "admin")
    assert r.activo and r.fecha_vencimiento == HOY_FIN


# -- normalizacion de arranque -----------------------------------------------------------------------
def test_normalizar_vencimientos_idempotente_y_selectiva(factory, crear_producto):
    hoy = crear_producto("hoy", venc=HOY_00)
    fut = crear_producto("fut", venc=HOY_00 + timedelta(days=5))
    pasado = crear_producto("pasado", venc=HOY_00 - timedelta(days=2))
    hora = crear_producto("hora", venc=HOY_00 + timedelta(hours=9))
    inactivo = crear_producto("inactivo", venc=HOY_00, activo=False)
    sin = crear_producto("sin")
    with sesion(factory) as s:
        assert normalizar_vencimientos(s, AHORA) == 2
    with sesion(factory) as s:
        assert normalizar_vencimientos(s, AHORA) == 0            # idempotente
        f = lambda p: s.get(ProductoORM, p.id).fecha_vencimiento  # noqa: E731
        assert f(hoy) == HOY_FIN
        assert f(fut) == (HOY_FIN + timedelta(days=5))
        assert f(pasado) == HOY_00 - timedelta(days=2)           # fechas pasadas intactas
        assert f(hora) == HOY_00 + timedelta(hours=9)            # hora explicita intacta
        assert f(inactivo) == HOY_00                             # inactivos intactos
        assert f(sin) is None
