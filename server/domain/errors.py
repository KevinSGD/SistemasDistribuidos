"""Errores de dominio. `codigo` coincide con docs/CONTRATO_API.md."""


class ErrorDominio(Exception):
    codigo = "ERROR_DOMINIO"
    http = 400

    def __init__(self, mensaje: str, detalle: dict | None = None):
        super().__init__(mensaje)
        self.mensaje = mensaje
        self.detalle = detalle or {}


class StockInsuficiente(ErrorDominio):
    codigo, http = "STOCK_INSUFICIENTE", 409


class ProductoVencido(ErrorDominio):
    codigo, http = "PRODUCTO_VENCIDO", 409


class ProductoInactivo(ErrorDominio):
    codigo, http = "PRODUCTO_INACTIVO", 409


class CantidadInvalida(ErrorDominio):
    codigo, http = "VALIDACION", 422


class NoEncontrado(ErrorDominio):
    codigo, http = "NO_ENCONTRADO", 404
