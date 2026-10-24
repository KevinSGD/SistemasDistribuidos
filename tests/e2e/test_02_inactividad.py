"""Escenario 2 (requisito estrella): cierre de sesion por inactividad, con tiempos REALES.

Clientes Windows reales (`Aplicacion` + ventanas, offscreen, opciones de PRODUCCION sin tocar) y una
sonda HTTP viven a la vez contra una instancia WSL propia; toda la linea de tiempo (~1 min) corre UNA
vez, en paralelo, y cada test comprueba un requisito distinto:

  comprador  (B1)  sin actividad                        -> aviso a ~20 s y cierre a ~30 s
  idle2      (B2)  teclado+raton REALES en el aviso     -> el reloj se reinicia
                   (proceso aparte: el filtro de eventos es del QApplication, uno por proceso)
  idle3      (B3)  refresco automatico (WS/sondeo/GET)  -> NO renueva: cierra igual a ~30 s
  idle4      (B4)  pulsa "Seguir conectado" en el aviso -> renueva
  admin      (UI)  cambia 180/30 -> 30/10 en Configuracion > Seguridad de sesion
  sonda            sesion HTTP sin cliente: el servidor responde 401 SESION_INACTIVA

Toda llamada HTTP de la propia prueba (sondeos del servidor, generador de eventos) corre en HILOS
para no bloquear el bucle Qt y no falsear los tiempos medidos en los clientes.
La duracion de la fixture (~1 min) se contabiliza en el setup del primer test."""
from __future__ import annotations

import secrets
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from types import SimpleNamespace

import pytest
from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication, QPushButton

from client.application.mensajes import MENSAJE_INACTIVIDAD
from client.infrastructure.api_client import ApiClient, ApiError
from client.presentation.views.buyer_window import BuyerWindow
from client.presentation.views.main_window import MainWindow
from shared.schemas import ProductoUpdate, UsuarioIn
from tests.e2e.helpers import ClienteExterno, cerrar_app, crear_oferta, entrar, esperar, nueva_app
from tests.e2e.wsl import WslServidor

pytestmark = pytest.mark.e2e

INACT, AVISO = 30, 10          # minimos que admite el servidor (30 s / 5 s)
TOL_AVISO = (19.5, 22.5)       # el aviso debe verse a ~20 s (ticks de 1 s)
TOL_CIERRE = (29.5, 33.0)      # y el cierre a ~30 s


@dataclass
class Sujeto:
    """Mediciones de un cliente. Las horas estan en el reloj de su origen (monotonic o pared)."""
    nombre: str
    app: object = None
    ref: float = 0.0                                   # ultima actividad conocida
    ref_tras_actividad: float | None = None
    token: str = ""
    avisos: list = field(default_factory=list)         # (t_desde_ref, restantes, texto_dialogo)
    cierre_t: float | None = None
    cierre_msg: str = ""
    observ: dict = field(default_factory=dict)

    def ref_vigente(self) -> float:
        return self.ref_tras_actividad if self.ref_tras_actividad is not None else self.ref

    def rel(self, t: float) -> float:
        return t - self.ref


def _registrar(s: Sujeto) -> None:
    """Engancha las senales de una Aplicacion del proceso de pruebas."""
    app = s.app
    s.ref = app.idle._ultima
    s.token = app.sesion.token
    s.eventos_id, s.api_id = id(app.eventos), id(app.api)
    s.conexiones = []
    s.observ["reloj_inicial"] = app.ventana.barra.reloj.segundos
    app.idle.aviso.connect(lambda r, s=s: s.avisos.append(
        (time.monotonic() - s.ref_vigente(), r, app._dialogo.texto_cuenta if app._dialogo else None)))
    app.conexion_cambiada.connect(lambda v, s=s: s.conexiones.append((time.monotonic(), v)))

    def terminada(msg, s=s):
        s.cierre_t, s.cierre_msg = time.monotonic(), msg
    app.sesion_terminada.connect(terminada)


def _ws_aceptados(srv: WslServidor) -> int:
    return int(srv.en_linux(f"grep -c 'WebSocket /ws' {srv.dir}/logs/stdout.log || true").strip() or 0)


