import threading
from datetime import timedelta

import pytest
from sqlalchemy import func, select

from server.application.errores import ErrorValidacion, RolNoPermitido
from server.domain.errors import (
    EfectivoInsuficiente, NoEncontrado, ProductoInactivo, ProductoVencido, StockInsuficiente,
)
from server.infrastructure.db.engine import sesion
from server.infrastructure.db.orm import DetalleFacturaORM, FacturaORM, ProductoORM
from server.infrastructure.db.repos import ProductoRepo

from .conftest import AHORA

CLI = {"nombre": "Ana", "documento": "123"}
TARJ = {"metodo": "tarjeta_simulada"}


def stock(factory, pid):
    with sesion(factory) as s:
        return s.scalar(select(ProductoORM.stock).where(ProductoORM.id == pid))


def n_facturas(factory):
    with sesion(factory) as s:
        return (s.scalar(select(func.count()).select_from(FacturaORM)),
                s.scalar(select(func.count()).select_from(DetalleFacturaORM)))


def linea(pid, cant):
    return {"producto_id": pid, "cantidad": cant}


def test_compra_exitosa_valores_y_eventos(ventas, factory, usuarios, crear_producto, config,
                                          eventos):
    _, c1, _ = usuarios
    p = crear_producto(precio=10.0, stock=20, venc=AHORA + timedelta(days=2))  # critico: 50%
    q = crear_producto("Pan", 4.0, 10)
    config.actualizar({"iva_pct": 19}, "admin")
    eventos.clear()
    f = ventas.comprar(c1, [linea(p.id, 2), linea(q.id, 1)], CLI,
                       {"metodo": "efectivo", "efectivo_recibido": 50})
    assert f["numero"] == "FAC-000001"
    # 2*5.00 + 1*4.00 = 14.00 ; iva 19% = 2.66 ; total 16.66
    assert f["subtotal"] == 24.0 and f["ahorro"] == 10.0
    assert f["iva"] == 2.66 and f["total"] == 16.66
    assert f["efectivo_recibido"] == 50 and f["cambio"] == 33.34
    it = f["items"][0]
    assert (it["precio_original"], it["descuento_pct"], it["precio_final"], it["subtotal"]) \
        == (10.0, 50.0, 5.0, 10.0)
    assert f["cliente"] == CLI and f["negocio"]["nombre_negocio"] == "Mi Negocio"
    assert stock(factory, p.id) == 18 and stock(factory, q.id) == 9
    ev = {(e["tipo"], e["payload"]["producto_id"]): e["payload"]["stock"] for e in eventos}
    assert ev == {("stock_actualizado", p.id): 18, ("stock_actualizado", q.id): 9}
    assert ventas.comprar(c1, [linea(q.id, 1)], CLI, TARJ)["numero"] == "FAC-000002"


def test_tarjeta_sin_efectivo_cambio_cero(ventas, usuarios, crear_producto):
    p = crear_producto(precio=3.0)
    f = ventas.comprar(usuarios[1], [linea(p.id, 1)], CLI, TARJ)
    assert f["efectivo_recibido"] is None and f["cambio"] == 0.0 and f["total"] == 3.0


def test_stock_insuficiente_rollback_total(ventas, factory, usuarios, crear_producto, eventos):
    a = crear_producto("A", 5.0, 10)
    b = crear_producto("B", 5.0, 1)
    eventos.clear()
    with pytest.raises(StockInsuficiente):
        ventas.comprar(usuarios[1], [linea(a.id, 3), linea(b.id, 2)], CLI, TARJ)
    assert stock(factory, a.id) == 10 and stock(factory, b.id) == 1
    assert n_facturas(factory) == (0, 0)
    assert eventos == []


def test_rollback_si_falla_descuento_atomico_a_mitad(ventas, factory, usuarios, crear_producto,
                                                     monkeypatch):
    """Fuerza el fallo en la 2da linea (carrera simulada): la 1ra debe revertirse."""
    a, b = crear_producto("A", 5.0, 10), crear_producto("B", 5.0, 10)
    real = ProductoRepo.descontar_stock_atomico

    def falso(self, id, cantidad):
        return False if id == b.id else real(self, id, cantidad)
    monkeypatch.setattr(ProductoRepo, "descontar_stock_atomico", falso)
    with pytest.raises(StockInsuficiente):
        ventas.comprar(usuarios[1], [linea(a.id, 4), linea(b.id, 1)], CLI, TARJ)
    assert stock(factory, a.id) == 10 and n_facturas(factory) == (0, 0)


def test_rollback_si_falla_la_factura(ventas, factory, usuarios, crear_producto, monkeypatch):
    from server.infrastructure.db.repos import FacturaRepo
    p = crear_producto(stock=10)

    def boom(self, nf):
        raise RuntimeError("disco lleno")
    monkeypatch.setattr(FacturaRepo, "crear", boom)
    with pytest.raises(RuntimeError):
        ventas.comprar(usuarios[1], [linea(p.id, 4)], CLI, TARJ)
    assert stock(factory, p.id) == 10


