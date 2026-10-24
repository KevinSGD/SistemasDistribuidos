import threading
from datetime import datetime, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from server.domain.entities import ProductoDominio
from server.infrastructure.db import engine as eng_mod
from server.infrastructure.db.engine import sesion
from server.infrastructure.db.orm import (
    DescuentoORM, DetalleFacturaORM, FacturaORM, ProductoORM,
)
from server.infrastructure.db.repos import (
    ConfigRepo, DescuentoRepo, DetalleDTO, FacturaRepo, NuevaFactura, ProductoRepo,
    SesionRepo, UsuarioRepo,
)
from server.infrastructure.db.seed import CONFIG_POR_DEFECTO, sembrar_configuracion


def prod(nombre="Leche", precio=10.0, stock=5, maximo=100, venc=None, activo=True):
    return ProductoDominio(None, nombre, "lacteos", precio, stock, maximo, venc, activo)


def nueva_factura(pid, usuario_id=None, cant=1):
    d = DetalleDTO(pid, "Leche", cant, 10.0, 0.0, 10.0, 10.0 * cant)
    return NuevaFactura("efectivo", 10.0 * cant, 0.0, 0.0, 10.0 * cant, usuario_id, (d,))


# ── Pragmas / engine ───────────────────────────────────────────────────────
def test_pragmas_activos(engine):
    with engine.connect() as c:
        assert c.execute(text("PRAGMA foreign_keys")).scalar() == 1
        assert c.execute(text("PRAGMA journal_mode")).scalar().lower() == "wal"


def test_ruta_por_variable_de_entorno(monkeypatch, tmp_path):
    monkeypatch.setenv("INVENTARIO_DB", str(tmp_path / "x" / "env.db"))
    assert eng_mod.ruta_db_por_defecto() == tmp_path / "x" / "env.db"


# ── FK y CHECK ─────────────────────────────────────────────────────────────
def test_fk_detalle_con_producto_inexistente_falla(s):
    f = FacturaORM(numero="FAC-000001", metodo_pago="efectivo", subtotal=1, total=1)
    f.detalles.append(DetalleFacturaORM(producto_id=999, nombre_producto="x", cantidad=1,
                                        precio_unitario=1, precio_final=1, subtotal=1))
    s.add(f)
    with pytest.raises(IntegrityError):
        s.flush()


@pytest.mark.parametrize("campo,valor", [
    ("precio_base", -1.0), ("stock", -1), ("stock_maximo", -1),
])
def test_check_producto(s, campo, valor):
    kw = dict(nombre="p", categoria="c", precio_base=1.0, stock=1, stock_maximo=1)
    kw[campo] = valor
    s.add(ProductoORM(**kw))
    with pytest.raises(IntegrityError):
        s.flush()


@pytest.mark.parametrize("pct", [-0.1, 100.1])
def test_check_descuento_porcentaje(s, pct):
    p = ProductoRepo(s).crear(prod())
    s.add(DescuentoORM(producto_id=p.id, porcentaje=pct, motivo="m"))
    with pytest.raises(IntegrityError):
        s.flush()


@pytest.mark.parametrize("cant", [0, -2])
def test_check_detalle_cantidad(s, cant):
    p = ProductoRepo(s).crear(prod())
    f = FacturaORM(numero="FAC-000001", metodo_pago="efectivo", subtotal=1, total=1)
    f.detalles.append(DetalleFacturaORM(producto_id=p.id, nombre_producto="x", cantidad=cant,
                                        precio_unitario=1, precio_final=1, subtotal=1))
    s.add(f)
    with pytest.raises(IntegrityError):
        s.flush()


def test_check_detalle_descuento_pct(s):
    p = ProductoRepo(s).crear(prod())
    f = FacturaORM(numero="FAC-000001", metodo_pago="efectivo", subtotal=1, total=1)
    f.detalles.append(DetalleFacturaORM(producto_id=p.id, nombre_producto="x", cantidad=1,
                                        descuento_pct=101, precio_unitario=1,
                                        precio_final=1, subtotal=1))
    s.add(f)
    with pytest.raises(IntegrityError):
        s.flush()


