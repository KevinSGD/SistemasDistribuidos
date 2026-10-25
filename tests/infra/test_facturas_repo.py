"""FacturaRepo: filtros combinados, offset, texto sin tildes y resumen en SQL."""
from datetime import datetime

import pytest

from server.domain.entities import ProductoDominio
from server.infrastructure.db.engine import sesion
from server.infrastructure.db.repos import (
    DetalleDTO, FacturaRepo, NuevaFactura, ProductoRepo, UsuarioRepo,
)

D = datetime


@pytest.fixture
def datos(factory):
    """6 facturas: 2 usuarios, 2 metodos, 3 dias."""
    with sesion(factory) as s:
        u = UsuarioRepo(s)
        ana = u.crear("Ana Cuenta", "ana", "x", "comprador").id
        beto = u.crear("Beto Cuenta", "beto", "x", "comprador").id
        pr = ProductoRepo(s)
        leche = pr.crear(ProductoDominio(None, "Leche", "L", 100.0, 99, 999, None, True)).id
        pan = pr.crear(ProductoDominio(None, "Pan", "P", 50.0, 99, 999, None, True)).id
        repo = FacturaRepo(s)

        def f(fecha, cli, doc, metodo, uid, lineas, ahorro=0.0):
            det = tuple(DetalleDTO(pid, n, c, pu, 0.0, pu, pu * c) for pid, n, c, pu in lineas)
            sub = sum(d.subtotal for d in det)
            iva = round(sub * 0.19)
            repo.crear(NuevaFactura(
                metodo_pago=metodo, subtotal=sub + ahorro, ahorro=ahorro, iva=iva,
                total=sub + iva, usuario_id=uid, detalles=det, cliente_nombre=cli,
                cliente_documento=doc, fecha=fecha))

        L = (leche, "Leche", 2, 100.0)
        P = (pan, "Pan", 3, 50.0)
        f(D(2026, 6, 1, 9), "José Pérez", "111", "efectivo", ana, [L])
        f(D(2026, 6, 1, 15), "Maria Lopez", "222", "tarjeta_simulada", beto, [L, P], 20.0)
        f(D(2026, 6, 2, 10), "JOSE PEREZ", "333", "tarjeta_simulada", ana, [P])
        f(D(2026, 6, 2, 11), "", "", "efectivo", beto, [P, L])
        f(D(2026, 6, 3, 8), "Ñandú 100%", "444_5", "efectivo", ana, [L])
        f(D(2026, 6, 3, 9), "Luis", "555", "tarjeta_simulada", beto, [P])
    return {"ana": ana, "beto": beto}


def listar(factory, **kw):
    with sesion(factory) as s:
        return FacturaRepo(s).listar(**kw)


def resumen(factory, **kw):
    with sesion(factory) as s:
        return FacturaRepo(s).resumen(**kw)


def test_orden_mas_recientes_primero_y_nombre_de_cuenta(factory, datos):
    fs = listar(factory)
    assert [f.numero for f in fs] == [f"FAC-{n:06d}" for n in range(6, 0, -1)]
    assert fs[0].usuario_nombre == "Beto Cuenta" and fs[-1].usuario_nombre == "Ana Cuenta"
    assert fs[0].detalles and fs[0].cliente_nombre == "Luis"


def test_offset_y_limite_paginan_sin_solaparse(factory, datos):
    todas = [f.numero for f in listar(factory)]
    p1 = [f.numero for f in listar(factory, limite=4)]
    p2 = [f.numero for f in listar(factory, limite=4, offset=4)]
    assert p1 + p2 == todas and len(p2) == 2
    assert listar(factory, limite=3, offset=99) == []


def test_filtros_combinados(factory, datos):
    fs = listar(factory, desde=D(2026, 6, 2), hasta=D(2026, 6, 2, 23, 59, 59),
                metodo_pago="efectivo", usuario_id=datos["beto"])
    assert [f.numero for f in fs] == ["FAC-000004"]
    assert listar(factory, usuario_id=datos["ana"], metodo_pago="tarjeta_simulada")[0].numero \
        == "FAC-000003"
    assert listar(factory, desde=D(2026, 6, 4)) == []