class Sondeador:
    """Mide en el SERVIDOR, desde hilos, cuanto le queda a una sesion (GET /auth/sesion no renueva)."""

    def __init__(self, url: str):
        self.url = url
        self.pool = ThreadPoolExecutor(max_workers=6, thread_name_prefix="sonda")
        self.apis: dict[str, ApiClient] = {}

    def preparar(self, token: str) -> None:
        self.apis[token] = ApiClient(self.url, token=token)
        self.apis[token].health()                       # abre la conexion ahora (la nueva cuesta ~0,2 s)

    def pedir(self, token: str):
        api = self.apis[token]

        def tarea():
            t0 = time.monotonic()
            try:
                return t0, time.monotonic(), api.estado_sesion().segundos_restantes
            except ApiError as e:
                return t0, time.monotonic(), (e.http, e.codigo, e.mensaje, e.detalle.get("motivo"))
        return self.pool.submit(tarea)

    def cerrar(self):
        self.pool.shutdown(wait=True, cancel_futures=True)
        for a in self.apis.values():
            a.cerrar()


def _valor(fut):
    """Resultado de una futura de Sondeador: devuelve el segundo elemento util (restantes o error)."""
    return fut.result(timeout=10)[2]


@pytest.fixture(scope="module")
def linea_de_tiempo(qapp, wsl_ok):
    srv = WslServidor("inact").iniciar()
    apps: list = []
    externo = sonda = gen = None
    son = Sondeador(srv.url)
    generador = ThreadPoolExecutor(max_workers=1, thread_name_prefix="gen")   # operaciones del admin
    R = SimpleNamespace(srv=srv, t_inicio=time.monotonic())
    try:
        gen = ApiClient(srv.url)
        gen.login("admin", srv.admin_pw)
        pw = {n: secrets.token_urlsafe(12) for n in ("idle2", "idle3", "idle4", "sonda")}
        for n, p in pw.items():
            gen.crear_usuario(UsuarioIn(nombre=n, usuario=n, password=p))
        producto = crear_oferta(gen, stock=500, precio=10000, nombre="Producto refresco")

        # -- 1. sesiones abiertas con los valores por defecto (180 / 30) ---------------------------
        externo = ClienteExterno(srv.url, "idle2", pw["idle2"])      # B2: otro proceso Windows

        def abrir(nombre, usuario, clave, clase):
            a = nueva_app(srv.url)
            apps.append(a)
            entrar(a, usuario, clave)
            assert isinstance(a.ventana, clase)
            s = Sujeto(nombre, a)
            _registrar(s)
            son.preparar(s.token)
            return s
        b1 = abrir("B1 inactivo", "comprador", srv.comp_pw, BuyerWindow)
        b3 = abrir("B3 refresco automatico", "idle3", pw["idle3"], BuyerWindow)
        b4 = abrir("B4 seguir conectado", "idle4", pw["idle4"], BuyerWindow)
        adm = abrir("Admin (UI)", "admin", srv.admin_pw, MainWindow)
        listo = externo.esperar_evento("listo", 30)
        assert listo is not None, f"B2 no inicio sesion: {externo.stderr}"
        b2 = Sujeto("B2 actividad real", ref=listo["ref"], token=listo["token"])
        b2.observ["reloj_inicial"] = listo["reloj"]
        son.preparar(b2.token)
        sonda = ApiClient(srv.url)
        sonda.login("sonda", pw["sonda"])
        sonda.health()
        t_sonda = time.monotonic()
        locales = [b1, b3, b4]
        R.sujetos = {"b1": b1, "b2": b2, "b3": b3, "b4": b4, "adm": adm}
        R.inicial = {s.nombre: (s.app.idle.inactividad_segundos, s.app.idle.aviso_segundos,
                                s.app.sesion.inactividad_segundos, s.app.sesion.aviso_segundos,
                                s.observ["reloj_inicial"]) for s in locales}
        R.inicial[b2.nombre] = (listo["inactividad"], listo["aviso"], listo["inactividad"],
                                listo["aviso"], listo["reloj"])
        assert esperar(lambda: all(s.app.eventos.esta_conectado for s in locales + [adm]), 15)
        assert esperar(lambda: bool((externo.pedir("estado", "estado", 3) or {}).get("ws")), 15, paso=0.3)
        for s in locales:
            s.conexiones.clear()
        externo.pedir("reset", "reset_ok", 5)
        R.ws_antes = _ws_aceptados(srv)

        # contadores de B3 (refresco automatico)
        c3 = SimpleNamespace(reportes=0, eventos=0, sondeos=0, listados=0, salud=0, muestras=[])
        orig = b3.app.idle._reportar
        b3.app.idle._reportar = lambda: (setattr(c3, "reportes", c3.reportes + 1), orig())[1]
        b3.app.evento_ws.connect(lambda n, p: setattr(c3, "eventos", c3.eventos + 1))
        b3.app.sondeo.connect(lambda: setattr(c3, "sondeos", c3.sondeos + 1))
        b3.app.estado_servidor.connect(lambda *_: setattr(c3, "salud", c3.salud + 1))
        orig_list = b3.app.api.listar_ofertas

        def listar():
            c3.listados += 1
            return orig_list()
        b3.app.api.listar_ofertas = listar
        R.c3 = c3

        # -- 2. el admin cambia 180/30 -> 30/10 DESDE LA UI ---------------------------------------
        adm.app.ventana.ir_a("configuracion")
        cfg = adm.app.ventana.vistas["configuracion"]
        assert esperar(lambda: bool(cfg._base), 10)
        cfg._widgets["inactividad_segundos"].setText(str(INACT))
        cfg._widgets["aviso_segundos"].setText(str(AVISO))
        assert cfg.btn_guardar.isEnabled(), cfg.errores_locales()
        gen.registrar_actividad()
        t_cambio = time.monotonic()
        cfg.btn_guardar.click()
        R.admin_ui_aplicado = esperar(lambda: "Aplicado" in cfg.lbl_vigente.text(), 10)
        R.admin_ui_texto = cfg.lbl_vigente.text()
        R.t_ui_aplicado = time.monotonic() - t_cambio
        gen.registrar_actividad()
        R.config_servidor = gen.obtener_config()
        aplicado: dict[str, float] = {}

        def todos():
            for s in locales:
                i = s.app.idle
                if s.nombre not in aplicado and i is not None and i.inactividad_segundos == INACT:
                    aplicado[s.nombre] = time.monotonic() - t_cambio
            e = externo.pedir("estado", "estado", 3)
            if e and e["inactividad"] == INACT:
                aplicado.setdefault(b2.nombre, time.monotonic() - t_cambio)
            return len(aplicado) == len(locales) + 1
        R.todos_aplicados = esperar(todos, 15, paso=0.2)
        R.aplicado = aplicado
        R.tras_cambio = {s.nombre: (s.app.idle.inactividad_segundos, s.app.idle.aviso_segundos,
                                    s.app.sesion.inactividad_segundos, id(s.app.eventos) == s.eventos_id,
                                    id(s.app.api) == s.api_id, list(s.conexiones)) for s in locales}
        e = externo.pedir("estado", "estado", 5)
        R.tras_cambio[b2.nombre] = (e["inactividad"], e["aviso"], e["sesion_inactividad"],
                                    e["mismo_ws"], e["mismo_api"], e["conexiones"])
        R.ws_despues = _ws_aceptados(srv)

        # -- 3. guion: el tiempo corre ------------------------------------------------------------
        ahora = time.monotonic()
        prox = {"stock": ahora + 2, "sondeo": ahora + 3, "cargar": ahora + 4, "muestra": ahora + 2,
                "cfg": ahora + 8}
        stock_n = [499]
        sonda_res: dict = {}
        futuros_b3: list = []

        def generar(fn):
            def _t():
                try:
                    gen.registrar_actividad()
                    fn()
                except Exception as ex:      # noqa: BLE001
                    R.errores_gen = getattr(R, "errores_gen", []) + [repr(ex)]
            generador.submit(_t)

        def programar_contraste(s: Sujeto):
            s.observ["srv_en"] = [time.monotonic() + d for d in (0.5, 1.5, 3.0)]
            s.observ["srv_fut"] = []

        # B4: al aparecer el aviso, 1 s despues el usuario pulsa "Seguir conectado"
        def pulsar_seguir():
            app = b4.app
            if app.sesion is None or app._dialogo is None:
                return
            b4.observ["dialogo_visible_antes"] = True
            b4.observ["restantes_antes"] = app.idle.restantes()
            app._dialogo.findChild(QPushButton).click()
            b4.ref_tras_actividad = app.idle._ultima
            b4.observ["dialogo_cerrado"] = esperar(lambda: app._dialogo is None, 2)
            b4.observ["restantes_despues"] = app.idle.restantes()
            b4.observ["reloj_despues"] = app.ventana.barra.reloj.segundos
            programar_contraste(b4)
        armado = {"b4": False}

        def al_aviso_b4(_r):
            if not armado["b4"]:
                armado["b4"] = True
                QTimer.singleShot(1000, pulsar_seguir)
        b4.app.idle.aviso.connect(al_aviso_b4)

        fin = time.monotonic() + 100
        b2_armado = None
        while time.monotonic() < fin:
            QApplication.processEvents()
            time.sleep(0.01)
            ahora = time.monotonic()
            # ---- B3: refresco automatico (servidor -> WS, sondeo local, GET silencioso)
            if b3.app.sesion is not None:
                if ahora >= prox["stock"]:
                    prox["stock"] = ahora + 3
                    stock_n[0] -= 1
                    n = stock_n[0]
                    generar(lambda n=n: gen.actualizar_producto(producto.id, ProductoUpdate(stock=n)))
                if ahora >= prox["cfg"]:
                    prox["cfg"] = ahora + 1000
                    generar(lambda: gen.actualizar_config({"nombre_negocio": "Tienda E2E refresco"}))
                if ahora >= prox["sondeo"]:
                    prox["sondeo"] = ahora + 5
                    b3.app.sondeo.emit()
                if ahora >= prox["cargar"]:
                    prox["cargar"] = ahora + 4
                    b3.app.ventana.cargar(silencioso=True)
                if ahora >= prox["muestra"]:
                    prox["muestra"] = ahora + 4
                    futuros_b3.append((ahora - b3.ref, son.pedir(b3.token), b3.app.idle.restantes()))
            # ---- B2 (proceso aparte): a 1 s de aparecer el aviso, el usuario toca teclado y raton
            if b2_armado is None and b2.ref_tras_actividad is None:
                av = externo.ultimo("aviso")
                if av is not None:
                    b2_armado = av["t"] + 1.0
            if b2_armado is not None and b2_armado > 0 and time.time() >= b2_armado:
                b2_armado = -1
                h = externo.pedir("actividad", "actividad_hecha", 10)
                b2.observ.update(h)
                b2.observ["reloj_despues"] = h["reloj"]
                b2.observ["dialogo_cerrado"] = h["dialogo_cerrado"]
                b2.ref_tras_actividad = h["ref"]
                programar_contraste(b2)
            # ---- contraste en el SERVIDOR despues de la accion de B2 y B4
            for s in (b2, b4):
                for t_s in list(s.observ.get("srv_en", [])):
                    if ahora >= t_s:
                        s.observ["srv_en"].remove(t_s)
                        s.observ["srv_fut"].append(son.pedir(s.token))
            # ---- sonda: viva a los 25 s (sin renovar), 401 SESION_INACTIVA pasados 31,5 s
            if "vivo" not in sonda_res and ahora - t_sonda >= 25:
                sonda_res["vivo"] = son.pool.submit(lambda: sonda.estado_sesion().segundos_restantes)
            if "caducada" not in sonda_res and ahora - t_sonda >= INACT + 1.5:
                def _cad():
                    try:
                        sonda.estado_sesion()
                        return "sin error"
                    except ApiError as ex:
                        return (ex.http, ex.codigo, ex.mensaje)
                sonda_res["caducada"] = son.pool.submit(_cad)
            term = externo.ultimo("terminada")
            if term is not None and b2.cierre_t is None:
                b2.cierre_t, b2.cierre_msg = term["t"], term["mensaje"]
            if (all(s.app.sesion is None for s in locales + [adm]) and b2.cierre_t is not None
                    and len(sonda_res) == 2):
                break
        generador.shutdown(wait=True)
        R.duracion_guion = time.monotonic() - t_cambio
        R.sonda = {}
        for k, f in sonda_res.items():
            try:
                R.sonda[k] = f.result(timeout=10)
            except ApiError as ex:
                R.sonda[k] = (ex.http, ex.codigo)
        for s in (b2, b4):
            s.observ["srv"] = [_valor(f) for f in s.observ.get("srv_fut", [])]
        c3.muestras = [(t, _valor(f), loc) for t, f, loc in futuros_b3]
        # avisos de B2 (proceso aparte), medidos desde su ultima actividad vigente en ese instante
        ref = b2.ref
        for ev in externo.eventos:
            if ev["ev"] == "actividad_hecha":
                ref = ev["ref"]
            elif ev["ev"] == "aviso":
                b2.avisos.append((ev["t"] - ref, ev["restantes"], ev["dialogo"]))
        lg = externo.pedir("login", "login", 5)
        R.final = {s.nombre: (s.app.sesion is None, s.cierre_msg, s.app.login.lbl_aviso.text(),
                              s.app.login.lbl_aviso.isVisible(), s.app.login.isVisible(),
                              s.app.ventana is None) for s in locales + [adm]}
        R.final[b2.nombre] = (b2.cierre_t is not None, b2.cierre_msg, lg["aviso"], lg["aviso_visible"],
                              lg["visible"], True)
        # el servidor rechaza el token de todo cliente que cerro por inactividad
        for k, s in R.sujetos.items():
            r = _valor(son.pedir(s.token))
            s.observ["token_final"] = r if isinstance(r, tuple) else ("sin error", r)
        R.t_total = time.monotonic() - R.t_inicio
        yield R
    finally:
        generador.shutdown(wait=False, cancel_futures=True)
        if externo is not None:
            externo.cerrar()
        for a in apps:
            cerrar_app(a)
        son.cerrar()
        for c in (sonda, gen):
            if c is not None:
                c.cerrar()
        srv.limpiar()


