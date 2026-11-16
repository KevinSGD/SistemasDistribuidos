"""Capturas REALES (plataforma Windows) de los componentes de seguridad, como evidencia del informe.
NO es un test de pytest.

    .venv\\Scripts\\python.exe -m tests.e2e.capturas_seguridad [directorio_salida]

Levanta un servidor aislado en WSL2 y recorre: login con error generico (usuario inexistente y clave
incorrecta con el MISMO mensaje), bloqueo temporal, sesion cerrada por desactivacion y por cambio de
clave, vista de comprador (sin funciones administrativas), Seguridad de sesion, Usuarios, Facturas (solo
consulta), validacion de pago, aviso y cierre por inactividad y servidor desconectado."""
from __future__ import annotations

import shutil
import sys
import time
from pathlib import Path

from tests.e2e import capturas as base
from tests.e2e.capturas import RAIZ, componer_con_dialogo, guardar, sembrar
from tests.e2e.helpers import entrar, esperar
from tests.e2e.wsl import WslServidor

from PyQt6.QtWidgets import QApplication                                  # noqa: E402

from client.application.sesion import Aplicacion, OpcionesCliente          # noqa: E402
from client.infrastructure.api_client import ApiClient                    # noqa: E402
from client.presentation.styles.theme import aplicar_tema                 # noqa: E402
from shared.schemas import UsuarioIn, UsuarioUpdate                       # noqa: E402

SALIDA = Path(sys.argv[1]) if len(sys.argv) > 1 else RAIZ / "docs" / "capturas" / "seguridad"


def intentar(app: Aplicacion, usuario: str, clave: str) -> str:
    """Un intento de login por la UI; devuelve el texto de error mostrado."""
    app.login.input_usuario.setText(usuario)
    app.login.input_password.setText(clave)
    app.login.lbl_error.setText("")
    app.login.btn_login.click()
    esperar(lambda: bool(app.login.lbl_error.text()), 10)
    esperar(lambda: False, 0.3)
    return app.login.lbl_error.text()


