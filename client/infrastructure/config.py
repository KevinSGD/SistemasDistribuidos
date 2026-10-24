"""Configuracion del cliente: URL del servidor y timeouts.

Prioridad de la URL: variable INVENTARIO_URL > archivo de ajustes del usuario > por defecto.
El directorio de ajustes puede forzarse con INVENTARIO_CLIENT_DIR (tests)."""
from __future__ import annotations

import json
import os
from pathlib import Path
from urllib.parse import urlsplit

from platformdirs import user_config_dir

ENV_URL = "INVENTARIO_URL"
ENV_DIR = "INVENTARIO_CLIENT_DIR"
URL_POR_DEFECTO = "http://localhost:8000"
ARCHIVO = "cliente.json"

# Timeouts cortos (segundos): la GUI nunca espera, pero los workers tampoco deben colgarse.
TIMEOUT_CONEXION = float(os.environ.get("INVENTARIO_TIMEOUT_CONEXION", "3"))
TIMEOUT_LECTURA = float(os.environ.get("INVENTARIO_TIMEOUT_LECTURA", "8"))


def normalizar_url(url: str) -> str:
    """Devuelve `esquema://host[:puerto]` sin barra final ni ruta. Lanza ValueError si no es valida."""
    texto = (url or "").strip()
    if not texto:
        raise ValueError("La URL del servidor está vacía")
    if "://" not in texto:
        texto = "http://" + texto
    partes = urlsplit(texto)
    if partes.scheme not in ("http", "https") or not partes.hostname:
        raise ValueError("URL no válida (use http://host:puerto)")
    try:
        _ = partes.port
    except ValueError as exc:
        raise ValueError("Puerto no válido") from exc
    return f"{partes.scheme}://{partes.netloc}"


def _ruta_ajustes() -> Path:
    return Path(os.environ.get(ENV_DIR) or user_config_dir("InventarioApp")) / ARCHIVO


def url_fijada_por_entorno() -> bool:
    return bool(os.environ.get(ENV_URL))


def cargar_url() -> str:
    env = os.environ.get(ENV_URL)
    if env:
        try:
            return normalizar_url(env)
        except ValueError:
            pass
    try:
        datos = json.loads(_ruta_ajustes().read_text(encoding="utf-8"))
        return normalizar_url(str(datos.get("url", "")))
    except (OSError, ValueError, AttributeError):
        return URL_POR_DEFECTO


def guardar_url(url: str) -> str:
    """Persiste la URL (normalizada) en los ajustes del usuario y la devuelve."""
    limpia = normalizar_url(url)
    ruta = _ruta_ajustes()
    try:
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_text(json.dumps({"url": limpia}), encoding="utf-8")
    except OSError:
        pass      # no poder persistir no debe impedir iniciar sesion
    return limpia
