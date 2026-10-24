"""Punto de entrada del cliente: `python -m client.main`.

Opciones: --url URL (sobrescribe ajustes), --salir-en SEGUNDOS (solo pruebas de humo)."""
from __future__ import annotations

import argparse
import logging
import sys

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication

from client.application.sesion import Aplicacion
from client.presentation.styles.theme import aplicar_tema


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="client.main")
    parser.add_argument("--url", default=None)
    parser.add_argument("--salir-en", type=float, default=None, help=argparse.SUPPRESS)
    args, resto = parser.parse_known_args(argv if argv is not None else sys.argv[1:])

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    app = QApplication([sys.argv[0], *resto])
    app.setStyle("Fusion")
    aplicar_tema(app)

    controlador = Aplicacion(url=args.url)
    controlador.iniciar()
    if args.salir_en is not None:
        QTimer.singleShot(int(args.salir_en * 1000), app.quit)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