# ============================================================================================
# a) inicio de sesion con los valores por defecto
# ============================================================================================
def test_a_comprador_inicia_con_180_30_por_defecto(linea_de_tiempo):
    R = linea_de_tiempo
    for nombre, (i, a, si, sa, reloj) in R.inicial.items():
        assert (i, a, si, sa) == (180, 30, 180, 30), nombre
        assert 175 <= reloj <= 180, (nombre, reloj)       # barra: "Sesion: 02:5x/03:00"
    print(f"\n[a] sesiones abiertas con 180/30 (inact, aviso, sesion.inact, sesion.aviso, reloj): {R.inicial}")


# ============================================================================================
# b) el admin cambia a 30/10 desde la UI (Configuracion > Seguridad de sesion)
# ============================================================================================
def test_b_admin_cambia_a_30_10_por_la_ui(linea_de_tiempo):
    R = linea_de_tiempo
    assert R.admin_ui_aplicado, R.admin_ui_texto
    assert R.admin_ui_texto.startswith("✓ Aplicado a tu sesión actual")
    assert (R.config_servidor.inactividad_segundos, R.config_servidor.aviso_segundos) == (INACT, AVISO)
    print(f"\n[b] UI admin: '{R.admin_ui_texto}' en {R.t_ui_aplicado:.2f} s; servidor: "
          f"{R.config_servidor.inactividad_segundos}/{R.config_servidor.aviso_segundos}")


