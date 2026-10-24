"""Capturas REALES del cliente Windows (plataforma 'windows', con fuentes del sistema) conectado al
servidor Linux/WSL2. NO es un test de pytest: se ejecuta aparte (abre ventanas reales ~1 min).

    .venv\\Scripts\\python.exe -m tests.e2e.capturas [directorio_salida]

Levanta su propia instancia aislada del servidor (puerto desde 8010), la siembra con datos de una tienda
y recorre: login, dashboard admin, configuracion (Seguridad de sesion), catalogo del comprador, pago,
factura, aviso de inactividad con cuenta regresiva y login con "Sesion cerrada por inactividad"."""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))
os.environ.pop("QT_QPA_PLATFORM", None)              # plataforma real de Windows (no offscreen)
_CFG = tempfile.mkdtemp(prefix="inv_cap_cfg_")
os.environ["INVENTARIO_CLIENT_DIR"] = _CFG
os.environ.pop("INVENTARIO_URL", None)
for _f in (sys.stdout, sys.stderr):
    if hasattr(_f, "reconfigure"):
        _f.reconfigure(encoding="utf-8", errors="replace")

from PyQt6.QtCore import QPoint, Qt                                  # noqa: E402
from PyQt6.QtGui import QColor, QPainter, QPixmap                     # noqa: E402
from PyQt6.QtWidgets import QApplication                              # noqa: E402

from client.application.sesion import Aplicacion, OpcionesCliente      # noqa: E402
from client.infrastructure.api_client import ApiClient                # noqa: E402
from client.presentation.styles.theme import aplicar_tema              # noqa: E402
from shared.schemas import (ClienteIn, CompraIn, ItemCompraIn, PagoIn, ProductoIn, UsuarioIn,
                            UsuarioUpdate)  # noqa: E402
from tests.e2e.helpers import entrar, esperar                          # noqa: E402
from tests.e2e.wsl import WslServidor                                  # noqa: E402

SALIDA = Path(sys.argv[1]) if len(sys.argv) > 1 else RAIZ / "docs" / "capturas"


def sembrar(api: ApiClient, comprador: ApiClient) -> dict:
    api.actualizar_config({
        "nombre_negocio": "Supermercado La Esperanza", "nit": "900.123.456-7",
        "direccion": "Cra 7 # 12-34, Bogotá", "telefono": "601 555 0134", "iva_pct": 19})
    ahora = datetime.now()
    def p(nombre, cat, precio, stock, dias=None, maximo=200):
        return api.crear_producto(ProductoIn(
            nombre=nombre, categoria=cat, precio_base=precio, stock=stock, stock_maximo=maximo,
            fecha_vencimiento=None if dias is None else ahora + timedelta(days=dias, hours=6)))
    prods = {
        "leche": p("Leche entera 1 L", "Lácteos", 4200, 48, 1),
        "yogur": p("Yogur griego natural 500 g", "Lácteos", 7800, 22, 2),
        "queso": p("Queso campesino 500 g", "Lácteos", 12900, 14, 5),
        "pan": p("Pan tajado integral", "Panadería", 6900, 30, 1),
        "croissant": p("Croissant de mantequilla x4", "Panadería", 9500, 12, 3),
        "pollo": p("Pechuga de pollo 1 kg", "Carnes", 18900, 9, 2),
        "carne": p("Carne molida de res 500 g", "Carnes", 16400, 17, 6),
        "fresa": p("Fresas bandeja 500 g", "Frutería", 8900, 25, 2),
        "banano": p("Banano criollo x6", "Frutería", 3500, 180, 4, maximo=200),
        "jugo": p("Jugo de naranja 1 L", "Bebidas", 5600, 64, 6),
        "arroz": p("Arroz blanco 1 kg", "Abarrotes", 4900, 120, 240),
        "aceite": p("Aceite de girasol 900 ml", "Abarrotes", 15800, 6, 300),
        "cafe": p("Café molido 250 g", "Abarrotes", 11300, 40, 180),
    }
    # historial de ventas para que el sistema tenga uso real
    for clave, cant in (("arroz", 3), ("cafe", 2), ("aceite", 1)):
        comprador.comprar(CompraIn(items=[ItemCompraIn(producto_id=prods[clave].id, cantidad=cant)],
                                   cliente=ClienteIn(nombre="Cliente de mostrador", documento="222222222"),
                                   pago=PagoIn(metodo="tarjeta_simulada")))
    for nombre, usuario, activo in (("Laura Gómez", "laura", True), ("Andrés Pérez", "andres", True),
                                    ("Carlos Ruiz", "carlos", False)):
        u = api.crear_usuario(UsuarioIn(nombre=nombre, usuario=usuario, password="clave-demo-1234"))
        if not activo:
            api.actualizar_usuario(u.id, UsuarioUpdate(activo=False))
    api.forzar_escaneo()
    return prods


