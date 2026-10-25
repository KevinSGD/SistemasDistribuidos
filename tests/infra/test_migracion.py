import hashlib
import shutil
import sqlite3
from datetime import datetime

import pytest
from sqlalchemy import func, select

from server.infrastructure.db.engine import sesion
from server.infrastructure.db.migrar_legacy import main, migrar
from server.infrastructure.db.orm import (
    ConfiguracionORM, DescuentoORM, DetalleFacturaORM, FacturaORM, ProductoORM, UsuarioORM,
)
from server.infrastructure.db.repos import FacturaRepo


# Esquema legacy (monolito v1.0) reproducido con SQL puro, tal como lo creaba SQLAlchemy.
_DDL_LEGACY = """
CREATE TABLE usuarios (
    id INTEGER NOT NULL, nombre VARCHAR(100) NOT NULL, usuario VARCHAR(50) NOT NULL,
    password VARCHAR(256) NOT NULL, rol VARCHAR(20), activo INTEGER,
    PRIMARY KEY (id), UNIQUE (usuario));
CREATE TABLE productos (
    id INTEGER NOT NULL, nombre VARCHAR(100) NOT NULL, categoria VARCHAR(50) NOT NULL,
    precio_base FLOAT NOT NULL, stock INTEGER NOT NULL, stock_maximo INTEGER NOT NULL,
    fecha_vencimiento DATETIME, fecha_ingreso DATETIME, nivel_riesgo VARCHAR(20),
    activo INTEGER, PRIMARY KEY (id));
CREATE TABLE ventas (
    id INTEGER NOT NULL, producto_id INTEGER NOT NULL, cantidad INTEGER NOT NULL,
    precio_unitario FLOAT NOT NULL, precio_final FLOAT NOT NULL, descuento_aplicado FLOAT,
    fecha DATETIME, PRIMARY KEY (id), FOREIGN KEY(producto_id) REFERENCES productos (id));
CREATE TABLE descuentos (
    id INTEGER NOT NULL, producto_id INTEGER NOT NULL, porcentaje FLOAT NOT NULL,
    motivo VARCHAR(200) NOT NULL, activo INTEGER, fecha_inicio DATETIME, fecha_fin DATETIME,
    PRIMARY KEY (id), FOREIGN KEY(producto_id) REFERENCES productos (id));
"""


def _sha(p: str) -> str:
    return hashlib.sha256(p.encode()).hexdigest()


def _ts(d: datetime) -> str:
    return d.strftime("%Y-%m-%d %H:%M:%S.%f")


@pytest.fixture
def legacy_db(tmp_path):
    """BD legacy generada con SQL puro (sin importar el monolito)."""
    original = tmp_path / "inventario.db"
    con = sqlite3.connect(original)
    con.executescript(_DDL_LEGACY)
    ing = _ts(datetime(2026, 3, 1))
    con.executemany(
        "INSERT INTO usuarios (nombre, usuario, password, rol, activo) VALUES (?,?,?,?,?)",
        [("Admin", "admin", _sha("admin123"), "admin", 1),
         ("Comp", "comprador", _sha("c123"), "usuario", 0)])
    con.executemany(
        "INSERT INTO productos (nombre, categoria, precio_base, stock, stock_maximo,"
        " fecha_vencimiento, fecha_ingreso, nivel_riesgo, activo) VALUES (?,?,?,?,?,?,?,?,?)",
        [("Leche", "lacteos", 10.0, 20, 50, _ts(datetime(2026, 5, 1)), ing, "normal", 1),
         ("Pan", "panaderia", 2.5, 5, 30, None, ing, "normal", 0)])
    con.execute(
        "INSERT INTO descuentos (producto_id, porcentaje, motivo, activo, fecha_inicio)"
        " VALUES (1, 30, 'vence pronto', 1, ?)", (ing,))
    t0 = datetime(2026, 4, 1, 10, 15, 5)
    t1 = datetime(2026, 4, 1, 10, 15, 40)  # mismo minuto
    t2 = datetime(2026, 4, 2, 9, 0, 0)
    con.executemany(
        "INSERT INTO ventas (producto_id, cantidad, precio_unitario, precio_final,"
        " descuento_aplicado, fecha) VALUES (?,?,?,?,?,?)",
        [(1, 2, 10.0, 14.0, 30, _ts(t0)),
         (2, 1, 2.5, 2.5, 0, _ts(t1)),
         (1, 1, 10.0, 10.0, 0, _ts(t2))])
    con.commit()
    con.close()
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
