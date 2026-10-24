"""Cliente HTTP sincrono del contrato (docs/CONTRATO_API.md). Solo httpx + shared.schemas.

Es seguro llamarlo desde varios hilos de trabajo; NUNCA desde el hilo de la GUI (usar
client.infrastructure.workers.ejecutar). No renueva actividad salvo `registrar_actividad()`."""
from __future__ import annotations

import threading
from datetime import datetime
from typing import Any, Callable, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from shared.schemas import (
    ActividadOut, AlertasOut, CompraIn, ConfigOut, ConfigPublicaOut, ConfigUpdate,
    EscaneoOut, FacturaOut, HealthOut, ItemRiesgo, LoginIn, LoginOut, MensajeOut,
    ProductoIn, ProductoOut, ProductoUpdate, ResumenRiesgoOut, SesionOut, UsuarioIn,
    UsuarioOut, UsuarioUpdate,
)

from .config import TIMEOUT_CONEXION, TIMEOUT_LECTURA, normalizar_url

PREFIJO = "/api/v1"
CODIGOS_SESION_INVALIDA = frozenset({"SESION_INACTIVA", "SESION_CERRADA", "TOKEN_INVALIDO"})
T = TypeVar("T", bound=BaseModel)


class ApiError(Exception):
    """Respuesta de error del servidor ({codigo, mensaje, detalle})."""

    def __init__(self, codigo: str, mensaje: str, http: int = 0, detalle: dict | None = None):
        super().__init__(mensaje)
        self.codigo = codigo
        self.mensaje = mensaje
        self.http = http
        self.detalle = detalle or {}

    @property
    def reintentar_en(self) -> int | None:
        v = self.detalle.get("reintentar_en_segundos")
        return int(v) if isinstance(v, (int, float)) else None

    def __repr__(self) -> str:
        return f"ApiError({self.codigo!r}, {self.mensaje!r}, http={self.http})"


class ErrorConexion(Exception):
    """El servidor no responde (rechazo de conexion, timeout, red caida)."""

    def __init__(self, mensaje: str = "No se pudo conectar con el servidor", url: str = ""):
        super().__init__(mensaje)
        self.mensaje = mensaje
        self.url = url


