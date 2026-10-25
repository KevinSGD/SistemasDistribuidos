"""Valores por defecto de la configuracion. No siembra usuarios (lo hace seguridad)."""
from __future__ import annotations

from datetime import datetime, time

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .orm import ConfiguracionORM, ProductoORM

CONFIG_POR_DEFECTO: dict[str, str] = {
    "moneda": "$",
    "dias_alerta_vencimiento": "7",
    "dias_critico_vencimiento": "3",
    "umbral_stock_bajo": "10",
    "descuento_critico": "50",
    "descuento_alto": "30",
    "descuento_sobrestock": "10",
    "intervalo_escaneo_segundos": "60",
    "nombre_negocio": "Mi Negocio",
    "nit": "",
    "direccion": "",
    "telefono": "",
    "iva_pct": "0",
    "decimales_moneda": "0",
    "inactividad_segundos": "180",
    "aviso_segundos": "30",
    "sesion_maxima_minutos": "480",
}


#: Claves retiradas del producto; se borran de BD ya sembradas al arrancar.
CLAVES_OBSOLETAS: tuple[str, ...] = ("descuento_medio",)


def sembrar_configuracion(sesion: Session) -> int:
    """Inserta solo las claves ausentes (no pisa valores editados) y borra las obsoletas
    (idempotente). Devuelve cuantas inserto."""
    sesion.execute(delete(ConfiguracionORM).where(ConfiguracionORM.clave.in_(CLAVES_OBSOLETAS)))
    existentes = set(sesion.scalars(select(ConfiguracionORM.clave)))
    nuevas = [ConfiguracionORM(clave=k, valor=v)
              for k, v in CONFIG_POR_DEFECTO.items() if k not in existentes]
    sesion.add_all(nuevas)
    sesion.flush()
    return len(nuevas)


def normalizar_vencimientos(sesion: Session, ahora: datetime | None = None) -> int:
    """Pasa a 23:59:59 los productos ACTIVOS con vencimiento a las 00:00:00 exactas cuya fecha
    es hoy o futura (una fecha sin hora vale hasta el final del dia). No toca fechas pasadas
    ni horas explicitas. Idempotente. Devuelve cuantos modifico."""
    ahora = ahora or datetime.now()
    hoy = ahora.date()
    n = 0
    q = select(ProductoORM).where(ProductoORM.activo.is_(True),
                                  ProductoORM.fecha_vencimiento.is_not(None))
    for p in sesion.scalars(q):
        f = p.fecha_vencimiento
        if f.time() == time(0, 0, 0) and f.date() >= hoy:
            p.fecha_vencimiento = datetime.combine(f.date(), time(23, 59, 59))
            n += 1
    sesion.flush()
    return n
