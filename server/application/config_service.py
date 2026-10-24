"""ConfigService: lectura tipada y escritura validada y atomica de la configuracion."""
from __future__ import annotations

import math

from server.domain.entities import PoliticaRiesgo
from server.infrastructure.db.engine import sesion
from server.infrastructure.db.repos import ConfigRepo

from .errores import ErrorValidacion, exigir_admin
from .eventos import CONFIG_CAMBIADA, EventBus, evento

# clave -> (tipo, minimo, maximo). tipo: int | float | str | "str_no_vacio"
ESQUEMA: dict[str, tuple] = {
    "moneda": ("str_no_vacio", None, None),
    "nombre_negocio": ("str_no_vacio", None, None),
    "nit": (str, None, None),
    "direccion": (str, None, None),
    "telefono": (str, None, None),
    "dias_alerta_vencimiento": (int, 0, 3650),
    "dias_critico_vencimiento": (int, 0, 3650),
    "umbral_stock_bajo": (int, 0, 1_000_000),
    "descuento_critico": (float, 0, 100),
    "descuento_alto": (float, 0, 100),
    "descuento_medio": (float, 0, 100),
    "descuento_sobrestock": (float, 0, 100),
    "intervalo_escaneo_segundos": (int, 10, 3600),
    "iva_pct": (float, 0, 100),
    "decimales_moneda": (int, 0, 2),
    "inactividad_segundos": (int, 30, 3600),
    "aviso_segundos": (int, 5, None),
    "sesion_maxima_minutos": (int, 1, 10080),
}
CLAVES_PUBLICAS = ("moneda", "nombre_negocio", "nit", "direccion", "telefono", "iva_pct",
                   "decimales_moneda")


def _convertir(clave: str, valor):
    tipo, mn, mx = ESQUEMA[clave]
    if tipo in (str, "str_no_vacio"):
        if not isinstance(valor, str):
            raise ErrorValidacion(f"'{clave}' debe ser texto", {"clave": clave})
        valor = valor.strip()
        if tipo == "str_no_vacio" and not valor:
            raise ErrorValidacion(f"'{clave}' no puede estar vacío", {"clave": clave})
        return valor
    if isinstance(valor, bool):
        raise ErrorValidacion(f"'{clave}' debe ser numérico", {"clave": clave})
    try:
        num = float(valor)
    except (TypeError, ValueError):
        raise ErrorValidacion(f"'{clave}' debe ser numérico", {"clave": clave}) from None
    if not math.isfinite(num):
        raise ErrorValidacion(f"'{clave}' no es un número válido", {"clave": clave})
    if tipo is int:
        if num != int(num):
            raise ErrorValidacion(f"'{clave}' debe ser un entero", {"clave": clave})
        num = int(num)
    if mn is not None and num < mn or mx is not None and num > mx:
        raise ErrorValidacion(f"'{clave}' fuera de rango [{mn}, {mx}]",
                              {"clave": clave, "minimo": mn, "maximo": mx, "valor": num})
    return num


def _texto(v) -> str:
    return str(int(v)) if isinstance(v, float) and v == int(v) else str(v)


class ConfigService:
    def __init__(self, sesion_factory, bus: EventBus | None = None):
        self._factory = sesion_factory
        self._bus = bus

    def _leer(self) -> dict:
        with sesion(self._factory) as s:
            crudo = ConfigRepo(s).todos()
        out = {}
        for k, v in crudo.items():
            if k in ESQUEMA:
                try:
                    out[k] = _convertir(k, v)
                except ErrorValidacion:  # valor corrupto en BD: no tumba al sistema
                    out[k] = _convertir(k, _defecto(k))
            else:
                out[k] = v
        return out

    def valores(self) -> dict:
        """Lectura interna (sin rol) para otros servicios."""
        return self._leer()

    def obtener_todo(self, rol: str | None) -> dict:
        exigir_admin(rol)
        return self._leer()

    def obtener_publica(self) -> dict:
        v = self._leer()
        return {k: v[k] for k in CLAVES_PUBLICAS}

    def politica_riesgo(self) -> PoliticaRiesgo:
        v = self._leer()
        return PoliticaRiesgo(
            dias_alerta=v["dias_alerta_vencimiento"], dias_critico=v["dias_critico_vencimiento"],
            umbral_stock_bajo=v["umbral_stock_bajo"],
            descuento_critico=v["descuento_critico"], descuento_alto=v["descuento_alto"],
            descuento_medio=v["descuento_medio"], descuento_sobrestock=v["descuento_sobrestock"],
            decimales_moneda=v["decimales_moneda"],
        )

    def actualizar(self, cambios: dict, rol: str | None) -> dict:
        exigir_admin(rol)
        if not isinstance(cambios, dict) or not cambios:
            raise ErrorValidacion("Sin cambios de configuración")
        desconocidas = sorted(k for k in cambios if k not in ESQUEMA)
        if desconocidas:
            raise ErrorValidacion("Claves de configuración desconocidas",
                                  {"claves": desconocidas})
        nuevos = {k: _convertir(k, v) for k, v in cambios.items()}
        with sesion(self._factory) as s:
            repo = ConfigRepo(s)
            actual = {k: _convertir(k, v) for k, v in repo.todos().items() if k in ESQUEMA}
            final = {**actual, **nuevos}
            self._validar_cruzada(final)
            modificadas = sorted(k for k, v in nuevos.items() if actual.get(k) != v)
            for k in modificadas:
                repo.set(k, _texto(nuevos[k]))
        if modificadas and self._bus is not None:
            self._bus.publicar(evento(CONFIG_CAMBIADA, {"claves": modificadas}))
        return self._leer()

    @staticmethod
    def _validar_cruzada(f: dict) -> None:
        if f["aviso_segundos"] >= f["inactividad_segundos"]:
            raise ErrorValidacion("aviso_segundos debe ser menor que inactividad_segundos",
                                  {"aviso_segundos": f["aviso_segundos"],
                                   "inactividad_segundos": f["inactividad_segundos"]})
        if f["dias_critico_vencimiento"] > f["dias_alerta_vencimiento"]:
            raise ErrorValidacion(
                "dias_critico_vencimiento no puede superar dias_alerta_vencimiento",
                {"dias_critico_vencimiento": f["dias_critico_vencimiento"],
                 "dias_alerta_vencimiento": f["dias_alerta_vencimiento"]})


def _defecto(k: str):
    from server.infrastructure.db.seed import CONFIG_POR_DEFECTO
    return CONFIG_POR_DEFECTO[k]