def test_numero_factura_unico(s):
    s.add(FacturaORM(numero="A", metodo_pago="e", subtotal=0, total=0))
    s.add(FacturaORM(numero="A", metodo_pago="e", subtotal=0, total=0))
    with pytest.raises(IntegrityError):
        s.flush()


# ── Productos ──────────────────────────────────────────────────────────────
def test_crud_productos_devuelve_dominio(s):
    r = ProductoRepo(s)
    p = r.crear(prod("A"))
    assert isinstance(p, ProductoDominio) and p.id is not None
    assert r.obtener(p.id) == p
    r.actualizar(ProductoDominio(p.id, "B", "c", 2.0, 3, 4, None, True))
    assert r.obtener(p.id).nombre == "B"
    assert r.baja_logica(p.id) is True
    assert r.listar_activos() == []
    assert r.obtener(p.id).activo is False
    assert r.obtener(12345) is None


def test_descontar_stock_atomico(s):
    r = ProductoRepo(s)
    p = r.crear(prod(stock=5))
    assert r.descontar_stock_atomico(p.id, 3) is True
    assert r.obtener(p.id).stock == 2
    assert r.descontar_stock_atomico(p.id, 3) is False
    assert r.obtener(p.id).stock == 2
    assert r.descontar_stock_atomico(p.id, 2) is True
    assert r.obtener(p.id).stock == 0
    assert r.descontar_stock_atomico(p.id, 1) is False
    assert r.descontar_stock_atomico(p.id, 0) is False
    assert r.descontar_stock_atomico(999, 1) is False


def test_descontar_stock_concurrente_no_sobrevende(factory):
    with sesion(factory) as s:
        pid = ProductoRepo(s).crear(prod(stock=10)).id
    ok = []

    def comprar():
        with sesion(factory) as s2:
            ok.append(ProductoRepo(s2).descontar_stock_atomico(pid, 1))

    hilos = [threading.Thread(target=comprar) for _ in range(25)]
    [h.start() for h in hilos]
    [h.join() for h in hilos]
    assert sum(ok) == 10
    with sesion(factory) as s:
        assert ProductoRepo(s).obtener(pid).stock == 0


def test_retirar_vencidos(s):
    r = ProductoRepo(s)
    ahora = datetime(2026, 1, 10)
    viejo = r.crear(prod("viejo", venc=ahora - timedelta(days=1)))
    r.crear(prod("fresco", venc=ahora + timedelta(days=1)))
    r.crear(prod("sin fecha"))
    retirados = r.retirar_vencidos(ahora)
    assert [p.id for p in retirados] == [viejo.id]
    assert {p.nombre for p in r.listar_activos()} == {"fresco", "sin fecha"}


# ── Descuentos ─────────────────────────────────────────────────────────────
def test_reemplazar_descuento_activo(s):
    p = ProductoRepo(s).crear(prod())
    d = DescuentoRepo(s)
    d.reemplazar_activo(p.id, 10, "a")
    d2 = d.reemplazar_activo(p.id, 30, "b")
    assert d.activo_de(p.id) == d2
    assert len(d.listar_activos()) == 1


# ── Facturas ───────────────────────────────────────────────────────────────
def test_numero_consecutivo(s):
    p = ProductoRepo(s).crear(prod())
    fr = FacturaRepo(s)
    nums = [fr.crear(nueva_factura(p.id)).numero for _ in range(3)]
    assert nums == ["FAC-000001", "FAC-000002", "FAC-000003"]


def test_factura_roundtrip_y_filtros(s):
    p = ProductoRepo(s).crear(prod())
    u = UsuarioRepo(s).crear("U", "u1", "h")
    fr = FacturaRepo(s)
    base = datetime(2026, 3, 1, 12)
    for i in range(3):
        nf = nueva_factura(p.id, u.id if i < 2 else None, cant=i + 1)
        fr.crear(NuevaFactura(**{**nf.__dict__, "fecha": base + timedelta(days=i)}))
    f = fr.obtener_por_numero("FAC-000002")
    assert f.detalles[0].cantidad == 2 and f.usuario_id == u.id
    assert fr.obtener_por_numero("nope") is None
    assert len(fr.listar()) == 3
    assert [x.numero for x in fr.listar()][0] == "FAC-000003"
    assert len(fr.listar(usuario_id=u.id)) == 2
    assert len(fr.listar(desde=base + timedelta(days=1), hasta=base + timedelta(days=1, hours=1))) == 1


