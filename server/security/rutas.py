"""Directorio de datos del servidor (secreto JWT, credenciales iniciales). Nunca en el repo."""
import os
from pathlib import Path

ENV_DATA_DIR = "INVENTARIO_DATA_DIR"


def directorio_datos() -> Path:
    """INVENTARIO_DATA_DIR, o el directorio de la base de datos (INVENTARIO_DB / por defecto)."""
    d = os.environ.get(ENV_DATA_DIR)
    if d:
        p = Path(d)
    else:
        from server.infrastructure.db.engine import ruta_db_por_defecto
        p = ruta_db_por_defecto().parent
    p.mkdir(parents=True, exist_ok=True)
    return p


def escribir_privado(ruta: Path, contenido: str, *, exclusivo: bool = True) -> bool:
    """Escribe con permisos 0600 (efectivos en POSIX). Con exclusivo=True no pisa: False si existe."""
    flags = os.O_WRONLY | os.O_CREAT | (os.O_EXCL if exclusivo else os.O_TRUNC)
    try:
        fd = os.open(ruta, flags, 0o600)
    except FileExistsError:
        return False
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(contenido)
    try:
        os.chmod(ruta, 0o600)
    except OSError:
        pass
    return True
