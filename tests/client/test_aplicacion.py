"""Controlador raiz contra el servidor real: login, barra, cierres por inactividad y por servidor."""
import pytest
from PyQt6.QtWidgets import QApplication

from client.application.sesion import Aplicacion, OpcionesCliente
from client.infrastructure.api_client import ApiClient
from client.presentation.views.barra_estado import BarraEstado
from shared.schemas import UsuarioIn, UsuarioUpdate
from tests.client.conftest import ADMIN_PW, COMP_PW, puerto_libre

RAPIDO = OpcionesCliente(throttle_actividad=0.2, tick_ms=100, health_ms=300, sondeo_ms=500,
                         ping_ms=60000, backoff=(0.1, 0.2), solo_espontaneos=False,
                         cierre_logout_ms=200)


@pytest.fixture
def crear_app(qapp, servidor):
    creadas = []

    def _crear(url=None, **kw):
        a = Aplicacion(url or servidor.url, kw.pop("opciones", RAPIDO), timeout=2.0, **kw)
        a.iniciar()
        creadas.append(a)
        return a
    yield _crear
    for a in creadas:
        if a.sesion is not None:
            a._cerrando = False
            a._cerrar_sesion_local("fin", avisar_servidor=False)
        if a.login is not None:
            a.login.cerrada.disconnect()
            a.login.close()
            a.login.deleteLater()
        a.deleteLater()
    QApplication.processEvents()


def entrar(a, espera, usuario="comprador", pw=COMP_PW):
    a.login.input_usuario.setText(usuario)
    a.login.input_password.setText(pw)
    a.login.btn_login.click()
    assert espera(lambda: a.sesion is not None)


def test_login_valida_campos_vacios(crear_app, espera):
    a = crear_app()
    a.login.btn_login.click()
    assert a.login.lbl_error.text() == "Completa todos los campos"
    assert a.sesion is None


def test_login_credenciales_incorrectas(crear_app, espera):
    a = crear_app()
    a.login.input_usuario.setText("comprador")
    a.login.input_password.setText("mala-clave-xx")
    a.login.btn_login.click()
    assert not a.login.btn_login.isEnabled() or a.login.btn_login.text() == "Ingresando…"
    assert espera(lambda: a.login.lbl_error.text() != "")
    assert a.login.lbl_error.text() == "Usuario o contraseña incorrectos"
    assert a.login.btn_login.isEnabled() and a.sesion is None
    assert a.login.input_password.text() == ""


def test_login_servidor_no_disponible(crear_app, espera):
    a = crear_app(f"http://127.0.0.1:{puerto_libre()}")
    a.login.input_usuario.setText("admin")
    a.login.input_password.setText("lo-que-sea")
    a.login.btn_login.click()
    assert espera(lambda: "No se pudo conectar" in a.login.lbl_error.text())
    assert a.login.btn_login.isEnabled()


def test_login_bloqueo_429_muestra_segundos(crear_app, espera):
    a = crear_app()
    for _ in range(6):
        a.login.input_usuario.setText("victima-429")
        a.login.input_password.setText("incorrecta-123")
        a.login.btn_login.click()
        assert espera(lambda: a.login._cargando is False and a.login.lbl_error.text() != "")
        if "Reintenta en" in a.login.lbl_error.text():
            break
        a.login.lbl_error.setText("")
    assert "Reintenta en" in a.login.lbl_error.text()
    assert not a.login.btn_login.isEnabled() and "Reintentar en" in a.login.btn_login.text()
    a.login.restablecer()


def test_probar_servidor(crear_app, espera):
    a = crear_app()
    a.login.input_servidor.setText(a.url)
    a.login._probar()
    assert espera(lambda: "en línea" in a.login.lbl_servidor.text())
    a.login.input_servidor.setText(f"127.0.0.1:{puerto_libre()}")
    a.login._probar()
    assert espera(lambda: "No se pudo conectar" in a.login.lbl_servidor.text())


def test_login_ok_abre_ventana_con_barra_y_guarda_url(crear_app, espera):
    a = crear_app()
    entrar(a, espera)
    assert a.sesion.rol == "comprador" and a.ventana is not None and a.ventana.isVisible()
    assert not a.login.isVisible()
    barra = a.ventana.findChild(BarraEstado)
    assert barra is not None
    assert espera(lambda: barra.conexion.conectado)          # health en vivo
    assert espera(lambda: a.eventos.esta_conectado)
    assert barra.reloj.segundos > 0
    from client.infrastructure.config import cargar_url
    assert cargar_url() == a.url                              # persistida


def test_login_admin(crear_app, espera):
    a = crear_app()
    entrar(a, espera, "admin", ADMIN_PW)
    assert a.sesion.rol == "admin" and a.ventana is not None


