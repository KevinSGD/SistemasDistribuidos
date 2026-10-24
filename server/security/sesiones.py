"""AuthService: login, validacion por inactividad, actividad, logout.

Cada operacion abre su propia sesion de BD de vida corta (commit al salir)."""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Callable, Protocol

from server.infrastructure.db.engine import sesion as _abrir
from server.infrastructure.db.repos import ConfigRepo, SesionRepo, UsuarioRepo

from . import tokens
from .errores import (CredencialesInvalidas, SesionCerrada, SesionInactiva, TokenInvalido,
                      TooManyAttempts)
from .hashing import hashear, verificar

MSG_LOGIN = "Usuario o contrasena incorrectos"
_HASH_SENUELO = hashear("senuelo-para-igualar-tiempos")
INACTIVIDAD_DEF, AVISO_DEF, MAXIMA_DEF = 180, 30, 480


class Bus(Protocol):
    def publicar(self, evento: str, payload: dict, usuario_id: int | None = None) -> None: ...


@dataclass(frozen=True)
class Contexto:
    usuario_id: int
    rol: str
    jti: str


@dataclass(frozen=True)
class EstadoSesion:
    segundos_restantes: int
    inactividad_segundos: int
    aviso_segundos: int


class LimitadorIntentos:
    """Bloqueo temporal tras N fallos consecutivos por usuario (en memoria)."""

    def __init__(self, max_intentos: int = 5, bloqueo_segundos: int = 60,
                 reloj: Callable[[], datetime] = datetime.now):
        self.max, self.bloqueo, self.reloj = max_intentos, bloqueo_segundos, reloj
        self._fallos: dict[str, int] = {}
        self._hasta: dict[str, datetime] = {}

    def comprobar(self, clave: str) -> None:
        hasta = self._hasta.get(clave)
        if hasta is None:
            return
        restante = (hasta - self.reloj()).total_seconds()
        if restante > 0:
            raise TooManyAttempts("Demasiados intentos fallidos. Intente mas tarde",
                                  {"reintentar_en_segundos": int(restante) + 1})
        del self._hasta[clave]
        self._fallos.pop(clave, None)

    def fallo(self, clave: str) -> None:
        n = self._fallos.get(clave, 0) + 1
        self._fallos[clave] = n
        if n >= self.max:
            self._hasta[clave] = self.reloj() + timedelta(seconds=self.bloqueo)

    def exito(self, clave: str) -> None:
        self._fallos.pop(clave, None)
        self._hasta.pop(clave, None)


def _entero(valor, defecto: int) -> int:
    try:
        return int(float(valor))
    except (TypeError, ValueError):
        return defecto


