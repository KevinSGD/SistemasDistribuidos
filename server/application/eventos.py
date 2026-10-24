"""EventBus en proceso. Publicable desde cualquier hilo.

Evento: {"tipo": str, "payload": dict, "para": "todos" | "admin" | {"usuario_id": int}}.
Sin loop vinculado, los callbacks corren de forma sincrona en el hilo que publica (tests).
Con `vincular_loop(loop)`, cada callback se agenda con `call_soon_threadsafe` en ese loop,
de modo que los consumidores asyncio (WebSocket) nunca se ejecutan en hilos ajenos.
Una excepcion de un suscriptor se registra y no afecta a los demas ni al publicador.
"""
from __future__ import annotations

import asyncio
import logging
import threading
from typing import Callable

log = logging.getLogger(__name__)

STOCK_ACTUALIZADO = "stock_actualizado"
DESCUENTO_CAMBIADO = "descuento_cambiado"
PRODUCTOS_RETIRADOS = "productos_retirados"
CONFIG_CAMBIADA = "config_cambiada"
SESION_CERRADA = "sesion_cerrada"
TIPOS = frozenset({STOCK_ACTUALIZADO, DESCUENTO_CAMBIADO, PRODUCTOS_RETIRADOS,
                   CONFIG_CAMBIADA, SESION_CERRADA})

Callback = Callable[[dict], None]


def evento(tipo: str, payload: dict, para: str | dict = "todos") -> dict:
    return {"tipo": tipo, "payload": payload, "para": para}


class EventBus:
    def __init__(self) -> None:
        self._subs: list[Callback] = []
        self._lock = threading.Lock()
        self._loop: asyncio.AbstractEventLoop | None = None

    def vincular_loop(self, loop: asyncio.AbstractEventLoop | None) -> None:
        self._loop = loop

    def suscribir(self, callback: Callback) -> Callable[[], None]:
        """Registra un callback. Devuelve la funcion que lo da de baja."""
        with self._lock:
            self._subs.append(callback)

        def baja() -> None:
            with self._lock:
                if callback in self._subs:
                    self._subs.remove(callback)
        return baja

    def publicar(self, ev: dict) -> None:
        if ev.get("tipo") not in TIPOS:
            raise ValueError(f"Tipo de evento desconocido: {ev.get('tipo')!r}")
        with self._lock:
            subs = list(self._subs)
        loop = self._loop
        for cb in subs:
            try:
                if loop is not None and not loop.is_closed():
                    loop.call_soon_threadsafe(self._invocar, cb, ev)
                else:
                    self._invocar(cb, ev)
            except Exception:  # noqa: BLE001
                log.exception("Fallo al despachar evento %s", ev.get("tipo"))

    @staticmethod
    def _invocar(cb: Callback, ev: dict) -> None:
        try:
            cb(ev)
        except Exception:  # noqa: BLE001
            log.exception("Suscriptor de eventos fallo con %s", ev.get("tipo"))
