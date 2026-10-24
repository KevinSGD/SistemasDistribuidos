"""Arranque del servidor: `python -m server.main`.

Variables: INVENTARIO_HOST (0.0.0.0), INVENTARIO_PORT (8000), INVENTARIO_DB, INVENTARIO_LOG_DIR.
Un solo worker: el limitador de intentos de login y el EventBus viven en memoria."""
from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

import uvicorn
from platformdirs import user_log_dir

from server.logfilter import RedactarTokenFilter

FORMATO = "%(asctime)s %(levelname)s %(name)s: %(message)s"


def configurar_logs() -> Path:
    """Consola + archivo rotativo en el directorio de logs estandar (o INVENTARIO_LOG_DIR)."""
    d = Path(os.environ.get("INVENTARIO_LOG_DIR") or user_log_dir("InventarioApp"))
    d.mkdir(parents=True, exist_ok=True)
    ruta = d / "servidor.log"
    archivo = RotatingFileHandler(ruta, maxBytes=2_000_000, backupCount=3, encoding="utf-8")
    archivo.setFormatter(logging.Formatter(FORMATO))
    consola = logging.StreamHandler()
    consola.setFormatter(logging.Formatter(FORMATO))
    filtro = RedactarTokenFilter()
    for h in (archivo, consola):
        h.addFilter(filtro)
    raiz = logging.getLogger()
    raiz.setLevel(logging.INFO)
    raiz.handlers = [consola, archivo]
    for nombre in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        lg = logging.getLogger(nombre)
        lg.handlers = []
        lg.addFilter(filtro)
        lg.propagate = True       # uvicorn usa handlers propios; se centraliza en la raiz
    return ruta


def main() -> None:
    ruta_log = configurar_logs()
    from server.api.app import crear_app

    host = os.environ.get("INVENTARIO_HOST", "0.0.0.0")
    puerto = int(os.environ.get("INVENTARIO_PORT", "8000"))
    logging.getLogger(__name__).info("Iniciando en %s:%s (logs: %s)", host, puerto, ruta_log)
    uvicorn.run(crear_app(), host=host, port=puerto, workers=1, log_config=None)


if __name__ == "__main__":
    main()
