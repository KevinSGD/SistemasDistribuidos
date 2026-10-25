"""VentaService: consulta/auditoria de facturas (solo lectura) y evento factura_creada."""
import pytest
from sqlalchemy import func, select

from server.application.errores import ErrorValidacion, RolNoPermitido
from server.infrastructure.db.engine import sesion
from server.infrastructure.db.orm import FacturaORM

CLI = {"nombre": "Ana Pérez", "documento": "123"}
EFE = {"metodo": "efectivo", "efectivo_recibido": 100000}
TARJ = {"metodo": "tarjeta_simulada"}


def linea(pid, cant=1):
    return {"producto_id": pid, "cantidad": cant}


@pytest.fixture
def escenario(ventas, usuarios, crear_producto):
    admin, c1, c2 = usuarios
    p = crear_producto("Leche", 100.0, 100)
    ventas.comprar(c1, [linea(p.id, 2)], CLI, EFE)
    ventas.comprar(c2, [linea(p.id, 1)], {"nombre": "Luis", "documento": "9"}, TARJ)
    ventas.comprar(c1, [linea(p.id, 3)], {"nombre": "", "documento": ""}, TARJ)
    return usuarios, p


def test_admin_ve_todas_comprador_solo_las_suyas(ventas, escenario):
    (admin, c1, c2), _ = escenario
    assert len(ventas.listar_facturas(admin, "admin")) == 3
    assert [f["usuario_id"] for f in ventas.listar_facturas(c1, "comprador")] == [c1, c1]
    assert [f["usuario_id"] for f in ventas.listar_facturas(c2, "comprador")] == [c2]


def test_factura_trae_nombre_de_la_cuenta(ventas, escenario):
    (admin, c1, c2), _ = escenario
    fs = ventas.listar_facturas(admin, "admin")
    assert {f["usuario_nombre"] for f in fs} == {"Comp 1", "Comp 2"}
    assert fs[0]["cliente"] == {"nombre": "", "documento": ""}        # el cliente es otro campo
    assert ventas.obtener_factura(fs[0]["numero"], admin, "admin")["usuario_nombre"] == "Comp 1"


def test_comprador_ignora_filtro_de_usuario(ventas, escenario):
    (admin, c1, c2), _ = escenario
    fs = ventas.listar_facturas(c1, "comprador", filtro_usuario_id=c2)
    assert {f["usuario_id"] for f in fs} == {c1}
    assert {f["usuario_id"] for f in ventas.listar_facturas(admin, "admin", filtro_usuario_id=c2)} \
        == {c2}


def test_filtros_texto_metodo_y_paginacion(ventas, escenario):
    (admin, c1, c2), _ = escenario
    assert len(ventas.listar_facturas(admin, "admin", q="perez")) == 1
    assert len(ventas.listar_facturas(admin, "admin", metodo_pago="tarjeta_simulada")) == 2
    assert [f["numero"] for f in ventas.listar_facturas(admin, "admin", limite=1, offset=1)] \
        == ["FAC-000002"]
    # el comprador tambien puede buscar, pero solo dentro de las suyas
    assert ventas.listar_facturas(c2, "comprador", q="perez") == []


@pytest.mark.parametrize("kw", [{"limite": 0}, {"limite": 1001}, {"offset": -1},
                                {"metodo_pago": "cheque"}])
def test_validaciones(ventas, escenario, kw):
    (admin, *_), _ = escenario
    with pytest.raises(ErrorValidacion):
        ventas.listar_facturas(admin, "admin", **kw)


def test_resumen_solo_admin(ventas, escenario):
    (admin, c1, _), _ = escenario
    with pytest.raises(RolNoPermitido):
        ventas.resumen_facturas("comprador")
    with pytest.raises(RolNoPermitido):
        ventas.resumen_facturas(None)
    r = ventas.resumen_facturas("admin")
    assert r["cantidad"] == 3 and r["top_productos"][0] == {
        "nombre": "Leche", "unidades": 6, "total": 600}
    assert ventas.resumen_facturas("admin", filtro_usuario_id=c1)["cantidad"] == 2
    assert ventas.resumen_facturas("admin", metodo_pago="efectivo")["cantidad"] == 1
    with pytest.raises(ErrorValidacion):
        ventas.resumen_facturas("admin", metodo_pago="cheque")


def test_rol_invalido_en_listado(ventas, escenario):
    with pytest.raises(RolNoPermitido):
        ventas.listar_facturas(1, None)


def test_evento_factura_creada_solo_admin_y_tras_commit(ventas, factory, bus, usuarios,
                                                       crear_producto):
    _, c1, _ = usuarios
    p = crear_producto("Pan", 10.0, 5)
    vistos = []

    def espia(ev):
        if ev["tipo"] == "factura_creada":
            with sesion(factory) as s:        # la factura ya debe ser visible (commit hecho)
                vistos.append(s.scalar(select(func.count()).select_from(FacturaORM)))
    bus.suscribir(espia)
    recibidos = []
    bus.suscribir(recibidos.append)
    f = ventas.comprar(c1, [linea(p.id, 2)], CLI, EFE)
    ev = [e for e in recibidos if e["tipo"] == "factura_creada"]
    assert len(ev) == 1 and ev[0]["para"] == "admin"
    assert ev[0]["payload"] == {"numero": f["numero"], "total": f["total"],
                                "metodo_pago": "efectivo"}
    assert vistos == [1]


def test_sin_evento_si_la_compra_falla(ventas, bus, usuarios, crear_producto, eventos):
    _, c1, _ = usuarios
    p = crear_producto("Pan", 10.0, 1)
    eventos.clear()
    with pytest.raises(Exception):
        ventas.comprar(c1, [linea(p.id, 5)], CLI, EFE)
    assert eventos == []


def test_las_facturas_son_inmutables_no_hay_api_de_escritura(ventas):
    for nombre in ("anular_factura", "editar_factura", "borrar_factura", "eliminar_factura",
                   "actualizar_factura"):
        assert not hasattr(ventas, nombre)
