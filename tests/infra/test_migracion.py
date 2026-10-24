import shutil
import sqlite3
from datetime import datetime

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from server.infrastructure.db.engine import sesion
from server.infrastructure.db.migrar_legacy import main, migrar
from server.infrastructure.db.orm import (
    ConfiguracionORM, DescuentoORM, DetalleFacturaORM, FacturaORM, ProductoORM, UsuarioORM,
)
from server.infrastructure.db.repos import FacturaRepo


@pytest.fixture
def legacy_db(tmp_path):
    """BD legacy generada con el models.py monolitico actual."""
    import models  # noqa: F401  (registra tablas en database.Base)
    from database import Base

    original = tmp_path / "inventario.db"
    eng = create_engine(f"sqlite:///{original}")
    Base.metadata.create_all(eng)
    with Session(eng) as s:
        s.add(models.Usuario(nombre="Admin", usuario="admin", rol="admin",
                             password=models.Usuario.hashear_password("admin123")))
        s.add(models.Usuario(nombre="Comp", usuario="comprador", rol="usuario",
                             password=models.Usuario.hashear_password("c123"), activo=0))
        a = models.Producto(nombre="Leche", categoria="lacteos", precio_base=10.0, stock=20,
                            stock_maximo=50, fecha_vencimiento=datetime(2026, 5, 1))
        b = models.Producto(nombre="Pan", categoria="panaderia", precio_base=2.5, stock=5,
                            stock_maximo=30, activo=0)
        s.add_all([a, b])
        s.flush()
        s.add(models.Descuento(producto_id=a.id, porcentaje=30, motivo="vence pronto"))
        t0 = datetime(2026, 4, 1, 10, 15, 5)
        t1 = datetime(2026, 4, 1, 10, 15, 40)  # mismo minuto
        t2 = datetime(2026, 4, 2, 9, 0, 0)
        s.add_all([
            models.Venta(producto_id=a.id, cantidad=2, precio_unitario=10.0, precio_final=14.0,
                         descuento_aplicado=30, fecha=t0),
            models.Venta(producto_id=b.id, cantidad=1, precio_unitario=2.5, precio_final=2.5,
                         descuento_aplicado=0, fecha=t1),
            models.Venta(producto_id=a.id, cantidad=1, precio_unitario=10.0, precio_final=10.0,
                         descuento_aplicado=0, fecha=t2),
        ])
        s.commit()
    eng.dispose()
    copia = tmp_path / "copia.db"  # se migra siempre sobre una copia
    shutil.copy(original, copia)
    return copia


def contar(s, modelo):
    return s.scalar(select(func.count()).select_from(modelo))


def test_migracion_completa_e_idempotente(s, legacy_db):
    r1 = migrar(legacy_db, s)
    s.commit()
    assert r1["productos"] == 2 and r1["usuarios"] == 2 and r1["descuentos"] == 1
    assert r1["facturas"] == 2 and r1["ventas"] == 3

    conteos = [contar(s, m) for m in
               (ProductoORM, UsuarioORM, DescuentoORM, FacturaORM, DetalleFacturaORM,
                ConfiguracionORM)]
    r2 = migrar(legacy_db, s)
    s.commit()
    assert [contar(s, m) for m in
            (ProductoORM, UsuarioORM, DescuentoORM, FacturaORM, DetalleFacturaORM,
             ConfiguracionORM)] == conteos
    assert r2.get("productos", 0) == 0 and r2.get("facturas", 0) == 0
    assert r2["facturas_omitidas"] == 2


def test_migracion_conserva_datos(s, legacy_db):
    migrar(legacy_db, s)
    s.commit()
    admin = s.scalars(select(UsuarioORM).where(UsuarioORM.usuario == "admin")).one()
    import hashlib
    assert admin.password_hash == "sha256$" + hashlib.sha256(b"admin123").hexdigest()
    assert admin.rol == "admin" and admin.activo is True
    comp = s.scalars(select(UsuarioORM).where(UsuarioORM.usuario == "comprador")).one()
    assert comp.rol == "comprador" and comp.activo is False

    leche = s.get(ProductoORM, 1)
    assert (leche.nombre, leche.stock, leche.fecha_vencimiento) == ("Leche", 20, datetime(2026, 5, 1))
    assert s.get(ProductoORM, 2).activo is False

    f = FacturaRepo(s).obtener_por_numero("FAC-LEG-202604011015")
    assert len(f.detalles) == 2 and f.usuario_id is None
    assert f.total == pytest.approx(16.5) and f.subtotal == pytest.approx(22.5)
    assert f.ahorro == pytest.approx(6.0)
    d = f.detalles[0]
    assert d.precio_final == pytest.approx(7.0) and d.subtotal == pytest.approx(14.0)
    assert d.nombre_producto == "Leche" and d.descuento_pct == 30


def test_numeracion_nueva_no_choca_con_historicas(s, legacy_db):
    migrar(legacy_db, s)
    s.commit()
    from server.infrastructure.db.repos import DetalleDTO, NuevaFactura
    d = DetalleDTO(1, "Leche", 1, 10, 0, 10, 10)
    assert FacturaRepo(s).crear(NuevaFactura("efectivo", 10, 0, 0, 10, None, (d,))).numero == "FAC-000001"


def test_legacy_no_se_modifica_y_cli(tmp_path, legacy_db):
    antes = legacy_db.read_bytes()
    destino = tmp_path / "nuevo.db"
    assert main([str(legacy_db), "--destino", str(destino)]) == 0
    assert main([str(legacy_db), "--destino", str(destino)]) == 0
    assert legacy_db.read_bytes() == antes
    con = sqlite3.connect(destino)
    assert con.execute("select count(*) from productos").fetchone()[0] == 2
    assert con.execute("select count(*) from facturas").fetchone()[0] == 2
    con.close()


def test_legacy_inexistente(s, tmp_path):
    with pytest.raises(FileNotFoundError):
        migrar(tmp_path / "no.db", s)
