"""Utilidades de los tests E2E: bucle Qt, clientes reales y datos de prueba."""
from __future__ import annotations

import time
import uuid
from datetime import datetime, timedelta

from client.application.sesion import Aplicacion, OpcionesCliente
from shared.schemas import ClienteIn, CompraIn, ItemCompraIn, PagoIn, ProductoIn

#: Opciones de PRODUCCION sin tocar (throttle 10 s, tick 1 s, health 10 s, solo eventos espontaneos).
#: Los eventos de QTest llegan como espontaneos, asi que el IdleMonitor real los cuenta como actividad.
REAL = OpcionesCliente()


def esperar(condicion, timeout: float = 10.0, paso: float = 0.01) -> bool:
    """Procesa eventos Qt hasta que `condicion()` sea verdadera (o venza el tiempo)."""
    from PyQt6.QtWidgets import QApplication
    limite = time.monotonic() + timeout
    while time.monotonic() < limite:
        QApplication.processEvents()
        if condicion():
            return True
        time.sleep(paso)
    QApplication.processEvents()
    return bool(condicion())


def correr(segundos: float) -> None:
    """Deja correr el bucle de eventos `segundos` (sin condicion)."""
    esperar(lambda: False, timeout=segundos)


def nueva_app(url: str, opciones: OpcionesCliente | None = None, **kw) -> Aplicacion:
    a = Aplicacion(url, opciones or REAL, timeout=kw.pop("timeout", 8.0), **kw)
    a.iniciar()
    return a


def entrar(a: Aplicacion, usuario: str, password: str, timeout: float = 15.0) -> float:
    """Inicia sesion tecleando en el LoginView real. Devuelve time.monotonic() al abrirse la sesion."""
    a.login.input_usuario.setText(usuario)
    a.login.input_password.setText(password)
    a.login.btn_login.click()
    assert esperar(lambda: a.sesion is not None and a.ventana is not None, timeout), \
        f"No se pudo iniciar sesion como {usuario}: {a.login.lbl_error.text()!r}"
    return time.monotonic()


def cerrar_app(a: Aplicacion) -> None:
    """Cierre limpio de una Aplicacion de prueba (sin cerrar el QApplication)."""
    from PyQt6.QtWidgets import QApplication
    try:
        esperar(lambda: False, timeout=0.3)         # deja terminar peticiones en vuelo
        if a.sesion is not None:
            a._cerrando = False
            a._cerrar_sesion_local("fin", avisar_servidor=False)
        if a.login is not None:
            try:
                a.login.cerrada.disconnect()
            except TypeError:
                pass
            a.login.close()
            a.login.deleteLater()
        a.deleteLater()
    finally:
        QApplication.processEvents()


def crear_oferta(api, stock: int = 10, precio: float = 10000.0, nombre: str | None = None,
                 categoria: str = "Lácteos", dias: float = 1, **extra):
    """Producto que vence pronto: el servidor lo evalua como oferta critica (50 % por defecto)."""
    nombre = nombre or f"Leche {uuid.uuid4().hex[:6]}"
    return api.crear_producto(ProductoIn(
        nombre=nombre, categoria=categoria, precio_base=precio, stock=stock, stock_maximo=1000,
        fecha_vencimiento=datetime.now() + timedelta(days=dias, hours=12), **extra))


def compra_tarjeta(pid: int, cantidad: int = 1) -> CompraIn:
    return CompraIn(items=[ItemCompraIn(producto_id=pid, cantidad=cantidad)],
                    cliente=ClienteIn(nombre="Cliente E2E", documento="1020304050"),
                    pago=PagoIn(metodo="tarjeta_simulada"))


def esperar_ofertas(v, *productos, timeout: float = 10.0) -> bool:
    return esperar(lambda: v.estado == "lista" and all(p.id in v.tarjetas for p in productos), timeout)


def llenar_pago(dlg, nombre: str = "María Núñez", doc: str = "1020304050") -> None:
    dlg.input_nombre.setText(nombre)
    dlg.input_documento.setText(doc)


class ClienteExterno:
    """Cliente Windows en un proceso aparte (tests/e2e/cliente_worker.py): su teclado/raton no se
    mezcla con los clientes del proceso de pruebas. Los eventos llegan con la hora de pared del worker."""

    def __init__(self, url: str, usuario: str, password: str):
        import json
        import os
        import subprocess
        import sys
        import threading
        from pathlib import Path
        raiz = Path(__file__).resolve().parents[2]
        env = dict(os.environ, INV_E2E_PW=password, PYTHONUNBUFFERED="1", PYTHONIOENCODING="utf-8")
        self.proc = subprocess.Popen(
            [sys.executable, str(raiz / "tests" / "e2e" / "cliente_worker.py"), url, usuario],
            cwd=raiz, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True, encoding="utf-8")
        self.eventos: list[dict] = []
        self.cursor = 0
        self.stderr: list[str] = []

        def leer():
            for linea in self.proc.stdout:
                try:
                    self.eventos.append(json.loads(linea))
                except ValueError:
                    self.stderr.append(linea)
        threading.Thread(target=leer, daemon=True).start()
        threading.Thread(target=lambda: self.stderr.extend(self.proc.stderr), daemon=True).start()

    def enviar(self, orden: str) -> None:
        self.proc.stdin.write(orden + "\n")
        self.proc.stdin.flush()

    def ultimo(self, ev: str) -> dict | None:
        return next((e for e in reversed(self.eventos) if e["ev"] == ev), None)

    def todos(self, ev: str) -> list[dict]:
        return [e for e in self.eventos if e["ev"] == ev]

    def esperar_evento(self, ev: str, timeout: float = 15.0, desde: int = 0) -> dict | None:
        fin = time.monotonic() + timeout
        while time.monotonic() < fin:
            for e in self.eventos[desde:]:
                if e["ev"] == ev:
                    return e
            esperar(lambda: False, 0.02)
        return None

    def pedir(self, orden: str, ev: str, timeout: float = 10.0) -> dict | None:
        n = len(self.eventos)
        self.enviar(orden)
        return self.esperar_evento(ev, timeout, desde=n)

    def cerrar(self) -> None:
        try:
            self.enviar("salir")
        except OSError:
            pass
        try:
            self.proc.wait(8)
        except Exception:  # noqa: BLE001
            self.proc.kill()
