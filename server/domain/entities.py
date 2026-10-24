"""Entidades de dominio. Sin dependencias de frameworks (contrato entre capas)."""
from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class NivelRiesgo(str, Enum):
    NORMAL = "normal"
    MEDIO = "medio"
    ALTO = "alto"
    CRITICO = "critico"


@dataclass(frozen=True)
class ProductoDominio:
    id: int | None
    nombre: str
    categoria: str
    precio_base: float
    stock: int
    stock_maximo: int
    fecha_vencimiento: datetime | None
    activo: bool = True


@dataclass(frozen=True)
class PoliticaRiesgo:
    """Umbrales y descuentos (porcentaje 0-100). Llegan desde la configuración."""
    dias_alerta: int = 7
    dias_critico: int = 3
    umbral_stock_bajo: int = 10
    proporcion_sobrestock: float = 0.9
    descuento_critico: float = 50.0
    descuento_alto: float = 30.0
    descuento_sobrestock: float = 10.0
    decimales_moneda: int = 0   # 0 = pesos enteros


@dataclass(frozen=True)
class EvaluacionRiesgo:
    producto_id: int | None
    nivel: NivelRiesgo
    motivo: str
    descuento: float
    precio_original: float
    precio_final: float
    dias_para_vencer: int | None
    vencido: bool = False


@dataclass(frozen=True)
class LineaCompra:
    producto_id: int
    cantidad: int