def test_vencido_inactivo_y_no_existente(ventas, usuarios, crear_producto):
    v = crear_producto("V", venc=AHORA - timedelta(hours=1))
    i = crear_producto("I", activo=False)
    with pytest.raises(ProductoVencido):
        ventas.comprar(usuarios[1], [linea(v.id, 1)], CLI, TARJ)
    with pytest.raises(ProductoInactivo):
        ventas.comprar(usuarios[1], [linea(i.id, 1)], CLI, TARJ)
    with pytest.raises(NoEncontrado):
        ventas.comprar(usuarios[1], [linea(999, 1)], CLI, TARJ)


def test_items_duplicados_se_consolidan(ventas, factory, usuarios, crear_producto):
    p = crear_producto(precio=2.0, stock=5)
    f = ventas.comprar(usuarios[1], [linea(p.id, 2), linea(p.id, 3)], CLI, TARJ)
    assert len(f["items"]) == 1 and f["items"][0]["cantidad"] == 5 and f["total"] == 10.0
    assert stock(factory, p.id) == 0
    q = crear_producto("Q", stock=4)
    with pytest.raises(StockInsuficiente):
        ventas.comprar(usuarios[1], [linea(q.id, 3), linea(q.id, 3)], CLI, TARJ)
    assert stock(factory, q.id) == 4


@pytest.mark.parametrize("items,pago", [
    ([], TARJ),
    ([linea(1, 0)], TARJ),
    ([linea(1, True)], TARJ),
    ([linea(1, 1)], {"metodo": "bitcoin"}),
    ([linea(1, 1)], {"metodo": "efectivo"}),
    ([{"cantidad": 1}], {"metodo": "efectivo", "efectivo_recibido": 5}),
])
def test_validaciones_de_entrada(ventas, usuarios, crear_producto, items, pago):
    crear_producto()
    with pytest.raises(ErrorValidacion):
        ventas.comprar(usuarios[1], items, CLI, pago)


def test_efectivo_insuficiente_no_toca_stock(ventas, factory, usuarios, crear_producto):
    p = crear_producto(precio=10.0, stock=5)
    with pytest.raises(EfectivoInsuficiente):
        ventas.comprar(usuarios[1], [linea(p.id, 2)], CLI,
                       {"metodo": "efectivo", "efectivo_recibido": 19.99})
    assert stock(factory, p.id) == 5 and n_facturas(factory) == (0, 0)


def test_dos_hilos_compran_el_ultimo_item(ventas, factory, usuarios, crear_producto):
    p = crear_producto(precio=7.0, stock=1)
    barrera = threading.Barrier(2)
    res = []

    def comprar(uid):
        barrera.wait()
        try:
            res.append(ventas.comprar(uid, [linea(p.id, 1)], CLI, TARJ))
        except StockInsuficiente as e:
            res.append(e)
    ts = [threading.Thread(target=comprar, args=(u,)) for u in usuarios[1:]]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert sum(isinstance(r, dict) for r in res) == 1
    assert sum(isinstance(r, StockInsuficiente) for r in res) == 1
    assert stock(factory, p.id) == 0 and n_facturas(factory) == (1, 1)


def test_muchos_hilos_nunca_sobrevenden(ventas, factory, usuarios, crear_producto):
    p = crear_producto(precio=1.0, stock=5)
    barrera = threading.Barrier(12)
    ok = []

    def comprar():
        barrera.wait()
        try:
            ventas.comprar(usuarios[1], [linea(p.id, 1)], CLI, TARJ)
            ok.append(1)
        except StockInsuficiente:
            pass
    ts = [threading.Thread(target=comprar) for _ in range(12)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert len(ok) == 5 and stock(factory, p.id) == 0 and n_facturas(factory)[0] == 5


def test_comprador_no_ve_facturas_ajenas(ventas, usuarios, crear_producto):
    adm, c1, c2 = usuarios
    p = crear_producto(stock=10)
    f1 = ventas.comprar(c1, [linea(p.id, 1)], CLI, TARJ)
    f2 = ventas.comprar(c2, [linea(p.id, 1)], CLI, TARJ)
    assert ventas.obtener_factura(f1["numero"], c1, "comprador")["numero"] == f1["numero"]
    with pytest.raises(NoEncontrado):
        ventas.obtener_factura(f2["numero"], c1, "comprador")
    assert ventas.obtener_factura(f2["numero"], adm, "admin")
    assert [f["numero"] for f in ventas.listar_facturas(c1, "comprador")] == [f1["numero"]]
    assert len(ventas.listar_facturas(adm, "admin")) == 2
    with pytest.raises(RolNoPermitido):
        ventas.listar_facturas(c1, None)