def test_cierre_por_inactividad_local_vuelve_al_login(crear_app, espera):
    a = crear_app()
    entrar(a, espera)
    ventana = a.ventana
    a.idle.actualizar_config(2, 1)                 # en caliente: 2 s en total, aviso al final
    assert espera(lambda: a._dialogo is not None, timeout=5)   # aviso con cuenta regresiva
    assert espera(lambda: a.sesion is None, timeout=6)
    assert a.login.isVisible()
    assert a.login.lbl_aviso.text() == "Sesión cerrada por inactividad"
    assert a.login.lbl_aviso.isVisible()
    assert a.idle is None and a.eventos is None and a.api is None and a.ventana is None
    assert a._dialogo is None
    assert not ventana.isVisible()


def test_actividad_evita_la_expiracion_y_cierra_aviso(crear_app, espera):
    a = crear_app()
    entrar(a, espera)
    a.idle.actualizar_config(3, 2)
    assert espera(lambda: a._dialogo is not None, timeout=5)
    a.idle.marcar_actividad_vista()
    assert espera(lambda: a._dialogo is None)
    assert a.sesion is not None
    assert a.idle.restantes() >= 2


def test_continuar_del_dialogo_renueva(crear_app, espera):
    a = crear_app()
    entrar(a, espera)
    a.idle.actualizar_config(3, 2)
    assert espera(lambda: a._dialogo is not None, timeout=5)
    a._dialogo.continuar.emit()
    assert espera(lambda: a._dialogo is None)
    assert a.sesion is not None


def test_logout_manual_llama_al_servidor(crear_app, espera, servidor):
    a = crear_app()
    entrar(a, espera)
    token = a.sesion.token
    a.cerrar_sesion()
    assert a.sesion is None and a.login.isVisible()
    assert a.login.lbl_aviso.text() == "Sesión cerrada"
    probe = ApiClient(servidor.url, token=token)
    from client.infrastructure.api_client import ApiError
    assert espera(lambda: _revocado(probe, ApiError))
    probe.cerrar()


def _revocado(probe, ApiError):
    try:
        probe.estado_sesion()
    except ApiError as e:
        return e.http == 401
    return False


def test_config_cambiada_actualiza_idle_en_caliente(crear_app, espera, api_admin):
    a = crear_app()
    entrar(a, espera)
    original = a.idle.inactividad_segundos
    assert espera(lambda: a.eventos.esta_conectado)
    try:
        api_admin.actualizar_config({"inactividad_segundos": 600, "aviso_segundos": 20})
        assert espera(lambda: a.idle is not None and a.idle.inactividad_segundos == 600)
        assert a.idle.aviso_segundos == 20
    finally:
        api_admin.actualizar_config({"inactividad_segundos": original, "aviso_segundos": 30})


def test_servidor_desactiva_usuario_cierra_sesion_con_motivo(crear_app, espera, api_admin):
    u = api_admin.crear_usuario(UsuarioIn(nombre="Victima", usuario="victima1",
                                          password="clave-victima-1"))
    a = crear_app()
    entrar(a, espera, "victima1", "clave-victima-1")
    assert espera(lambda: a.eventos.esta_conectado)
    api_admin.actualizar_usuario(u.id, UsuarioUpdate(activo=False))
    assert espera(lambda: a.sesion is None, timeout=8)
    assert "desactivado" in a.login.lbl_aviso.text()
    assert a.login.isVisible()


def test_eventos_ws_llegan_a_las_vistas_sin_contar_actividad(crear_app, espera, api_admin):
    a = crear_app()
    entrar(a, espera)
    vistos = []
    a.evento_ws.connect(lambda n, p: vistos.append(n))
    assert espera(lambda: a.eventos.esta_conectado)
    a.idle.actualizar_config(60, 10)
    restantes_antes = a.idle.restantes()
    api_admin.actualizar_config({"nombre_negocio": "Tienda WS"})
    assert espera(lambda: "config_cambiada" in vistos)
    assert a.idle.restantes() <= restantes_antes      # el evento no renovo el tiempo local
    api_admin.actualizar_config({"nombre_negocio": "Tienda"})


def test_cierre_por_servidor_no_deja_warning_de_sesion_cerrada_sin_manejador(
        crear_app, espera, api_admin, caplog):
    import logging
    u = api_admin.crear_usuario(UsuarioIn(nombre="Victima2", usuario="victima2",
                                          password="clave-victima-2"))
    a = crear_app()
    entrar(a, espera, "victima2", "clave-victima-2")
    assert espera(lambda: a.eventos.esta_conectado)
    with caplog.at_level(logging.DEBUG):
        api_admin.actualizar_usuario(u.id, UsuarioUpdate(activo=False))
        assert espera(lambda: a.sesion is None, timeout=8)
        espera(lambda: False, timeout=0.8)           # deja llegar verificaciones en vuelo
    assert not [r for r in caplog.records
                if r.levelno >= logging.WARNING and "sin manejador" in r.getMessage()]


def test_error_inesperado_al_verificar_sesion_si_se_registra(crear_app, espera, caplog):
    import logging
    a = crear_app()
    entrar(a, espera)
    with caplog.at_level(logging.WARNING):
        a._error_verificacion(RuntimeError("boom"))
    assert any("verificar la sesion" in r.getMessage() for r in caplog.records)
