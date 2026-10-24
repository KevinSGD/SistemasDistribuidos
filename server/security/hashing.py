"""Hash de contrasenas: argon2id; verifica ademas el formato legacy `sha256$<hex>`."""
from __future__ import annotations

import hashlib
import hmac

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

_ph = PasswordHasher()  # argon2id por defecto
PREFIJO_SHA256 = "sha256$"


def hashear(password: str) -> str:
    return _ph.hash(password)


def verificar(password: str, hash_guardado: str) -> tuple[bool, bool]:
    """Devuelve (ok, necesita_rehash). Nunca lanza por un hash invalido."""
    if not hash_guardado or not isinstance(hash_guardado, str) or password is None:
        return False, False
    try:
        if hash_guardado.startswith(PREFIJO_SHA256):
            esperado = hash_guardado[len(PREFIJO_SHA256):].strip().lower()
            real = hashlib.sha256(password.encode("utf-8")).hexdigest()
            ok = hmac.compare_digest(real.encode(), esperado.encode())
            return ok, ok
        if hash_guardado.startswith("$argon2"):
            _ph.verify(hash_guardado, password)
            return True, _ph.check_needs_rehash(hash_guardado)
    except (VerificationError, InvalidHashError, ValueError, TypeError):
        return False, False
    return False, False
