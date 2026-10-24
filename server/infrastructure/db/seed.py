"""Valores por defecto de la configuracion. No siembra usuarios (lo hace seguridad)."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from .orm import ConfiguracionORM

CONFIG_POR_DEFECTO: dict[str, str] = {
    "moneda": "$",
    "dias_alerta_vencimiento": "7",
    "dias_critico_vencimiento": "3",
    "umbral_stock_bajo": "10",
    "descuento_critico": "50",
    "descuento_alto": "30",
    "descuento_medio": "15",
    "descuento_sobrestock": "10",
    "intervalo_escaneo_segundos": "60",
    "nombre_negocio": "Mi Negocio",
    "nit": "",
    "direccion": "",
    "telefono": "",
    "iva_pct": "0",
    "inactividad_segundos": "180",
    "aviso_segundos": "30",
    "sesion_maxima_minutos": "480",
}


def sembrar_configuracion(sesion: Session) -> int:
    """Inserta solo las claves ausentes (no pisa valores editados). Devuelve cuantas inserto."""
    existentes = set(sesion.scalars(select(ConfiguracionORM.clave)))
    nuevas = [ConfiguracionORM(clave=k, valor=v)
              for k, v in CONFIG_POR_DEFECTO.items() if k not in existentes]
    sesion.add_all(nuevas)
    sesion.flush()
    return len(nuevas)