# ============================================================================================
# c) la sesion YA ABIERTA recibe el cambio por WebSocket, sin reconectar
# ============================================================================================
def test_c_cambio_llega_a_sesiones_abiertas_sin_reconectar(linea_de_tiempo):
    R = linea_de_tiempo
    assert R.todos_aplicados, R.aplicado
    for nombre, (i, a, si, mismo_ws, mismo_api, conex) in R.tras_cambio.items():
        assert (i, a, si) == (INACT, AVISO, INACT), nombre   # IdleMonitor y SesionUsuario actualizados
        assert mismo_ws and mismo_api, nombre                # mismo EventClient y mismo ApiClient/token
        assert conex == [], f"{nombre} reconecto el WebSocket: {conex}"
    assert R.ws_despues == R.ws_antes                        # el servidor no vio sockets nuevos
    assert max(R.aplicado.values()) < 5                      # llega en segundos
    print("\n[c] latencia de aplicacion tras pulsar Guardar: "
          + ", ".join(f"{k}={v:.2f}s" for k, v in R.aplicado.items())
          + f"; sockets WS aceptados por el servidor antes/despues: {R.ws_antes}/{R.ws_despues}")


# ============================================================================================
# d) sin actividad: aviso a ~20 s con cuenta regresiva, cierre a ~30 s, 401 con ese token
# ============================================================================================
def test_d_sin_actividad_aviso_a_20s_y_cierre_a_30s(linea_de_tiempo):
    R = linea_de_tiempo
    b1 = R.sujetos["b1"]
    assert b1.avisos, "nunca aparecio el aviso"
    primer = b1.avisos[0]
    assert TOL_AVISO[0] <= primer[0] <= TOL_AVISO[1], primer  # DialogoInactividad a ~20 s
    cuenta = [r for _, r, _ in b1.avisos]
    assert cuenta[0] in (AVISO, AVISO - 1) and cuenta == sorted(cuenta, reverse=True) and cuenta[-1] <= 1
    assert all(txt == str(r) for _, r, txt in b1.avisos), b1.avisos   # el dialogo muestra la cuenta
    cierre = b1.rel(b1.cierre_t)
    assert TOL_CIERRE[0] <= cierre <= TOL_CIERRE[1], cierre   # cierre a ~30 s de la ultima actividad
    cerrada, msg, aviso_login, visible, login_visible, sin_ventana = R.final[b1.nombre]
    assert cerrada and sin_ventana and login_visible and visible
    assert aviso_login == MENSAJE_INACTIVIDAD == "Sesión cerrada por inactividad"
    # Al expirar, el cliente hace logout; ese primer contacto ya cierra la sesion en el servidor por
    # inactividad, asi que luego el token figura SESION_CERRADA (motivo inactividad). La primera
    # comprobacion de una sesion SIN cliente (la sonda) devuelve SESION_INACTIVA.
    http, codigo, _msg, motivo = b1.observ["token_final"]
    assert http == 401 and codigo in ("SESION_INACTIVA", "SESION_CERRADA")
    if codigo == "SESION_CERRADA":
        assert motivo == "inactividad"
    assert isinstance(R.sonda["vivo"], int) and R.sonda["vivo"] <= 6   # a los 25 s: viva, sin renovar
    assert R.sonda["caducada"][:2] == (401, "SESION_INACTIVA"), R.sonda
    print(f"\n[d] B1: aviso a {primer[0]:.2f} s, cuenta regresiva {cuenta}, cierre a {cierre:.2f} s, "
          f"login muestra '{aviso_login}'; token de B1 -> {b1.observ['token_final']}; "
          f"sonda a los 25 s: {R.sonda['vivo']} s restantes; a los 31,5 s: {R.sonda['caducada']}")


