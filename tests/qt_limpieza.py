"""Limpieza determinista de objetos Qt entre pruebas.

Las pruebas mueven la aplicacion a mano con `processEvents()`, y Qt NO entrega asi los
`deleteLater()` (solo los entrega un bucle de eventos real, `app.exec()`, que es el que usa la
aplicacion de verdad). Los widgets quedaban vivos hasta que el recolector de basura de Python los
finalizaba en un momento arbitrario, a veces DENTRO de un `processEvents` con senales en cola
dirigidas a ellos: cierre nativo (access violation) intermitente.

Evidencia (tests/stress/stress_login_logout.py, 4 procesos x 80 ciclos): sin esta limpieza caian
4 de 4; con ella, 0 de 4. Con el recolector desactivado tambien 0 de 4."""
from __future__ import annotations

import gc


def vaciar_qt(rondas: int = 3) -> None:
    """Entrega los borrados diferidos y recolecta en un punto seguro (fuera de todo evento)."""
    try:
        from PyQt6.QtCore import QCoreApplication, QEvent
    except ImportError:          # entornos solo-servidor (p. ej. el venv de Ubuntu)
        return
    app = QCoreApplication.instance()
    if app is None:
        return
    for _ in range(rondas):
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        app.processEvents()
    gc.collect()