class ApiClient:
    def __init__(self, base_url: str, *, token: str | None = None,
                 timeout: httpx.Timeout | float | None = None,
                 transport: httpx.BaseTransport | None = None,
                 on_sesion_invalida: Callable[[str], None] | None = None):
        """`on_sesion_invalida(codigo)` se invoca UNA vez (en el hilo que hizo la peticion)."""
        self.base_url = normalizar_url(base_url)
        self.token = token
        self.on_sesion_invalida = on_sesion_invalida
        self._notificado = False
        self._lock = threading.Lock()
        if timeout is None:
            timeout = httpx.Timeout(TIMEOUT_LECTURA, connect=TIMEOUT_CONEXION)
        self._http = httpx.Client(base_url=self.base_url + PREFIJO, timeout=timeout,
                                  transport=transport)

    # -- infraestructura ------------------------------------------------------------------
    def cerrar(self) -> None:
        self._http.close()

    def establecer_token(self, token: str | None) -> None:
        self.token = token
        self._notificado = False

    def url_websocket(self) -> str:
        """URL base del WebSocket (sin token): ws://host:puerto/ws."""
        esquema = "wss" if self.base_url.startswith("https") else "ws"
        return f"{esquema}{self.base_url[self.base_url.index('://'):]}/ws"

    def _notificar_sesion(self, codigo: str) -> None:
        with self._lock:
            if self._notificado:
                return
            self._notificado = True
        if self.on_sesion_invalida:
            self.on_sesion_invalida(codigo)

    def _pedir(self, metodo: str, ruta: str, *, json: Any = None, params: dict | None = None,
               auth: bool = True, notificar: bool = True) -> httpx.Response:
        headers = {"Authorization": f"Bearer {self.token}"} if auth and self.token else {}
        try:
            resp = self._http.request(metodo, ruta, json=json, params=params, headers=headers)
        except httpx.HTTPError as exc:      # ConnectError, timeouts, errores de red, protocolo
            raise ErrorConexion(
                f"No se pudo conectar con el servidor ({self.base_url})", self.base_url) from exc
        if resp.status_code >= 400:
            err = self._error(resp)
            if notificar and auth and err.http == 401 and err.codigo in CODIGOS_SESION_INVALIDA:
                self._notificar_sesion(err.codigo)
            raise err
        return resp

    @staticmethod
    def _error(resp: httpx.Response) -> ApiError:
        try:
            d = resp.json()
            if isinstance(d, dict) and "codigo" in d:
                detalle = d.get("detalle")
                return ApiError(str(d["codigo"]), str(d.get("mensaje", "")), resp.status_code,
                                detalle if isinstance(detalle, dict) else {})
        except ValueError:
            pass
        return ApiError("ERROR_HTTP", f"Respuesta inesperada del servidor ({resp.status_code})",
                        resp.status_code)

    @staticmethod
    def _modelo(cls: type[T], resp: httpx.Response) -> T:
        try:
            return cls.model_validate(resp.json())
        except (ValueError, ValidationError) as exc:
            raise ApiError("RESPUESTA_INVALIDA", "Respuesta del servidor no reconocida",
                           resp.status_code) from exc

    @staticmethod
    def _lista(cls: type[T], resp: httpx.Response) -> list[T]:
        try:
            return [cls.model_validate(x) for x in resp.json()]
        except (ValueError, TypeError, ValidationError) as exc:
            raise ApiError("RESPUESTA_INVALIDA", "Respuesta del servidor no reconocida",
                           resp.status_code) from exc

    # -- salud ----------------------------------------------------------------------------
    def health(self) -> HealthOut:
        return self._modelo(HealthOut, self._pedir("GET", "/health", auth=False))

    # -- auth -----------------------------------------------------------------------------
    def login(self, usuario: str, password: str) -> LoginOut:
        datos = LoginIn(usuario=usuario, password=password)
        r = self._pedir("POST", "/auth/login", json=datos.model_dump(), auth=False)
        out = self._modelo(LoginOut, r)
        self.establecer_token(out.token)
        return out

    def registrar_actividad(self) -> ActividadOut:
        """UNICA llamada que renueva la inactividad (ademas del login)."""
        return self._modelo(ActividadOut, self._pedir("POST", "/auth/actividad"))

    def estado_sesion(self) -> SesionOut:
        """No renueva la actividad."""
        return self._modelo(SesionOut, self._pedir("GET", "/auth/sesion"))

    def logout(self) -> MensajeOut:
        try:
            return self._modelo(MensajeOut, self._pedir("POST", "/auth/logout", notificar=False))
        finally:
            self.token = None

    # -- productos / ofertas --------------------------------------------------------------
    def listar_productos(self, activos: bool | None = None) -> list[ProductoOut]:
        params = {} if activos is None else {"activos": str(activos).lower()}
        return self._lista(ProductoOut, self._pedir("GET", "/productos", params=params))

    def crear_producto(self, datos: ProductoIn) -> ProductoOut:
        return self._modelo(ProductoOut, self._pedir(
            "POST", "/productos", json=datos.model_dump(mode="json")))

    def actualizar_producto(self, producto_id: int, datos: ProductoUpdate) -> ProductoOut:
        return self._modelo(ProductoOut, self._pedir(
            "PUT", f"/productos/{producto_id}",
            json=datos.model_dump(mode="json", exclude_unset=True)))

    def eliminar_producto(self, producto_id: int) -> None:
        self._pedir("DELETE", f"/productos/{producto_id}")

    def listar_ofertas(self) -> list[ItemRiesgo]:
        return self._lista(ItemRiesgo, self._pedir("GET", "/ofertas"))

    # -- riesgo ---------------------------------------------------------------------------
    def resumen_riesgo(self) -> ResumenRiesgoOut:
        return self._modelo(ResumenRiesgoOut, self._pedir("GET", "/riesgo/resumen"))

    def alertas_riesgo(self) -> AlertasOut:
        return self._modelo(AlertasOut, self._pedir("GET", "/riesgo/alertas"))

    def forzar_escaneo(self) -> EscaneoOut:
        return self._modelo(EscaneoOut, self._pedir("POST", "/riesgo/escaneo"))

    # -- compras / facturas ---------------------------------------------------------------
    def comprar(self, compra: CompraIn) -> FacturaOut:
        return self._modelo(FacturaOut, self._pedir(
            "POST", "/compras", json=compra.model_dump(mode="json")))

    def obtener_factura(self, numero: str) -> FacturaOut:
        return self._modelo(FacturaOut, self._pedir("GET", f"/facturas/{numero}"))

    def listar_facturas(self, desde: datetime | None = None, hasta: datetime | None = None,
                        limite: int | None = None) -> list[FacturaOut]:
        params: dict[str, Any] = {}
        if desde:
            params["desde"] = desde.isoformat()
        if hasta:
            params["hasta"] = hasta.isoformat()
        if limite:
            params["limite"] = limite
        return self._lista(FacturaOut, self._pedir("GET", "/facturas", params=params))

    # -- configuracion --------------------------------------------------------------------
    def obtener_config(self) -> ConfigOut:
        return self._modelo(ConfigOut, self._pedir("GET", "/config"))

    def actualizar_config(self, cambios: ConfigUpdate | dict) -> ConfigOut:
        modelo = cambios if isinstance(cambios, ConfigUpdate) else ConfigUpdate(**cambios)
        return self._modelo(ConfigOut, self._pedir(
            "PUT", "/config", json=modelo.model_dump(exclude_unset=True)))

    def config_publica(self) -> ConfigPublicaOut:
        return self._modelo(ConfigPublicaOut, self._pedir("GET", "/config/publica"))

    # -- usuarios -------------------------------------------------------------------------
    def listar_usuarios(self) -> list[UsuarioOut]:
        return self._lista(UsuarioOut, self._pedir("GET", "/usuarios"))

    def crear_usuario(self, datos: UsuarioIn) -> UsuarioOut:
        return self._modelo(UsuarioOut, self._pedir("POST", "/usuarios", json=datos.model_dump()))

    def actualizar_usuario(self, usuario_id: int, datos: UsuarioUpdate) -> UsuarioOut:
        return self._modelo(UsuarioOut, self._pedir(
            "PUT", f"/usuarios/{usuario_id}", json=datos.model_dump(exclude_unset=True)))
