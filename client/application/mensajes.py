"""Textos de usuario para errores y motivos de cierre de sesion."""
from __future__ import annotations

from client.infrastructure.api_client import ApiError, ErrorConexion

MENSAJE_INACTIVIDAD = "Sesión cerrada por inactividad"

_POR_CODIGO_SESION = {
    "SESION_INACTIVA": MENSAJE_INACTIVIDAD,
    "SESION_CERRADA": "Tu sesión fue cerrada. Inicia sesión de nuevo",
    "TOKEN_INVALIDO": "Sesión no válida. Inicia sesión de nuevo",
}
_POR_MOTIVO_WS = {
    "inactividad": MENSAJE_INACTIVIDAD,
    "usuario_desactivado": "Tu usuario fue desactivado por un administrador",
    "password_cambiada": "Tu contraseña fue cambiada. Inicia sesión de nuevo",
    "token_invalido": "Sesión no válida. Inicia sesión de nuevo",
    "logout": "Sesión cerrada",
}


def motivo_cierre(codigo_api: str | None = None, motivo_ws: str | None = None) -> str:
    """Mensaje de login para un cierre decidido por el servidor."""
    if codigo_api == "SESION_CERRADA" and motivo_ws in _POR_MOTIVO_WS:
        return _POR_MOTIVO_WS[motivo_ws]
    if codigo_api in _POR_CODIGO_SESION:
        return _POR_CODIGO_SESION[codigo_api]
    if motivo_ws in _POR_MOTIVO_WS:
        return _POR_MOTIVO_WS[motivo_ws]
    return _POR_CODIGO_SESION["TOKEN_INVALIDO"]


def texto_error(exc: BaseException) -> str:
    """Mensaje claro para mostrar al usuario a partir de una excepcion del ApiClient."""
    if isinstance(exc, ErrorConexion):
        return ("No se pudo conectar con el servidor. Verifica que esté encendido y la "
                "dirección sea correcta")
    if isinstance(exc, ApiError):
        if exc.codigo == "CREDENCIALES_INVALIDAS":
            return "Usuario o contraseña incorrectos"
        if exc.codigo == "TOO_MANY_ATTEMPTS":
            n = exc.reintentar_en
            return (f"Demasiados intentos fallidos. Reintenta en {n} segundos" if n
                    else "Demasiados intentos fallidos. Espera un momento")
        if exc.codigo in _POR_CODIGO_SESION:
            return _POR_CODIGO_SESION[exc.codigo]
        if exc.codigo == "ERROR_INTERNO":
            return "Error interno del servidor. Intenta de nuevo"
        return exc.mensaje or "Error inesperado"
    return "Error inesperado"
