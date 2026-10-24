"""Migracion idempotente desde la BD SQLite legacy (models.py monolitico).

Uso:  python -m server.infrastructure.db.migrar_legacy RUTA_LEGACY [--destino RUTA]

Solo LEE la BD legacy (modo ro). Decisiones:
- productos / descuentos: se conservan con el MISMO id; si el id ya existe en destino, se omite.
- usuarios: se conservan por nombre de usuario; el hash SHA-256 legacy se guarda como
  "sha256$<hex>" para que seguridad lo re-hashee (argon2id) en el primer login exitoso.
- ventas: el legacy no tenia facturas. Se agrupan por minuto (fecha truncada) en facturas
  historicas 'FAC-LEG-YYYYMMDDHHMM' con usuario_id NULL, metodo_pago 'historico', iva 0.
  Cada venta pasa a una linea de detalle. precio_final legacy era el TOTAL de la linea;
  en detalle_factura se guarda unitario (total/cantidad) y subtotal = total legacy.
  Ventas con producto inexistente se omiten y se cuentan en el resumen.
- No usa el contador de FAC-nnnnnn, por lo que no interfiere con la numeracion nueva.
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from .engine import crear_engine, crear_esquema, crear_session_factory, sesion
from .orm import (
    DescuentoORM, DetalleFacturaORM, FacturaORM, ProductoORM, UsuarioORM,
)
from .seed import sembrar_configuracion

PREFIJO_SHA256 = "sha256$"


def _dt(v) -> datetime | None:
    if v is None or isinstance(v, datetime):
        return v
    s = str(v).replace("T", " ")
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def _filas(con: sqlite3.Connection, tabla: str) -> list[sqlite3.Row]:
    existe = con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (tabla,)
    ).fetchone()
    return list(con.execute(f"SELECT * FROM {tabla}")) if existe else []


def migrar(ruta_legacy: str | Path, s: Session) -> dict[str, int]:
    """Importa en la sesion dada (el llamador hace commit). Devuelve un resumen."""
    ruta = Path(ruta_legacy)
    if not ruta.exists():
        raise FileNotFoundError(f"BD legacy no encontrada: {ruta}")
    con = sqlite3.connect(f"file:{ruta.as_posix()}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    r = defaultdict(int)
    try:
        sembrar_configuracion(s)

        # Usuarios
        for u in _filas(con, "usuarios"):
            if s.scalars(select(UsuarioORM).where(UsuarioORM.usuario == u["usuario"])).first():
                r["usuarios_omitidos"] += 1
                continue
            h = u["password"] or ""
            if not h.startswith(PREFIJO_SHA256):
                h = PREFIJO_SHA256 + h
            rol = "admin" if u["rol"] == "admin" else "comprador"
            s.add(UsuarioORM(nombre=u["nombre"], usuario=u["usuario"], password_hash=h,
                             rol=rol, activo=bool(u["activo"] if u["activo"] is not None else 1)))
            r["usuarios"] += 1
        s.flush()

        # Productos (mismo id)
        for p in _filas(con, "productos"):
            if s.get(ProductoORM, p["id"]) is not None:
                r["productos_omitidos"] += 1
                continue
            s.add(ProductoORM(
                id=p["id"], nombre=p["nombre"], categoria=p["categoria"],
                precio_base=max(p["precio_base"], 0), stock=max(p["stock"] or 0, 0),
                stock_maximo=max(p["stock_maximo"] or 0, 0),
                fecha_vencimiento=_dt(p["fecha_vencimiento"]),
                fecha_ingreso=_dt(p["fecha_ingreso"]) or datetime.now(),
                activo=bool(p["activo"] if p["activo"] is not None else 1)))
            r["productos"] += 1
        s.flush()

        # Descuentos (mismo id)
        for d in _filas(con, "descuentos"):
            if s.get(DescuentoORM, d["id"]) is not None:
                r["descuentos_omitidos"] += 1
                continue
            if s.get(ProductoORM, d["producto_id"]) is None:
                r["descuentos_huerfanos"] += 1
                continue
            s.add(DescuentoORM(
                id=d["id"], producto_id=d["producto_id"],
                porcentaje=min(max(d["porcentaje"], 0), 100), motivo=d["motivo"],
                activo=bool(d["activo"] if d["activo"] is not None else 1),
                fecha_inicio=_dt(d["fecha_inicio"]) or datetime.now(),
                fecha_fin=_dt(d["fecha_fin"])))
            r["descuentos"] += 1
        s.flush()

        # Ventas -> facturas historicas agrupadas por minuto
        grupos: dict[str, list[sqlite3.Row]] = defaultdict(list)
        for v in _filas(con, "ventas"):
            f = _dt(v["fecha"]) or datetime(1970, 1, 1)
            grupos[f.strftime("%Y%m%d%H%M")].append(v)
        for clave, ventas in sorted(grupos.items()):
            numero = f"FAC-LEG-{clave}"
            if s.scalars(select(FacturaORM.id).where(FacturaORM.numero == numero)).first():
                r["facturas_omitidas"] += 1
                continue
            detalles, subtotal, total = [], 0.0, 0.0
            for v in ventas:
                prod = s.get(ProductoORM, v["producto_id"])
                if prod is None or v["cantidad"] <= 0:
                    r["ventas_omitidas"] += 1
                    continue
                cant = v["cantidad"]
                pct = min(max(v["descuento_aplicado"] or 0.0, 0), 100)
                tot = max(v["precio_final"], 0)
                detalles.append(DetalleFacturaORM(
                    producto_id=prod.id, nombre_producto=prod.nombre, cantidad=cant,
                    precio_unitario=v["precio_unitario"], descuento_pct=pct,
                    precio_final=tot / cant, subtotal=tot))
                subtotal += v["precio_unitario"] * cant
                total += tot
                r["ventas"] += 1
            if not detalles:
                continue
            s.add(FacturaORM(
                numero=numero, fecha=_dt(ventas[0]["fecha"]) or datetime.now(),
                metodo_pago="historico", subtotal=subtotal,
                ahorro=max(subtotal - total, 0), iva=0.0, total=total,
                usuario_id=None, detalles=detalles))
            r["facturas"] += 1
        s.flush()
    finally:
        con.close()
    return dict(r)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("legacy", help="ruta del inventario.db legacy")
    ap.add_argument("--destino", help="BD destino (por defecto INVENTARIO_DB / servidor.db)")
    a = ap.parse_args(argv)
    eng = crear_engine(a.destino)
    crear_esquema(eng)
    with sesion(crear_session_factory(eng)) as s:
        resumen = migrar(a.legacy, s)
    print("Migracion completada:", resumen)
    return 0


if __name__ == "__main__":
    sys.exit(main())
