"""Errores de seguridad. `codigo`/`http` coinciden con docs/CONTRATO_API.md."""
from server.domain.errors import ErrorDominio


class ErrorSeguridad(ErrorDominio):
    codigo, http = "ERROR_SEGURIDAD", 401


class CredencialesInvalidas(ErrorSeguridad):
    codigo, http = "CREDENCIALES_INVALIDAS", 401


class TokenInvalido(ErrorSeguridad):
    codigo, http = "TOKEN_INVALIDO", 401


class SesionInactiva(ErrorSeguridad):
    codigo, http = "SESION_INACTIVA", 401


class SesionCerrada(ErrorSeguridad):
    codigo, http = "SESION_CERRADA", 401


class RolNoPermitido(ErrorSeguridad):
    codigo, http = "ROL_NO_PERMITIDO", 403


class TooManyAttempts(ErrorSeguridad):
    codigo, http = "TOO_MANY_ATTEMPTS", 429