# ============================================================================================
# e) actividad REAL (teclado + clic de Qt en la ventana) renueva y reinicia el reloj
# ============================================================================================
def test_e_actividad_real_renueva_la_sesion(linea_de_tiempo):
    R = linea_de_tiempo
    b2 = R.sujetos["b2"]
    o = b2.observ
    assert o["dialogo_visible_antes"], "la actividad debia ocurrir con el aviso a la vista (~21 s)"
    assert o["restantes_antes"] <= AVISO                    # estaba por cerrarse...
    assert o["dialogo_cerrado"]                             # ...la actividad cerro el aviso
    assert o["restantes_despues"] >= 29 and o["reloj_despues"] >= 29   # el reloj se reinicio a ~30
    srv15 = o["srv"][1]                                     # el SERVIDOR (1,5 s despues) tambien lo sabe
    assert isinstance(srv15, int) and srv15 >= 26, o["srv"]
    # sigue viva pasada la hora original de cierre y cierra a ~30 s de LA NUEVA actividad
    assert b2.ref_tras_actividad - b2.ref > 19
    assert b2.cierre_t - b2.ref > 40
    nuevo = b2.cierre_t - b2.ref_tras_actividad
    assert TOL_CIERRE[0] <= nuevo <= TOL_CIERRE[1], nuevo
    print(f"\n[e] B2 (proceso aparte): actividad real a {b2.ref_tras_actividad - b2.ref:.1f} s del login "
          f"(aviso visible, {o['restantes_antes']} s restantes) -> reloj {o['reloj_despues']} s; servidor "
          f"a +0,5/+1,5/+3 s: {o['srv']}; cierre natural {nuevo:.1f} s despues de la actividad "
          f"({b2.cierre_t - b2.ref:.1f} s tras el login)")