def test_numero_no_se_consume_con_rollback(factory):
    with sesion(factory) as s:
        p = ProductoRepo(s).crear(prod())
        FacturaRepo(s).crear(nueva_factura(p.id))
    with pytest.raises(RuntimeError):
        with sesion(factory) as s:
            FacturaRepo(s).crear(nueva_factura(p.id))
            raise RuntimeError
    with sesion(factory) as s:
        assert FacturaRepo(s).crear(nueva_factura(p.id)).numero == "FAC-000002"


# ── Sesion (context manager) ───────────────────────────────────────────────
def test_sesion_commit_y_rollback(factory):
    with sesion(factory) as s:
        ProductoRepo(s).crear(prod("ok"))
    with pytest.raises(ValueError):
        with sesion(factory) as s:
            ProductoRepo(s).crear(prod("fantasma"))
            raise ValueError
    with sesion(factory) as s:
        assert [p.nombre for p in ProductoRepo(s).listar_activos()] == ["ok"]


def test_sesion_cierra_siempre(factory):
    with sesion(factory) as s:
        pass
    assert not s.in_transaction()


def test_get_db_generador(engine):
    eng_mod.configurar(engine)
    gen = eng_mod.get_db()
    s = next(gen)
    ProductoRepo(s).crear(prod("via_dep"))
    with pytest.raises(StopIteration):
        next(gen)
    with sesion() as s2:
        assert ProductoRepo(s2).listar_activos()[0].nombre == "via_dep"


# ── Usuarios, sesiones, config ─────────────────────────────────────────────
def test_usuarios_y_sesiones(s):
    ur = UsuarioRepo(s)
    u = ur.crear("Ana", "ana", "$argon2id$x" + "a" * 200, "admin")
    assert ur.obtener_por_usuario("ana") == u and u.activo is True
    assert ur.actualizar(u.id, activo=False).activo is False
    sr = SesionRepo(s)
    se = sr.crear("jti1", u.id)
    assert not se.cerrada and sr.tocar("jti1", datetime(2030, 1, 1))
    assert sr.obtener_por_jti("jti1").ultima_actividad == datetime(2030, 1, 1)
    assert sr.cerrar("jti1", "logout") is True
    assert sr.cerrar("jti1", "otra") is False
    assert sr.tocar("jti1") is False
    assert sr.obtener_por_jti("jti1").motivo_cierre == "logout"
    sr.crear("jti2", u.id)
    assert sr.cerrar_todas_de_usuario(u.id, "admin") == 1
    with pytest.raises(IntegrityError):
        sr.crear("jti2", u.id)
        s.flush()


def test_config_defaults_y_seed(s):
    esperadas = {
        "moneda", "dias_alerta_vencimiento", "dias_critico_vencimiento", "umbral_stock_bajo",
        "descuento_critico", "descuento_alto", "descuento_medio", "descuento_sobrestock",
        "intervalo_escaneo_segundos", "nombre_negocio", "nit", "direccion", "telefono",
        "iva_pct", "inactividad_segundos", "aviso_segundos", "sesion_maxima_minutos",
        "decimales_moneda",
    }
    assert set(CONFIG_POR_DEFECTO) == esperadas
    c = ConfigRepo(s)
    assert c.get("umbral_stock_bajo") == "10"  # default sin sembrar
    n = sembrar_configuracion(s)
    assert n == len(esperadas)
    c.set("umbral_stock_bajo", 20)
    assert sembrar_configuracion(s) == 0  # idempotente, no pisa
    assert c.get("umbral_stock_bajo") == "20"
    assert c.todos()["iva_pct"] == "0"
    assert c.get("inexistente", "z") == "z"