def main() -> int:
    SALIDA.mkdir(parents=True, exist_ok=True)
    for viejo in SALIDA.glob("*.png"):
        viejo.unlink()
    qapp = QApplication(["capturas_seguridad"])
    qapp.setStyle("Fusion")
    aplicar_tema(qapp)
    srv = WslServidor("capseg").iniciar()
    apps: list[Aplicacion] = []
    try:
        adm_api = ApiClient(srv.url)
        adm_api.login("admin", srv.admin_pw)
        comp_api = ApiClient(srv.url)
        comp_api.login("comprador", srv.comp_pw)
        sembrar(adm_api, comp_api)
        for nombre, usuario in (("Usuario Bloqueo", "bloqueo"), ("Usuario Desactivar", "desactivar"),
                                ("Usuario Clave", "cambioclave")):
            adm_api.crear_usuario(UsuarioIn(nombre=nombre, usuario=usuario, password="clave-demo-1234"))

        # ---- 12 y 13: mensaje generico (usuario inexistente vs clave incorrecta) ------------------
        a = Aplicacion(srv.url, OpcionesCliente(), timeout=8.0)
        apps.append(a)
        a.iniciar()
        m1 = intentar(a, "usuario_que_no_existe", "cualquiera123")
        guardar(a.login, "01_login_usuario_inexistente.png", SALIDA)
        m2 = intentar(a, "comprador", "clave-incorrecta")
        guardar(a.login, "02_login_clave_incorrecta_mismo_mensaje.png", SALIDA)
        print("  mensajes:", repr(m1), "|", repr(m2), "| iguales:", m1 == m2)

        # ---- bloqueo temporal tras fallos consecutivos --------------------------------------------
        for i in range(8):
            m = intentar(a, "bloqueo", "mala-clave")
            if "Reintentar" in a.login.btn_login.text() or "intentos" in m.lower():
                break
        guardar(a.login, "03_login_bloqueo_temporal.png", SALIDA)
        print("  bloqueo:", repr(a.login.lbl_error.text()), repr(a.login.btn_login.text()))

        # ---- sesion cerrada por desactivacion y por cambio de clave --------------------------------
        for usuario, accion, nombre in (
                ("desactivar", lambda uid: UsuarioUpdate(activo=False), "04_sesion_cerrada_usuario_desactivado.png"),
                ("cambioclave", lambda uid: UsuarioUpdate(password="otra-clave-5678"),
                 "05_sesion_cerrada_clave_cambiada.png")):
            b = Aplicacion(srv.url, OpcionesCliente(), timeout=8.0)
            apps.append(b)
            b.iniciar()
            entrar(b, usuario, "clave-demo-1234")
            esperar(lambda: b.eventos.esta_conectado, 10)
            uid = next(u.id for u in adm_api.listar_usuarios() if u.usuario == usuario)
            adm_api.actualizar_usuario(uid, accion(uid))
            assert esperar(lambda: b.sesion is None, 20), f"la sesion de {usuario} no se cerro"
            esperar(lambda: b.login.isVisible(), 5)
            print("  ", usuario, "->", repr(b.login.lbl_aviso.text()))
            guardar(b.login, nombre, SALIDA)

        # ---- comprador: solo catalogo/carrito (sin menu administrativo) ----------------------------
        comprador = Aplicacion(srv.url, OpcionesCliente(), timeout=8.0)
        apps.append(comprador)
        comprador.iniciar()
        entrar(comprador, "comprador", srv.comp_pw)
        v = comprador.ventana
        esperar(lambda: v.estado == "lista" and len(v.tarjetas) >= 8, 15)
        guardar(v, "06_rol_comprador_sin_funciones_admin.png", SALIDA)

        # ---- validacion de pago: datos incompletos no permiten confirmar --------------------------
        pid = list(v.tarjetas)[0]
        v.tarjetas[pid].btn_agregar.click()
        v.panel_carrito.btn_pagar.click()
        d = v.dialogo_pago
        d.input_nombre.setText("Ma")
        d.input_documento.setText("12")
        d.input_monto.setText("1")
        esperar(lambda: False, 0.5)
        d.show()
        print("  confirmar habilitado con datos invalidos:", d.btn_confirmar.isEnabled())
        guardar(d, "07_validacion_pago_datos_invalidos.png", SALIDA)
        d.reject()
        esperar(lambda: False, 0.3)

        # ---- admin: seguridad de sesion, usuarios, facturas (solo consulta) -------------------------
        admin = Aplicacion(srv.url, OpcionesCliente(), timeout=8.0)
        apps.append(admin)
        admin.iniciar()
        entrar(admin, "admin", srv.admin_pw)
        w = admin.ventana
        esperar(lambda: w.vistas["dashboard"].cargada, 10)
        w.ir_a("configuracion")
        esperar(lambda: w.vistas["configuracion"].cargada and bool(w.vistas["configuracion"]._base), 10)
        guardar(w, "08_admin_seguridad_de_sesion.png", SALIDA)
        w.ir_a("usuarios")
        esperar(lambda: w.vistas["usuarios"].cargada, 10)
        guardar(w, "09_admin_usuarios_estado_activo.png", SALIDA)
        w.ir_a("facturas")
        esperar(lambda: w.vistas["facturas"].cargada, 10)
        guardar(w, "10_admin_facturas_solo_consulta.png", SALIDA)
        admin.cerrar_sesion()
        esperar(lambda: admin.sesion is None, 10)
        admin.login.hide()

        # ---- inactividad: cambio en caliente, aviso con cuenta regresiva y cierre ------------------
        adm_api.registrar_actividad()
        adm_api.actualizar_config({"inactividad_segundos": 30, "aviso_segundos": 10})
        assert esperar(lambda: comprador.idle.inactividad_segundos == 30, 10)
        assert esperar(lambda: comprador._dialogo is not None, 40), "no aparecio el aviso"
        dlg = comprador._dialogo
        esperar(lambda: dlg.segundos <= 7, 10)
        pm = componer_con_dialogo(v, dlg)
        pm.save(str(SALIDA / "11_aviso_de_inactividad_cuenta_regresiva.png"), "PNG")
        print("  11_aviso_de_inactividad:", pm.width(), "x", pm.height())
        assert esperar(lambda: comprador.sesion is None, 20), "la sesion no se cerro"
        esperar(lambda: comprador.login.isVisible(), 5)
        guardar(comprador.login, "12_sesion_cerrada_por_inactividad.png", SALIDA)
        adm_api.actualizar_config({"inactividad_segundos": 900, "aviso_segundos": 30})

        # ---- servidor caido: indicador rojo, ventana sin bloquearse ---------------------------------
        c2 = Aplicacion(srv.url, OpcionesCliente(), timeout=4.0)
        apps.append(c2)
        c2.iniciar()
        entrar(c2, "comprador", srv.comp_pw)
        esperar(lambda: c2.ventana.estado == "lista", 15)
        srv.detener()
        esperar(lambda: False, 14)
        guardar(c2.ventana, "13_servidor_desconectado.png", SALIDA)
        adm_api.cerrar()
        comp_api.cerrar()
        print("OK ->", SALIDA)
        return 0
    finally:
        for x in apps:
            try:
                if x.sesion is not None:
                    x._cerrando = False
                    x._cerrar_sesion_local("fin", avisar_servidor=False)
                if x.login is not None:
                    x.login.cerrada.disconnect()
                    x.login.close()
            except Exception:  # noqa: BLE001
                pass
        srv.limpiar()
        shutil.rmtree(base._CFG, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