# ============================================================================================
# f) el refresco automatico (WS / sondeo / GET silencioso / health) NO renueva la sesion
# ============================================================================================
def test_f_refresco_automatico_no_renueva(linea_de_tiempo):
    R = linea_de_tiempo
    b3, c3 = R.sujetos["b3"], R.c3
    assert c3.eventos >= 3 and c3.sondeos >= 2 and c3.listados >= 3 and c3.salud >= 1, vars(c3)
    assert c3.reportes == 0                                  # el cliente nunca llamo a /auth/actividad
    restantes = [m[1] for m in c3.muestras if isinstance(m[1], int)]
    assert len(restantes) >= 4
    assert all(b <= a for a, b in zip(restantes, restantes[1:])), restantes   # el servidor solo descuenta
    assert TOL_CIERRE[0] <= b3.rel(b3.cierre_t) <= TOL_CIERRE[1]   # cerro igual a ~30 s
    assert R.final[b3.nombre][2] == MENSAJE_INACTIVIDAD
    print(f"\n[f] B3: {c3.eventos} eventos WS, {c3.sondeos} sondeos, {c3.listados} recargas de catalogo, "
          f"{c3.salud} health; renovaciones enviadas: {c3.reportes}; segundos restantes en el servidor: "
          f"{restantes}; cierre a {b3.rel(b3.cierre_t):.2f} s")


