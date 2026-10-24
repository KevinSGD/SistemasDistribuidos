"""RiesgoService (escaneo/aplicacion de descuentos) y Scheduler en hilo daemon."""
from __future__ import annotations

import logging
import threading
from datetime import datetime
from typing import Callable

from server.domain.entities import EvaluacionRiesgo, NivelRiesgo, ProductoDominio
from server.domain.riesgo import evaluar_producto
from server.infrastructure.db.engine import sesion
from server.infrastructure.db.repos import DescuentoRepo, ProductoRepo

from .config_service import ConfigService
from .errores import exigir_admin, exigir_autenticado
from .eventos import DESCUENTO_CAMBIADO, PRODUCTOS_RETIRADOS, EventBus, evento

log = logging.getLogger(__name__)

SEVERIDAD = [NivelRiesgo.CRITICO, NivelRiesgo.ALTO, NivelRiesgo.MEDIO, NivelRiesgo.NORMAL]


def item_riesgo(p: ProductoDominio, ev: EvaluacionRiesgo) -> dict:
    return {
        "producto_id": p.id, "nombre": p.nombre, "categoria": p.categoria, "stock": p.stock,
        "stock_maximo": p.stock_maximo, "nivel": ev.nivel.value, "motivo": ev.motivo,
        "descuento": ev.descuento, "precio_original": ev.precio_original,
        "precio_final": ev.precio_final, "dias_para_vencer": ev.dias_para_vencer,
        "fecha_vencimiento": p.fecha_vencimiento.isoformat() if p.fecha_vencimiento else None,
    }


class RiesgoService:
    def __init__(self, sesion_factory, config: ConfigService, bus: EventBus | None = None,
                 reloj: Callable[[], datetime] = datetime.now):
        self._factory = sesion_factory
        self._config = config
        self._bus = bus
        self._reloj = reloj

    # -- escaneo ------------------------------------------------------------
    def escanear_manual(self, rol: str | None) -> dict:
        exigir_admin(rol)
        return self.escanear()

    def escanear(self) -> dict:
        """Una sola transaccion: retira vencidos y sincroniza los descuentos activos con la
        evaluacion vigente. Los eventos se publican despues del commit."""
        ahora = self._reloj()
        politica = self._config.politica_riesgo()
        retirados: list[str] = []
        aplicados: list[dict] = []
        removidos: list[dict] = []
        with sesion(self._factory) as s:
            prod, desc = ProductoRepo(s), DescuentoRepo(s)
            for p in prod.retirar_vencidos(ahora):
                retirados.append(p.nombre)
                if desc.desactivar(p.id):
                    removidos.append({"producto_id": p.id, "nombre": p.nombre,
                                      "porcentaje": 0.0, "motivo": "Producto retirado"})
            activos = prod.listar_activos()
            vigentes = {d.producto_id: d for d in desc.listar_activos()}
            ids_activos = {p.id for p in activos}
            # descuentos huerfanos de productos inactivos
            for pid in set(vigentes) - ids_activos:
                if desc.desactivar(pid):
                    removidos.append({"producto_id": pid, "nombre": "", "porcentaje": 0.0,
                                      "motivo": "Producto inactivo"})
            for p in activos:
                ev = evaluar_producto(p, politica, ahora)
                actual = vigentes.get(p.id)
                if ev.descuento > 0:
                    if (actual is None or actual.porcentaje != ev.descuento
                            or actual.motivo != ev.motivo):
                        desc.reemplazar_activo(p.id, ev.descuento, ev.motivo)
                        aplicados.append({"producto_id": p.id, "nombre": p.nombre,
                                          "porcentaje": ev.descuento, "motivo": ev.motivo})
                elif actual is not None:
                    desc.desactivar(p.id)
                    removidos.append({"producto_id": p.id, "nombre": p.nombre,
                                      "porcentaje": 0.0, "motivo": ""})
            evaluados = len(activos)
        if self._bus is not None:
            if retirados:
                self._bus.publicar(evento(PRODUCTOS_RETIRADOS, {"nombres": retirados}, "admin"))
            for d in aplicados + removidos:
                self._bus.publicar(evento(DESCUENTO_CAMBIADO, {
                    "producto_id": d["producto_id"], "porcentaje": d["porcentaje"],
                    "motivo": d["motivo"]}))
        return {"evaluados": evaluados, "retirados": retirados,
                "descuentos_aplicados": aplicados, "descuentos_removidos": removidos,
                "cambios": bool(retirados or aplicados or removidos)}

    # -- consultas ----------------------------------------------------------
    def _evaluar_activos(self) -> list[tuple[ProductoDominio, EvaluacionRiesgo]]:
        ahora, pol = self._reloj(), self._config.politica_riesgo()
        with sesion(self._factory) as s:
            activos = ProductoRepo(s).listar_activos()
        return [(p, evaluar_producto(p, pol, ahora)) for p in activos]

    def resumen_dashboard(self, rol: str | None) -> dict:
        exigir_admin(rol)
        pares = self._evaluar_activos()
        conteos = {n.value: 0 for n in SEVERIDAD}
        for _, ev in pares:
            conteos[ev.nivel.value] += 1
        atencion = [item_riesgo(p, ev) for p, ev in pares if ev.nivel != NivelRiesgo.NORMAL]
        orden = {n.value: i for i, n in enumerate(SEVERIDAD)}
        atencion.sort(key=lambda i: (
            orden[i["nivel"]],
            i["dias_para_vencer"] if i["dias_para_vencer"] is not None else 10**9,
            i["nombre"]))
        return {"total_activos": len(pares), "conteos": conteos, "atencion": atencion,
                "con_descuento": sum(1 for _, ev in pares if ev.descuento > 0)}

    def alertas_por_severidad(self, rol: str | None) -> dict:
        exigir_admin(rol)
        out: dict[str, list] = {n.value: [] for n in SEVERIDAD if n != NivelRiesgo.NORMAL}
        for p, ev in self._evaluar_activos():
            if ev.nivel != NivelRiesgo.NORMAL:
                out[ev.nivel.value].append(item_riesgo(p, ev))
        return out

    def ofertas(self, rol: str | None) -> list[dict]:
        """Activos, no vencidos, stock > 0 y descuento > 0 segun la evaluacion vigente
        (el mismo precio que cobra VentaService)."""
        exigir_autenticado(rol)
        return [item_riesgo(p, ev) for p, ev in self._evaluar_activos()
                if ev.descuento > 0 and not ev.vencido and p.stock > 0]