class AuthService:
    def __init__(self, sesion_factory, bus: Bus | None = None,
                 reloj: Callable[[], datetime] = datetime.now,
                 limitador: LimitadorIntentos | None = None):
        self.factory, self.bus, self.reloj = sesion_factory, bus, reloj
        self.limitador = limitador or LimitadorIntentos(reloj=reloj)

    # ── configuracion (se lee en cada uso) ──
    @staticmethod
    def _cfg(s) -> tuple[int, int]:
        c = ConfigRepo(s)
        return (_entero(c.get("inactividad_segundos"), INACTIVIDAD_DEF),
                _entero(c.get("aviso_segundos"), AVISO_DEF))

    # ── login ──
    def login(self, usuario: str, password: str) -> dict:
        if not isinstance(usuario, str) or not isinstance(password, str) \
                or not usuario.strip() or not password:
            raise CredencialesInvalidas(MSG_LOGIN)
        clave = usuario.strip().lower()
        self.limitador.comprobar(clave)
        with _abrir(self.factory) as s:
            u = UsuarioRepo(s).obtener_por_usuario(usuario.strip())
            ok, rehash = verificar(password, u.password_hash if u else _HASH_SENUELO)
            if not (u and ok and u.activo):
                self.limitador.fallo(clave)
                raise CredencialesInvalidas(MSG_LOGIN)
            self.limitador.exito(clave)
            if rehash:
                UsuarioRepo(s).actualizar(u.id, password_hash=hashear(password))
            ahora = self.reloj()
            cfg = ConfigRepo(s)
            maxima = _entero(cfg.get("sesion_maxima_minutos"), MAXIMA_DEF)
            inact, aviso = self._cfg(s)
            jti = uuid.uuid4().hex
            SesionRepo(s).crear(jti, u.id, ahora)
            exp = ahora + timedelta(minutes=maxima)
            token = tokens.emitir(u.id, u.rol, jti, exp)
            return {
                "token": token, "expira_en": exp.isoformat(),
                "usuario": {"id": u.id, "nombre": u.nombre, "rol": u.rol},
                "sesion": {"inactividad_segundos": inact, "aviso_segundos": aviso},
            }

    # ── validacion ──
    def _resolver(self, token_o_ctx) -> tuple[str, int | None]:
        if isinstance(token_o_ctx, Contexto):
            return token_o_ctx.jti, token_o_ctx.usuario_id
        p = tokens.decodificar(token_o_ctx, self.reloj())
        return p["jti"], p["usuario_id"]

    def _validar(self, s, jti: str, usuario_id: int | None) -> tuple[Contexto, int, int, float]:
        """Devuelve (ctx, inactividad, aviso, segundos_transcurridos). Si caduco, cierra y lanza."""
        ses = SesionRepo(s).obtener_por_jti(jti)
        if ses is None or (usuario_id is not None and ses.usuario_id != usuario_id):
            raise TokenInvalido("Token invalido")
        if ses.cerrada:
            raise SesionCerrada("La sesion fue cerrada", {"motivo": ses.motivo_cierre})
        u = UsuarioRepo(s).obtener(ses.usuario_id)
        if u is None or not u.activo:
            SesionRepo(s).cerrar(jti, "usuario_inactivo")
            s.commit()
            raise SesionCerrada("La sesion fue cerrada", {"motivo": "usuario_inactivo"})
        inact, aviso = self._cfg(s)
        transcurrido = (self.reloj() - ses.ultima_actividad).total_seconds()
        if transcurrido > inact:
            SesionRepo(s).cerrar(jti, "inactividad")
            s.commit()  # persistir el cierre aunque se lance la excepcion
            if self.bus:
                self.bus.publicar("sesion_cerrada", {"motivo": "inactividad"}, u.id)
            raise SesionInactiva("Sesion cerrada por inactividad")
        return Contexto(u.id, u.rol, jti), inact, aviso, transcurrido

    def validar_token(self, token: str) -> Contexto:
        """No renueva la actividad."""
        jti, uid = self._resolver(token)
        with _abrir(self.factory) as s:
            return self._validar(s, jti, uid)[0]

    # ── actividad / estado ──
    def registrar_actividad(self, token_o_ctx) -> int:
        """Unico metodo (junto con login) que renueva ultima_actividad. Devuelve segundos restantes."""
        jti, uid = self._resolver(token_o_ctx)
        with _abrir(self.factory) as s:
            _, inact, _, _ = self._validar(s, jti, uid)
            SesionRepo(s).tocar(jti, self.reloj())
            return inact

    def estado_sesion(self, token_o_ctx) -> EstadoSesion:
        jti, uid = self._resolver(token_o_ctx)
        with _abrir(self.factory) as s:
            _, inact, aviso, t = self._validar(s, jti, uid)
            return EstadoSesion(max(0, int(inact - t)), inact, aviso)

    # ── cierre ──
    def logout(self, token_o_ctx) -> None:
        jti, _ = self._resolver(token_o_ctx)
        with _abrir(self.factory) as s:
            SesionRepo(s).cerrar(jti, "logout")

    def cerrar_sesiones_de(self, usuario_id: int, motivo: str = "revocada") -> int:
        with _abrir(self.factory) as s:
            n = SesionRepo(s).cerrar_todas_de_usuario(usuario_id, motivo)
        if n and self.bus:
            self.bus.publicar("sesion_cerrada", {"motivo": motivo}, usuario_id)
        return n