# ============================================================================================
# g) "Seguir conectado" en el aviso renueva
# ============================================================================================
def test_g_seguir_conectado_renueva(linea_de_tiempo):
    R = linea_de_tiempo
    b4 = R.sujetos["b4"]
    o = b4.observ
    assert o["dialogo_visible_antes"] and o["dialogo_cerrado"]
    assert o["restantes_despues"] >= 29
    srv15 = o["srv"][1]
    assert isinstance(srv15, int) and srv15 >= 26, o["srv"]
    assert b4.cierre_t - b4.ref > 40                         # sobrevivio a los 30 s originales
    nuevo = b4.cierre_t - b4.ref_tras_actividad
    assert TOL_CIERRE[0] <= nuevo <= TOL_CIERRE[1], nuevo
    print(f"\n[g] B4: 'Seguir conectado' a {b4.ref_tras_actividad - b4.ref:.1f} s del login -> servidor "
          f"{o['srv']} s, cierre natural a {nuevo:.1f} s del clic")


# ============================================================================================
# h) el admin (UI) tambien queda sujeto a la nueva politica
# ============================================================================================
def test_h_la_sesion_del_admin_tambien_cierra_con_el_nuevo_tiempo(linea_de_tiempo):
    R = linea_de_tiempo
    adm = R.sujetos["adm"]
    assert R.final[adm.nombre][0] and R.final[adm.nombre][2] == MENSAJE_INACTIVIDAD
    print(f"\n[h] admin cerrado por inactividad {adm.cierre_t - adm.ref:.1f} s tras su login; "
          f"guion completo {R.duracion_guion:.1f} s; fixture total {R.t_total:.1f} s")