def guardar(widget, nombre: str, destino: Path) -> Path:
    esperar(lambda: False, 0.4)
    pm = widget.grab()
    ruta = destino / nombre
    pm.save(str(ruta), "PNG")
    print(f"  {nombre}: {pm.width()}x{pm.height()}")
    return ruta


def componer_con_dialogo(ventana, dialogo) -> QPixmap:
    """Ventana principal atenuada con el dialogo modal centrado encima (lo que ve el usuario)."""
    base = ventana.grab()
    d = dialogo.grab()
    lb, ld = base.deviceIndependentSize(), d.deviceIndependentSize()     # coordenadas logicas (DPI)
    p = QPainter(base)
    p.fillRect(0, 0, int(lb.width()), int(lb.height()), QColor(15, 23, 42, 110))
    x = int((lb.width() - ld.width()) // 2)
    y = int((lb.height() - ld.height()) // 2)
    p.fillRect(x - 1, y - 1, int(ld.width()) + 2, int(ld.height()) + 2, QColor(100, 116, 139))
    p.drawPixmap(QPoint(x, y), d)
    p.end()
    return base


def main() -> int:
    SALIDA.mkdir(parents=True, exist_ok=True)
    for viejo in SALIDA.glob("*.png"):
        viejo.unlink()
    qapp = QApplication(["capturas"])
    qapp.setStyle("Fusion")
    aplicar_tema(qapp)
    print("plataforma Qt:", qapp.platformName())
    srv = WslServidor("capturas").iniciar()
    apps = []
    try:
        print(f"servidor Linux en {srv.url} (PID {srv.pid}); health: {srv.health()}")
        adm_api = ApiClient(srv.url)
        adm_api.login("admin", srv.admin_pw)
        comp_api = ApiClient(srv.url)
        comp_api.login("comprador", srv.comp_pw)
        sembrar(adm_api, comp_api)

        # ---- 1. login (con la prueba de servidor: "Servidor en linea (Linux)") -------------------
        admin = Aplicacion(srv.url, OpcionesCliente(), timeout=8.0)
        apps.append(admin)
        admin.iniciar()
        admin.login.btn_servidor.click()                      # despliega "Servidor" + Probar
        admin.login._probar()
        esperar(lambda: "en línea" in admin.login.lbl_servidor.text(), 15)
        guardar(admin.login, "01_login.png", SALIDA)

        # ---- 2/3. admin: dashboard y configuracion -----------------------------------------------
        entrar(admin, "admin", srv.admin_pw)
        w = admin.ventana
        esperar(lambda: w.barra.conexion._texto.text() == "Servidor en línea · Linux", 15)
        assert w.barra.conexion._texto.text() == "Servidor en línea · Linux"
        esperar(lambda: w.vistas["dashboard"].cargada, 10)
        guardar(w, "02_dashboard_admin.png", SALIDA)
        w.ir_a("inventario")
        esperar(lambda: w.vistas["inventario"].cargada, 10)
        guardar(w, "03_inventario_admin.png", SALIDA)
        w.ir_a("configuracion")
        esperar(lambda: w.vistas["configuracion"].cargada and bool(w.vistas["configuracion"]._base), 10)
        guardar(w, "04_configuracion_seguridad_de_sesion.png", SALIDA)
        w.ir_a("usuarios")
        esperar(lambda: w.vistas["usuarios"].cargada, 10)
        guardar(w, "05_usuarios_admin.png", SALIDA)
        admin.cerrar_sesion()
        esperar(lambda: admin.sesion is None, 10)
        admin.login.hide()

        # ---- 4. comprador: catalogo, carrito, pago, factura ---------------------------------------
        comprador = Aplicacion(srv.url, OpcionesCliente(), timeout=8.0)
        apps.append(comprador)
        comprador.iniciar()
        entrar(comprador, "comprador", srv.comp_pw)
        v = comprador.ventana
        esperar(lambda: v.estado == "lista" and len(v.tarjetas) >= 8, 15)
        esperar(lambda: v.config.iva_pct == 19, 10)
        guardar(v, "06_catalogo_comprador.png", SALIDA)
        ids = list(v.tarjetas)
        for pid, veces in ((ids[0], 2), (ids[1], 1), (ids[3], 1)):
            for _ in range(veces):
                v.tarjetas[pid].btn_agregar.click()
        guardar(v, "07_catalogo_con_carrito.png", SALIDA)
        v.panel_carrito.btn_pagar.click()
        d = v.dialogo_pago
        d.input_nombre.setText("María Fernanda Ruiz")
        d.input_documento.setText("1020304050")
        d.input_monto.setText("50000")
        esperar(lambda: d.btn_confirmar.isEnabled(), 5)
        d.show()
        guardar(d, "08_pago.png", SALIDA)
        d.btn_confirmar.click()
        esperar(lambda: v.dialogo_factura is not None, 15)
        fd = v.dialogo_factura
        guardar(fd, "09_factura.png", SALIDA)
        fd.btn_cerrar.click()
        esperar(lambda: False, 0.5)

        # ---- 5. inactividad: el admin pone 30/10 y el comprador (sesion abierta) lo recibe por WS -----
        adm_api.registrar_actividad()
        adm_api.actualizar_config({"inactividad_segundos": 30, "aviso_segundos": 10})
        assert esperar(lambda: comprador.idle.inactividad_segundos == 30, 10)
        t0 = time.monotonic()
        assert esperar(lambda: comprador._dialogo is not None, 40), "no aparecio el aviso"
        print(f"  aviso de inactividad visible a {time.monotonic() - t0:.1f} s del cambio (ultima actividad previa)")
        dlg = comprador._dialogo
        esperar(lambda: dlg.segundos <= 7, 10)
        esperar(lambda: False, 0.3)
        pm = componer_con_dialogo(v, dlg)
        ruta = SALIDA / "10_aviso_inactividad.png"
        pm.save(str(ruta), "PNG")
        print(f"  10_aviso_inactividad.png: {pm.width()}x{pm.height()} (cuenta regresiva en {dlg.texto_cuenta})")
        assert esperar(lambda: comprador.sesion is None, 20), "la sesion no se cerro"
        esperar(lambda: comprador.login.isVisible(), 5)
        assert comprador.login.lbl_aviso.text() == "Sesión cerrada por inactividad"
        guardar(comprador.login, "11_login_sesion_cerrada_por_inactividad.png", SALIDA)
        adm_api.cerrar()
        comp_api.cerrar()
        print("OK ->", SALIDA)
        return 0
    finally:
        for a in apps:
            try:
                if a.sesion is not None:
                    a._cerrando = False
                    a._cerrar_sesion_local("fin", avisar_servidor=False)
                if a.login is not None:
                    a.login.cerrada.disconnect()
                    a.login.close()
            except Exception:  # noqa: BLE001
                pass
        srv.limpiar()
        shutil.rmtree(_CFG, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
