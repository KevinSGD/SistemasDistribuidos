"""JWT HS256 (PyJWT). El secreto viene del entorno o de un archivo generado en el primer arranque."""
from __future__ import annotations

import os
import secrets
from datetime import datetime
from pathlib import Path

import jwt

from .errores import TokenInvalido
from .rutas import directorio_datos, escribir_privado

ENV_SECRET = "INVENTARIO_JWT_SECRET"
NOMBRE_ARCHIVO = "jwt_secret"
ALGORITMO = "HS256"

_cache: dict[Path, str] = {}


def obtener_secreto() -> str:
    env = os.environ.get(ENV_SECRET)
    if env:
        return env
    ruta = directorio_datos() / NOMBRE_ARCHIVO
    if ruta in _cache:
        return _cache[ruta]
    if not ruta.exists():
        escribir_privado(ruta, secrets.token_hex(32))  # exclusivo: gana un solo proceso
    secreto = ruta.read_text(encoding="utf-8").strip()
    if not secreto:
        raise RuntimeError(f"Archivo de secreto JWT vacio: {ruta}")
    _cache[ruta] = secreto
    return secreto


def emitir(usuario_id: int, rol: str, jti: str, exp: datetime) -> str:
    """`exp` es un datetime ingenuo en hora local del servidor (convencion del proyecto)."""
    return jwt.encode(
        {"sub": str(usuario_id), "rol": rol, "jti": jti, "exp": int(exp.timestamp())},
        obtener_secreto(), algorithm=ALGORITMO,
    )


def decodificar(token: str, ahora: datetime | None = None) -> dict:
    """Verifica firma y claims; `exp` se compara contra `ahora` (reloj inyectable).
    Devuelve {'usuario_id', 'rol', 'jti', 'exp'}. Lanza TokenInvalido."""
    if not token or not isinstance(token, str):
        raise TokenInvalido("Token invalido")
    try:
        p = jwt.decode(token, obtener_secreto(), algorithms=[ALGORITMO],
                       options={"verify_exp": False, "require": ["sub", "rol", "jti", "exp"]})
        exp = int(p["exp"])
        usuario_id = int(p["sub"])
        rol, jti = str(p["rol"]), str(p["jti"])
    except (jwt.PyJWTError, ValueError, TypeError):
        raise TokenInvalido("Token invalido") from None
    ahora_ts = (ahora or datetime.now()).timestamp()
    if ahora_ts >= exp:
        raise TokenInvalido("Token expirado", {"motivo": "expirado"})
    return {"usuario_id": usuario_id, "rol": rol, "jti": jti, "exp": exp}
