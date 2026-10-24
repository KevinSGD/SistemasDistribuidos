"""Redondeo monetario del dominio: unica implementacion en shared/dinero.py (la comparte el
cliente para que la vista previa coincida exactamente con el servidor)."""
from shared.dinero import dec, redondear

__all__ = ["dec", "redondear"]