class Scheduler:
    """Ejecuta `tarea` cada `intervalo()` segundos en un hilo daemon. El intervalo se
    relee en cada ciclo. Una excepcion se registra y el ciclo continua."""

    def __init__(self, tarea: Callable[[], object], intervalo: Callable[[], float],
                 inmediato: bool = True):
        self._tarea = tarea
        self._intervalo = intervalo
        self._inmediato = inmediato
        self._stop = threading.Event()
        self._hilo: threading.Thread | None = None
        self.ejecuciones = 0
        self.errores = 0

    @classmethod
    def para(cls, riesgo: RiesgoService, config: ConfigService) -> "Scheduler":
        return cls(riesgo.escanear, lambda: config.valores()["intervalo_escaneo_segundos"])

    @property
    def activo(self) -> bool:
        return self._hilo is not None and self._hilo.is_alive()

    def iniciar(self) -> None:
        if self.activo:
            return
        self._stop.clear()
        self._hilo = threading.Thread(target=self._bucle, name="scheduler-riesgo", daemon=True)
        self._hilo.start()

    def detener(self, timeout: float = 5.0) -> None:
        self._stop.set()
        h = self._hilo
        if h is not None and h.is_alive() and h is not threading.current_thread():
            h.join(timeout)
        self._hilo = None

    def _esperar(self) -> bool:
        """True si se pidio detener durante la espera."""
        try:
            espera = max(0.01, float(self._intervalo()))
        except Exception:  # noqa: BLE001
            log.exception("No se pudo leer el intervalo de escaneo; usando 60 s")
            espera = 60.0
        return self._stop.wait(espera)

    def _bucle(self) -> None:
        if not self._inmediato and self._esperar():
            return
        while not self._stop.is_set():
            try:
                self._tarea()
            except Exception:  # noqa: BLE001
                self.errores += 1
                log.exception("Fallo el escaneo programado; se reintenta en el siguiente ciclo")
            finally:
                self.ejecuciones += 1
            if self._esperar():
                break
