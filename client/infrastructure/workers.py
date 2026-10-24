"""Ejecucion de trabajo bloqueante (red) fuera del hilo de la GUI.

`ejecutar(fn, on_ok, on_error, parent)` DEBE llamarse desde el hilo de la GUI; `fn` corre en el
QThreadPool global y los callbacks vuelven al hilo de la GUI (conexion en cola)."""
from __future__ import annotations

import logging
from typing import Any, Callable

from PyQt6 import sip
from PyQt6.QtCore import QObject, QRunnable, QThreadPool, pyqtSignal

log = logging.getLogger(__name__)
_vivos: set["_Senales"] = set()      # evita que el recolector destruya las senales en vuelo


class _Senales(QObject):
    ok = pyqtSignal(object)
    error = pyqtSignal(object)


class _Tarea(QRunnable):
    def __init__(self, fn: Callable[[], Any], senales: _Senales):
        super().__init__()
        self._fn = fn
        self._senales = senales
        self.setAutoDelete(True)

    def run(self) -> None:
        try:
            resultado = self._fn()
        except BaseException as exc:  # noqa: BLE001  (se reenvia al hilo GUI)
            self._senales.error.emit(exc)
        else:
            self._senales.ok.emit(resultado)


def ejecutar(fn: Callable[[], Any], on_ok: Callable[[Any], None] | None = None,
             on_error: Callable[[BaseException], None] | None = None,
             parent: QObject | None = None) -> None:
    """Corre `fn()` en un hilo del pool. Si `parent` se destruye antes de terminar, los callbacks
    se omiten. Las excepciones dentro de los callbacks se registran (no abortan la aplicacion)."""
    senales = _Senales()                  # vive en el hilo que llama (GUI)
    _vivos.add(senales)

    def fin(cb, valor):
        try:
            if parent is not None and sip.isdeleted(parent):
                return
            if cb is not None:
                cb(valor)
            elif isinstance(valor, BaseException):
                log.warning("Error en tarea sin manejador: %r", valor)
        except Exception:  # noqa: BLE001
            log.exception("Fallo en callback de tarea")
        finally:
            _vivos.discard(senales)
            senales.deleteLater()

    senales.ok.connect(lambda v: fin(on_ok, v))
    senales.error.connect(lambda e: fin(on_error, e))
    QThreadPool.globalInstance().start(_Tarea(fn, senales))
