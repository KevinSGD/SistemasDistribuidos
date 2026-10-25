"""DTOs Pydantic v2 del contrato (docs/CONTRATO_API.md). Fuente unica para servidor y cliente.

No importa nada del servidor. Los modelos de respuesta toleran campos extra (compatibilidad
hacia adelante del cliente); los de peticion los rechazan (errores tempranos)."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Rol = Literal["admin", "comprador"]
MetodoPago = Literal["efectivo", "tarjeta_simulada"]
PASSWORD_MIN = 8


class _Entrada(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _Salida(BaseModel):
    model_config = ConfigDict(extra="ignore", from_attributes=True)


# -- errores / salud -----------------------------------------------------------------------
class ErrorOut(_Salida):
    codigo: str
    mensaje: str
    detalle: dict = Field(default_factory=dict)


class HealthOut(_Salida):
    estado: str
    version: str
    so: str


# -- autenticacion -------------------------------------------------------------------------
class LoginIn(_Entrada):
    usuario: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=256)


class UsuarioSesionOut(_Salida):
    id: int
    nombre: str
    rol: Rol


class ParametrosSesion(_Salida):
    inactividad_segundos: int
    aviso_segundos: int


class LoginOut(_Salida):
    token: str
    expira_en: datetime
    usuario: UsuarioSesionOut
    sesion: ParametrosSesion


class ActividadOut(_Salida):
    segundos_restantes: int


class SesionOut(_Salida):
    segundos_restantes: int
    inactividad_segundos: int
    aviso_segundos: int


class MensajeOut(_Salida):
    ok: bool = True


# -- productos / ofertas -------------------------------------------------------------------
class ProductoIn(_Entrada):
    nombre: str = Field(min_length=1, max_length=100)
    categoria: str = Field(default="General", max_length=50)
    precio_base: float = Field(ge=0)
    stock: int = Field(default=0, ge=0)
    stock_maximo: int = Field(default=100, ge=0)
    fecha_vencimiento: datetime | None = None
    activo: bool = True


class ProductoUpdate(_Entrada):
    """Todos opcionales: solo se aplican los campos enviados."""
    nombre: str | None = Field(default=None, min_length=1, max_length=100)
    categoria: str | None = Field(default=None, max_length=50)
    precio_base: float | None = Field(default=None, ge=0)
    stock: int | None = Field(default=None, ge=0)
    stock_maximo: int | None = Field(default=None, ge=0)
    fecha_vencimiento: datetime | None = None
    activo: bool | None = None


class ProductoOut(_Salida):
    id: int
    nombre: str
    categoria: str
    precio_base: float
    stock: int
    stock_maximo: int
    fecha_vencimiento: datetime | None = None
    activo: bool


# -- riesgo --------------------------------------------------------------------------------
class ItemRiesgo(_Salida):
    """Tambien es el formato de /ofertas (precio final y motivo incluidos)."""
    producto_id: int
    nombre: str
    categoria: str
    stock: int
    stock_maximo: int
    nivel: Literal["normal", "medio", "alto", "critico"]
    motivo: str
    descuento: float
    precio_original: float
    precio_final: float
    dias_para_vencer: int | None = None
    fecha_vencimiento: datetime | None = None


class ResumenRiesgoOut(_Salida):
    total_activos: int
    conteos: dict[str, int]
    atencion: list[ItemRiesgo]
    con_descuento: int


class AlertasOut(_Salida):
    critico: list[ItemRiesgo] = Field(default_factory=list)
    alto: list[ItemRiesgo] = Field(default_factory=list)
    medio: list[ItemRiesgo] = Field(default_factory=list)


class CambioDescuento(_Salida):
    producto_id: int
    nombre: str
    porcentaje: float
    motivo: str


class EscaneoOut(_Salida):
    evaluados: int
    retirados: list[str]
    descuentos_aplicados: list[CambioDescuento]
    descuentos_removidos: list[CambioDescuento]
    cambios: bool


# -- compras / facturas --------------------------------------------------------------------
class ItemCompraIn(_Entrada):
    producto_id: int
    cantidad: int = Field(gt=0)


class ClienteIn(_Entrada):
    nombre: str = Field(default="", max_length=150)
    documento: str = Field(default="", max_length=50)


class PagoIn(_Entrada):
    metodo: MetodoPago
    efectivo_recibido: float | None = Field(default=None, ge=0)


class CompraIn(_Entrada):
    items: list[ItemCompraIn] = Field(min_length=1)
    cliente: ClienteIn = Field(default_factory=ClienteIn)
    pago: PagoIn


class NegocioOut(_Salida):
    nombre_negocio: str
    nit: str
    direccion: str
    telefono: str
    moneda: str


class ClienteOut(_Salida):
    nombre: str
    documento: str


class ItemFacturaOut(_Salida):
    producto_id: int
    nombre: str
    cantidad: int
    precio_original: float
    descuento_pct: float
    precio_final: float
    subtotal: float


class FacturaOut(_Salida):
    numero: str
    fecha: datetime
    negocio: NegocioOut
    cliente: ClienteOut
    items: list[ItemFacturaOut]
    subtotal: float          # sin descuento
    ahorro: float
    iva: float
    total: float
    metodo_pago: MetodoPago
    efectivo_recibido: float | None = None
    cambio: float | None = None
    usuario_id: int | None = None
    usuario_nombre: str | None = None   # cuenta que hizo la compra (no confundir con `cliente`)


class VentaMetodoOut(_Salida):
    metodo: str
    cantidad: int
    total: int


class TopProductoOut(_Salida):
    nombre: str
    unidades: int
    total: int


class ResumenFacturasOut(_Salida):
    """GET /facturas/resumen (solo admin). Montos enteros; `desde`/`hasta` = rango real."""
    cantidad: int
    subtotal: int
    ahorro: int
    iva: int
    total: int
    ticket_promedio: int
    por_metodo: list[VentaMetodoOut] = Field(default_factory=list)
    top_productos: list[TopProductoOut] = Field(default_factory=list)
    desde: datetime | None = None
    hasta: datetime | None = None


# -- configuracion -------------------------------------------------------------------------
class ConfigPublicaOut(_Salida):
    moneda: str
    nombre_negocio: str
    nit: str = ""
    direccion: str = ""
    telefono: str = ""
    iva_pct: float = 0
    decimales_moneda: int = 0


class ConfigOut(ConfigPublicaOut):
    model_config = ConfigDict(extra="allow", from_attributes=True)
    dias_alerta_vencimiento: int
    dias_critico_vencimiento: int
    umbral_stock_bajo: int
    descuento_critico: float
    descuento_alto: float
    descuento_sobrestock: float
    intervalo_escaneo_segundos: int
    inactividad_segundos: int
    aviso_segundos: int
    sesion_maxima_minutos: int


_Valor = int | float | str


class ConfigUpdate(_Entrada):
    """Cuerpo de PUT /config: solo las claves a cambiar. Rangos y reglas cruzadas las valida
    el servidor (ConfigService) y responden 422 VALIDACION."""
    moneda: str | None = None
    nombre_negocio: str | None = None
    nit: str | None = None
    direccion: str | None = None
    telefono: str | None = None
    dias_alerta_vencimiento: _Valor | None = None
    dias_critico_vencimiento: _Valor | None = None
    umbral_stock_bajo: _Valor | None = None
    descuento_critico: _Valor | None = None
    descuento_alto: _Valor | None = None
    descuento_sobrestock: _Valor | None = None
    intervalo_escaneo_segundos: _Valor | None = None
    iva_pct: _Valor | None = None
    inactividad_segundos: _Valor | None = None
    aviso_segundos: _Valor | None = None
    sesion_maxima_minutos: _Valor | None = None


# -- usuarios ------------------------------------------------------------------------------
class UsuarioOut(_Salida):
    id: int
    nombre: str
    usuario: str
    rol: Rol
    activo: bool


class UsuarioIn(_Entrada):
    nombre: str = Field(min_length=1, max_length=100)
    usuario: str = Field(min_length=3, max_length=50, pattern=r"^\S+$")
    password: str = Field(min_length=PASSWORD_MIN, max_length=256)
    rol: Rol = "comprador"


class UsuarioUpdate(_Entrada):
    nombre: str | None = Field(default=None, min_length=1, max_length=100)
    rol: Rol | None = None
    activo: bool | None = None
    password: str | None = Field(default=None, min_length=PASSWORD_MIN, max_length=256)


# -- WebSocket -----------------------------------------------------------------------------
class EventoWS(_Salida):
    """Mensaje servidor -> cliente por /ws."""
    evento: Literal["stock_actualizado", "descuento_cambiado", "productos_retirados",
                    "config_cambiada", "sesion_cerrada", "factura_creada"]
    payload: dict