@pytest.mark.parametrize("texto,esperados", [
    ("jose", {1, 3}),            # sin tildes ni mayusculas
    ("PÉREZ", {1, 3}),
    ("FAC-000002", {2}),
    ("000004", {4}),
    ("333", {3}),
    ("100%", {5}),               # % literal, no comodin
    ("4_5", {5}),                # _ literal, no comodin
    ("nandu", {5}),              # Ñ -> n
    ("%", {5}),
    ("zzz", set()),
    ("   ", {1, 2, 3, 4, 5, 6}),
])
def test_busqueda_de_texto(factory, datos, texto, esperados):
    fs = listar(factory, q=texto)
    assert {int(f.numero[4:]) for f in fs} == esperados


def test_el_texto_no_busca_en_la_cuenta_del_usuario(factory, datos):
    assert listar(factory, q="Ana Cuenta") == []


def test_resumen_coincide_con_la_lista_filtrada(factory, datos):
    casos = [{}, {"metodo_pago": "efectivo"}, {"usuario_id": datos["ana"]}, {"q": "jose"},
             {"desde": D(2026, 6, 2), "hasta": D(2026, 6, 2, 23, 59)},
             {"q": "luis", "metodo_pago": "efectivo"}]
    for kw in casos:
        fs = listar(factory, **kw)
        r = resumen(factory, **kw)
        assert r["cantidad"] == len(fs), kw
        assert r["subtotal"] == round(sum(f.subtotal for f in fs)), kw
        assert r["ahorro"] == round(sum(f.ahorro for f in fs)), kw
        assert r["iva"] == round(sum(f.iva for f in fs)), kw
        assert r["total"] == round(sum(f.total for f in fs)), kw
        assert r["ticket_promedio"] == (round(r["total"] / len(fs)) if fs else 0), kw
        assert sum(m["cantidad"] for m in r["por_metodo"]) == len(fs), kw
        assert sum(m["total"] for m in r["por_metodo"]) == r["total"], kw
        if fs:
            assert r["desde"] == min(f.fecha for f in fs)
            assert r["hasta"] == max(f.fecha for f in fs)


def test_resumen_top_productos_por_unidades(factory, datos):
    r = resumen(factory)
    # Leche: 2+2+2+2 = 8 uds (f1,f2,f4,f5) ; Pan: 3+3+3+3 = 12 (f2,f3,f4,f6)
    assert r["top_productos"] == [
        {"nombre": "Pan", "unidades": 12, "total": 600},
        {"nombre": "Leche", "unidades": 8, "total": 800}]
    assert [m["metodo"] for m in r["por_metodo"]] == sorted(
        [m["metodo"] for m in r["por_metodo"]],
        key=lambda x: -next(y["total"] for y in r["por_metodo"] if y["metodo"] == x))


def test_resumen_vacio(factory, datos):
    r = resumen(factory, q="nadie")
    assert r["cantidad"] == 0 and r["total"] == 0 and r["ticket_promedio"] == 0
    assert r["por_metodo"] == [] and r["top_productos"] == []
    assert r["desde"] is None and r["hasta"] is None
    assert all(isinstance(r[k], int) for k in ("subtotal", "ahorro", "iva", "total"))


def test_top_limitado_a_cinco(factory):
    with sesion(factory) as s:
        uid = UsuarioRepo(s).crear("U", "u", "x").id
        pr = ProductoRepo(s)
        det = []
        for i in range(7):
            p = pr.crear(ProductoDominio(None, f"P{i}", "c", 10.0, 9, 99, None, True))
            det.append(DetalleDTO(p.id, f"P{i}", i + 1, 10.0, 0.0, 10.0, 10.0 * (i + 1)))
        FacturaRepo(s).crear(NuevaFactura("efectivo", 280.0, 0.0, 0.0, 280.0, uid, tuple(det)))
    top = resumen(factory)["top_productos"]
    assert [t["nombre"] for t in top] == ["P6", "P5", "P4", "P3", "P2"]


def test_obtener_por_numero_trae_cuenta(factory, datos):
    with sesion(factory) as s:
        f = FacturaRepo(s).obtener_por_numero("FAC-000002")
    assert f.usuario_nombre == "Beto Cuenta" and len(f.detalles) == 2
