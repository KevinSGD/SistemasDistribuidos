"""Manejo global de errores -> JSON {codigo, mensaje, detalle}."""
from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from server.domain.errors import ErrorDominio

log = logging.getLogger(__name__)


def _json(status: int, codigo: str, mensaje: str, detalle: dict | None = None,
          headers: dict | None = None) -> JSONResponse:
    return JSONResponse(status_code=status, headers=headers,
                        content={"codigo": codigo, "mensaje": mensaje, "detalle": detalle or {}})


def registrar_manejadores(app: FastAPI) -> None:
    @app.exception_handler(ErrorDominio)
    async def _dominio(_: Request, exc: ErrorDominio):
        headers = None
        espera = exc.detalle.get("reintentar_en_segundos")
        if exc.http == 429 and espera is not None:
            headers = {"Retry-After": str(espera)}
        return _json(exc.http, exc.codigo, exc.mensaje, exc.detalle, headers)

    @app.exception_handler(RequestValidationError)
    async def _validacion(_: Request, exc: RequestValidationError):
        errores = [{"campo": ".".join(str(p) for p in e.get("loc", ())), "mensaje": e.get("msg", ""),
                    "tipo": e.get("type", "")} for e in exc.errors()]
        return _json(422, "VALIDACION", "Datos de la petición inválidos", {"errores": errores})

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException):
        codigos = {404: "NO_ENCONTRADO", 405: "METODO_NO_PERMITIDO"}
        return _json(exc.status_code, codigos.get(exc.status_code, "ERROR_HTTP"),
                     str(exc.detail), headers=getattr(exc, "headers", None))

    @app.exception_handler(Exception)
    async def _inesperado(_: Request, exc: Exception):
        log.exception("Error no controlado", exc_info=exc)
        return _json(500, "ERROR_INTERNO", "Error interno del servidor")
