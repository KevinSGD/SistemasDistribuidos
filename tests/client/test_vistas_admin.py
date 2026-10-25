"""Vistas del administrador (MainWindow y sus pantallas) contra el servidor real, en offscreen."""
from __future__ import annotations

import threading
import uuid
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from PyQt6.QtCore import QDate
from PyQt6.QtWidgets import QApplication, QMessageBox

from client.application.sesion import Aplicacion, OpcionesCliente
from client.infrastructure.api_client import ApiClient, ApiError, ErrorConexion
from client.presentation.views import _comunes as comunes
from client.presentation.views import inventory_view as inv_mod
from client.presentation.views.config_view import DEFECTOS, duracion, vista_previa
from client.presentation.views.main_window import MainWindow, VISTAS, texto_retirados
from client.presentation.widgets import Toast
from shared.schemas import ProductoIn, ResumenRiesgoOut
from tests.client.conftest import ADMIN_PW

RAPIDO = OpcionesCliente(throttle_actividad=0.2, tick_ms=100, health_ms=500, sondeo_ms=60000,
                         ping_ms=60000, backoff=(0.1, 0.2), solo_espontaneos=False,
                         cierre_logout_ms=200)


@pytest.fixture
def app_admin(qapp, servidor, espera):
    a = Aplicacion(servidor.url, RAPIDO, timeout=4.0)
    a.iniciar()
    a.login.input_usuario.setText("admin")
    a.login.input_password.setText(ADMIN_PW)
    a.login.btn_login.click()
    assert espera(lambda: a.sesion is not None and isinstance(a.ventana, MainWindow))
    yield a
    if a.sesion is not None:
        a._cerrando = False
        a._cerrar_sesion_local("fin", avisar_servidor=False)
    if a.login is not None:
        a.login.cerrada.disconnect()
        a.login.close()
        a.login.deleteLater()
    a.deleteLater()
    QApplication.processEvents()


@pytest.fixture
def win(app_admin, espera):
    w = app_admin.ventana
    assert espera(lambda: w.vistas["dashboard"].cargada)
    return w


@pytest.fixture
def confirma(monkeypatch):
    """Sustituye el dialogo de confirmacion; devuelve el registro y permite fijar la respuesta."""
    estado = {"respuesta": True, "llamadas": []}

    def falsa(parent, titulo, texto, aceptar="Confirmar", peligro=False):
        estado["llamadas"].append((titulo, texto, aceptar))
        return estado["respuesta"]
    monkeypatch.setattr(comunes, "confirmar", falsa)
    return estado


@pytest.fixture
def productos(api_admin):
    """Tres productos de ejemplo con nombre unico; se dan de baja al terminar."""
    sufijo = uuid.uuid4().hex[:6]
    manana = datetime.now() + timedelta(days=1)
    datos = [
        ProductoIn(nombre=f"Yogur {sufijo}", categoria="Lácteos", precio_base=4500, stock=20,
                   stock_maximo=100, fecha_vencimiento=manana),
        ProductoIn(nombre=f"Arroz {sufijo}", categoria="Granos", precio_base=3200, stock=2,
                   stock_maximo=100),
        ProductoIn(nombre=f"Aceite {sufijo}", categoria="Despensa", precio_base=15900, stock=50,
                   stock_maximo=100),
    ]
    creados = [api_admin.crear_producto(d) for d in datos]
    yield creados, sufijo
    for p in creados:
        try:
            api_admin.eliminar_producto(p.id)
        except ApiError:
            pass


def ir(win, espera, clave):
    win.botones[clave].click()
    v = win.vistas[clave]
    assert espera(lambda: v.cargada), f"la vista {clave} no cargó"
    return v


def filas_inventario(v):
    return {v.tabla.texto(r, 1): r for r in range(v.tabla.rowCount())}


# ---------------------------------------------------------------------------------------------
# MainWindow
# ---------------------------------------------------------------------------------------------
def test_mainwindow_navega_por_todas_las_vistas(win, espera):
    assert win.windowTitle().endswith("Administrador")
    assert [b for b in win.botones] == [k for k, _e, _c in VISTAS]
    assert win.barra.btn_salir.text() == "Cerrar sesión"
    for i, (clave, etiqueta, _cls) in enumerate(VISTAS):
        assert win.botones[clave].text() == etiqueta
        v = ir(win, espera, clave)
        assert win.contenido.currentIndex() == i and win.vista_actual() == clave
        assert win.contenido.currentWidget() is v
        assert win.botones[clave].property("activo") is True
        otros = [b for k, b in win.botones.items() if k != clave]
        assert all(b.property("activo") is False for b in otros)


def test_cambiar_de_vista_marca_actividad_y_el_refresco_no(win, app_admin, espera, monkeypatch):
    marcas = []
    monkeypatch.setattr(app_admin, "marcar_actividad_vista", lambda: marcas.append(1))
    registros = []
    original = app_admin.api.registrar_actividad
    monkeypatch.setattr(app_admin.api, "registrar_actividad",
                        lambda: (registros.append(1), original())[1])
    win.botones["inventario"].click()
    win.botones["alertas"].click()
    assert len(marcas) == 2
    # eventos del servidor y sondeo refrescan datos pero NO cuentan como actividad
    llamadas = []
    orig = app_admin.api.alertas_riesgo
    monkeypatch.setattr(app_admin.api, "alertas_riesgo", lambda: (llamadas.append(1), orig())[1])
    app_admin.evento_ws.emit("stock_actualizado", {"producto_id": 1, "stock": 3})
    app_admin.sondeo.emit()
    assert espera(lambda: len(llamadas) >= 1)
    assert len(marcas) == 2 and registros == []


def test_evento_refresca_vistas_visibles_y_cargadas(win, app_admin, espera, monkeypatch):
    ir(win, espera, "inventario")
    ir(win, espera, "dashboard")
    cuentas = {"prod": 0, "res": 0}
    o1, o2 = app_admin.api.listar_productos, app_admin.api.resumen_riesgo
    monkeypatch.setattr(app_admin.api, "listar_productos",
                        lambda *a, **k: (cuentas.__setitem__("prod", cuentas["prod"] + 1), o1(*a, **k))[1])
    monkeypatch.setattr(app_admin.api, "resumen_riesgo",
                        lambda: (cuentas.__setitem__("res", cuentas["res"] + 1), o2())[1])
    app_admin.evento_ws.emit("descuento_cambiado", {"producto_id": 1, "porcentaje": 10, "motivo": "x"})
    assert espera(lambda: cuentas["prod"] >= 1 and cuentas["res"] >= 1)


def test_productos_retirados_muestra_toast_no_modal(win, app_admin, espera, monkeypatch):
    def prohibido(*a, **k):
        raise AssertionError("no debe abrirse un QMessageBox")
    monkeypatch.setattr(QMessageBox, "exec", prohibido)
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(prohibido))
    monkeypatch.setattr(QMessageBox, "information", staticmethod(prohibido))
    llamadas = []
    o = app_admin.api.listar_productos
    ir(win, espera, "inventario")
    monkeypatch.setattr(app_admin.api, "listar_productos", lambda *a, **k: (llamadas.append(1), o(*a, **k))[1])

    app_admin.evento_ws.emit("productos_retirados", {"nombres": ["Leche entera", "Pan tajado"]})
    toasts = Toast.activos(win)
    assert toasts, "debe mostrarse un Toast"
    t = toasts[-1]
    assert "Leche entera" in t.text() and "Pan tajado" in t.text() and t.tipo == "aviso"
    assert QApplication.activeModalWidget() is None
    assert win.isEnabled()
    assert espera(lambda: len(llamadas) >= 1)         # refresca el inventario
    t.cerrar()


def test_texto_retirados_resume_listas_largas():
    assert "Pan" in texto_retirados(["Pan"])
    largo = texto_retirados([f"P{i}" for i in range(8)])
    assert "8 productos" in largo and "y 3 más" in largo
    assert texto_retirados([])


def test_cerrar_sesion_pide_confirmacion(win, app_admin, espera, confirma):
    confirma["respuesta"] = False
    win.barra.btn_salir.click()
    assert confirma["llamadas"] and app_admin.sesion is not None
    confirma["respuesta"] = True
    win.barra.btn_salir.click()
    assert app_admin.sesion is None and app_admin.login.isVisible()
    assert len(confirma["llamadas"]) == 2


# ---------------------------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------------------------
def test_dashboard_con_datos(win, app_admin, espera, productos, api_admin):
    creados, sufijo = productos
    d = win.vistas["dashboard"]
    d.recargar()
    esperado = api_admin.resumen_riesgo()
    assert espera(lambda: d.tarjeta_total.valor == str(esperado.total_activos))
    assert d.tarjeta_criticos.valor == str(esperado.conteos["critico"])
    assert d.tarjeta_altos.valor == str(esperado.conteos["alto"])
    assert d.tarjeta_medios.valor == str(esperado.conteos["medio"])
    assert d.tarjeta_criticos.color_valor == "#DC2626"
    nombres = [f.lbl_nombre.text() for f in d.filas()]
    assert f"Yogur {sufijo}" in nombres                 # vence mañana -> crítico
    fila = d.filas()[nombres.index(f"Yogur {sufijo}")]
    assert fila.badge.nivel == "critico" and fila.item.descuento > 0
    assert fila.lbl_desc.text().startswith("-") and fila.lbl_desc.text().endswith("%")
    assert "<s>" in fila.lbl_original.text()
    assert fila.lbl_final.text().startswith("$")
    assert d.pagina == 0


def test_dashboard_vacio_y_error_con_reintento(win, app_admin, espera, monkeypatch):
    d = win.vistas["dashboard"]
    vacio = ResumenRiesgoOut(total_activos=4, conteos={"critico": 0, "alto": 0, "medio": 0, "normal": 4},
                             atencion=[], con_descuento=0)
    monkeypatch.setattr(app_admin.api, "resumen_riesgo", lambda: vacio)
    d.recargar()
    assert espera(lambda: d.pagina == 1 and d.tarjeta_total.valor == "4")

    def caido():
        raise ErrorConexion("sin red")
    monkeypatch.setattr(app_admin.api, "resumen_riesgo", caido)
    d.recargar()
    assert espera(lambda: d.pagina == 2)
    assert d.estado_error.boton is not None and d.estado_error.boton.text() == "Reintentar"
    monkeypatch.setattr(app_admin.api, "resumen_riesgo", lambda: vacio)
    d.estado_error.boton.click()
    assert espera(lambda: d.pagina == 1)
    assert d.tarjeta_total.valor == "4"


def test_dashboard_muestra_cargando_mientras_consulta(win, app_admin, espera, monkeypatch):
    d = win.vistas["dashboard"]
    liberar = threading.Event()
    original = app_admin.api.resumen_riesgo

    def lento():
        liberar.wait(5)
        return original()
    monkeypatch.setattr(app_admin.api, "resumen_riesgo", lento)
    d.recargar()
    assert d._cargando.isVisible()
    liberar.set()
    assert espera(lambda: not d._cargando.isVisible())


# ---------------------------------------------------------------------------------------------
# Inventario
# ---------------------------------------------------------------------------------------------
def test_inventario_tabla_columnas_y_riesgo(win, espera, productos):
    creados, sufijo = productos
    v = ir(win, espera, "inventario")
    v.recargar()
    assert espera(lambda: f"Yogur {sufijo}" in filas_inventario(v))
    cab = [v.tabla.horizontalHeaderItem(i).text() for i in range(v.tabla.columnCount())]
    assert cab == ["ID", "Nombre", "Categoría", "Precio base", "Precio con descuento", "Stock",
                   "Stock máx.", "Vencimiento", "Riesgo"]
    r = filas_inventario(v)[f"Yogur {sufijo}"]
    assert v.tabla.texto(r, 8) == "Crítico"
    assert v.tabla.texto(r, 3) == "$4.500"
    assert v.tabla.texto(r, 4) != v.tabla.texto(r, 3)           # con descuento
    r2 = filas_inventario(v)[f"Aceite {sufijo}"]
    assert v.tabla.texto(r2, 8) == "Normal" and v.tabla.texto(r2, 7) == "Sin vencimiento"
    assert v.tabla.texto(r2, 4) == v.tabla.texto(r2, 3)


def test_inventario_botones_sin_seleccion_y_filtros(win, espera, productos):
    creados, sufijo = productos
    v = ir(win, espera, "inventario")
    v.recargar()
    assert espera(lambda: f"Yogur {sufijo}" in filas_inventario(v))
    v.tabla.clearSelection()
    assert not v.btn_editar.isEnabled() and not v.btn_baja.isEnabled()
    assert v.seleccionar(creados[0].id)
    assert v.btn_editar.isEnabled() and v.btn_baja.isEnabled()
    # busqueda por texto
    v.busqueda.setText(sufijo)
    assert set(filas_inventario(v)) == {f"Yogur {sufijo}", f"Arroz {sufijo}", f"Aceite {sufijo}"}
    v.busqueda.setText(f"arroz {sufijo}")
    assert list(filas_inventario(v)) == [f"Arroz {sufijo}"]
    assert not v.btn_editar.isEnabled()                         # la seleccion quedo fuera del filtro
    # filtro por categoria
    v.busqueda.setText(sufijo)
    v.filtro_categoria.setCurrentText("Lácteos")
    assert list(filas_inventario(v)) == [f"Yogur {sufijo}"]
    v.busqueda.setText("zzz-no-existe")
    assert v.paginas.currentIndex() == inv_mod.SIN_RESULTADOS
    v.limpiar_filtros()
    assert v.paginas.currentIndex() == inv_mod.TABLA


def test_inventario_crear_editar_y_baja_por_la_ui(win, espera, confirma, api_admin):
    v = ir(win, espera, "inventario")
    nombre = f"Galletas {uuid.uuid4().hex[:6]}"
    # --- crear
    v.btn_agregar.click()
    dlg = v._dialogo
    assert dlg is not None and dlg.isVisible()
    dlg.nombre.setText(nombre)
    dlg.categoria.setCurrentText("Snacks")
    dlg.precio.setText("2500,50")
    dlg.stock.setText("40")
    dlg.stock_max.setText("120")
    dlg.tiene_venc.setChecked(True)
    dlg.vencimiento.setDate(QDate.currentDate().addDays(90))
    dlg.btn_guardar.click()
    assert espera(lambda: nombre in filas_inventario(v))
    assert espera(lambda: v._dialogo is None)
    creado = next(p for p in api_admin.listar_productos() if p.nombre == nombre)
    try:
        assert creado.precio_base == 2500.5 and creado.stock == 40 and creado.stock_maximo == 120
        assert creado.categoria == "Snacks" and creado.fecha_vencimiento is not None
        assert any("creado" in t.text() for t in Toast.activos(win))
        # --- editar (solo cambia stock y precio)
        assert v.seleccionar(creado.id)
        v.btn_editar.click()
        dlg = v._dialogo
        assert dlg.nombre.text() == nombre and dlg.stock.text() == "40" and dlg.tiene_venc.isChecked()
        dlg.stock.setText("55")
        dlg.precio.setText("2600")
        dlg.btn_guardar.click()
        assert espera(lambda: api_admin.listar_productos() and
                      next(p for p in api_admin.listar_productos() if p.id == creado.id).stock == 55)
        assert espera(lambda: v.tabla.texto(filas_inventario(v)[nombre], 5) == "55")
        assert next(p for p in api_admin.listar_productos() if p.id == creado.id).precio_base == 2600
        # --- editar sin cambios: aviso y no cierra
        assert v.seleccionar(creado.id)
        v.btn_editar.click()
        dlg = v._dialogo
        dlg.btn_guardar.click()
        assert not dlg.lbl_error.isHidden() and "No hay cambios" in dlg.lbl_error.text()
        dlg.btn_cancelar.click()
        # --- baja logica: cancelar no borra
        assert v.seleccionar(creado.id)
        confirma["respuesta"] = False
        v.btn_baja.click()
        assert confirma["llamadas"] and nombre in confirma["llamadas"][-1][1]
        assert any(p.id == creado.id for p in api_admin.listar_productos())
        # --- baja confirmada
        confirma["respuesta"] = True
        v.btn_baja.click()
        assert espera(lambda: nombre not in filas_inventario(v))
        assert not any(p.id == creado.id for p in api_admin.listar_productos())
        assert not v.btn_baja.isEnabled()
    finally:
        try:
            api_admin.eliminar_producto(creado.id)
        except ApiError:
            pass


def test_dialogo_producto_valida_antes_de_enviar(win, espera, api_admin):
    v = ir(win, espera, "inventario")
    antes = len(api_admin.listar_productos())
    v.btn_agregar.click()
    dlg = v._dialogo
    dlg.btn_guardar.click()                                     # todo vacio
    assert dlg.texto_error_campo("nombre") == "El nombre es obligatorio"
    assert "obligatorio" in dlg.texto_error_campo("precio_base")
    assert dlg.texto_error_campo("stock") and dlg.texto_error_campo("stock_maximo")
    assert dlg.nombre.property("error") == "true"
    dlg.nombre.setText("X")
    dlg.precio.setText("-5")
    dlg.stock.setText("abc")
    dlg.stock_max.setText("0")
    dlg.btn_guardar.click()
    assert "mayor que 0" in dlg.texto_error_campo("precio_base")
    assert dlg.texto_error_campo("stock") and "mayor que 0" in dlg.texto_error_campo("stock_maximo")
    assert dlg.texto_error_campo("nombre") == ""
    assert dlg.nombre.property("error") == "false"
    dlg.precio.setText("10")
    dlg.stock.setText("1.5")
    dlg.stock_max.setText("10")
    dlg.btn_guardar.click()
    assert dlg.texto_error_campo("stock")                       # no entero
    dlg.stock.setText("1")
    dlg.tiene_venc.setChecked(True)
    dlg.vencimiento.setDate(QDate.currentDate().addDays(-2))
    dlg.btn_guardar.click()
    assert "pasó" in dlg.texto_error_campo("fecha_vencimiento")
    assert len(api_admin.listar_productos()) == antes           # nada llego al servidor
    dlg.btn_cancelar.click()
    assert espera(lambda: v._dialogo is None)


def test_dialogo_producto_muestra_errores_del_servidor(win, app_admin, espera, monkeypatch):
    v = ir(win, espera, "inventario")
    v.btn_agregar.click()
    dlg = v._dialogo
    dlg.nombre.setText("Prueba")
    dlg.precio.setText("10")
    dlg.stock.setText("1")
    dlg.stock_max.setText("10")

    def rechaza(_datos):
        raise ApiError("VALIDACION", "Datos de la petición inválidos", 422,
                       {"errores": [{"campo": "body.nombre", "mensaje": "Nombre no permitido",
                                     "tipo": "x"}]})
    monkeypatch.setattr(app_admin.api, "crear_producto", rechaza)
    dlg.btn_guardar.click()
    assert espera(lambda: dlg.btn_guardar.isEnabled())
    assert dlg.texto_error_campo("nombre") == "Nombre no permitido" and dlg.isVisible()

    def conflicto(_datos):
        raise ApiError("PRODUCTO_INACTIVO", "El producto está inactivo", 409)
    monkeypatch.setattr(app_admin.api, "crear_producto", conflicto)
    dlg.btn_guardar.click()
    assert espera(lambda: not dlg.lbl_error.isHidden())
    assert dlg.lbl_error.text() == "El producto está inactivo"
    dlg.btn_cancelar.click()


@pytest.fixture
def espia_hilos(monkeypatch):
    hilos = []
    for nombre in ("exportar_excel", "exportar_pdf"):
        original = getattr(inv_mod, nombre)

        def envoltorio(*a, _o=original, **k):
            hilos.append(threading.current_thread())
            return _o(*a, **k)
        monkeypatch.setattr(inv_mod, nombre, envoltorio)
    return hilos


def test_exportar_excel_valido_en_hilo_aparte(win, espera, productos, espia_hilos, monkeypatch):
    openpyxl = pytest.importorskip("openpyxl")
    creados, sufijo = productos
    v = ir(win, espera, "inventario")
    v.recargar()
    assert espera(lambda: f"Yogur {sufijo}" in filas_inventario(v))
    v.busqueda.setText(sufijo)                                  # exporta lo filtrado
    abiertas = []
    monkeypatch.setattr(comunes, "abrir_ruta", lambda r: abiertas.append(Path(r)))
    v.btn_excel.click()
    assert espera(lambda: not v.barra_reporte.isHidden())
    ruta = v._ultimo_reporte
    assert ruta.suffix == ".xlsx" and ruta.name.startswith("inventario_") and ruta.exists()
    assert len(ruta.stem.split("_")) == 3                       # inventario_AAAAMMDD_HHMMSS
    assert espia_hilos and espia_hilos[0] is not threading.main_thread()
    wb = openpyxl.load_workbook(ruta)
    ws = wb["Inventario"]
    filas = [[c.value for c in r] for r in ws.iter_rows(min_row=4)]
    assert filas[0] == ["ID", "Nombre", "Categoría", "Precio base", "Precio con descuento", "Stock",
                        "Stock máx.", "Vencimiento", "Riesgo"]
    nombres = [f[1] for f in filas[1:]]
    assert sorted(nombres) == sorted([f"Yogur {sufijo}", f"Arroz {sufijo}", f"Aceite {sufijo}"])
    yogur = next(f for f in filas if f[1] == f"Yogur {sufijo}")
    assert yogur[3] == 4500 and yogur[4] < 4500 and yogur[8] == "Crítico"
    assert any("guardado" in t.text() for t in Toast.activos(win))
    # ofrecer abrir
    v.btn_abrir_archivo.click()
    v.btn_abrir_carpeta.click()
    assert abiertas == [ruta, ruta.parent]
    assert ruta.parent.name == "reportes" or ruta.parent.name == "Reportes"


def test_exportar_pdf_valido(win, espera, productos, espia_hilos):
    creados, sufijo = productos
    v = ir(win, espera, "inventario")
    v.recargar()
    assert espera(lambda: f"Aceite {sufijo}" in filas_inventario(v))
    v.btn_pdf.click()
    assert espera(lambda: not v.barra_reporte.isHidden())
    ruta = v._ultimo_reporte
    assert ruta.suffix == ".pdf" and ruta.exists()
    datos = ruta.read_bytes()
    assert datos.startswith(b"%PDF-") and b"%%EOF" in datos[-64:] and len(datos) > 1500
    assert espia_hilos[0] is not threading.main_thread()


def test_exportar_sin_filas_avisa(win, espera):
    v = ir(win, espera, "inventario")
    v.busqueda.setText("zzz-nada-coincide-zzz")
    assert not v.btn_excel.isEnabled() and not v.btn_pdf.isEnabled()
    v.exportar("xlsx")
    assert any("No hay productos" in t.text() for t in Toast.activos(win))


def test_inventario_se_actualiza_solo_por_eventos_del_servidor(win, espera, api_admin):
    v = ir(win, espera, "inventario")
    nombre = f"Evento {uuid.uuid4().hex[:6]}"
    p = api_admin.crear_producto(ProductoIn(nombre=nombre, precio_base=10, stock=5))
    try:
        assert espera(lambda: nombre in filas_inventario(v), timeout=10)
    finally:
        api_admin.eliminar_producto(p.id)
    assert espera(lambda: nombre not in filas_inventario(v), timeout=10)


# ---------------------------------------------------------------------------------------------
# Alertas
# ---------------------------------------------------------------------------------------------
def test_alertas_agrupadas_y_escaneo(win, app_admin, espera, productos):
    creados, sufijo = productos
    v = ir(win, espera, "alertas")
    v.recargar()
    assert espera(lambda: any(f.lbl_nombre.text() == f"Yogur {sufijo}" for f in v.filas()))
    assert "critico" in v.grupos()
    assert v.grupos() == sorted(v.grupos(), key=["critico", "alto", "medio"].index)
    yogur = next(f for f in v.filas() if f.lbl_nombre.text() == f"Yogur {sufijo}")
    assert yogur.badge.nivel == "critico" and "Stock" in yogur.lbl_stock.text()
    v.btn_escanear.click()
    assert not v.btn_escanear.isEnabled() and v.btn_escanear.text() == "Escaneando…"
    assert espera(lambda: v.btn_escanear.isEnabled())
    assert v.btn_escanear.text() == "Escanear ahora"
    textos = [t.text() for t in Toast.activos(win)]
    assert any("Escaneo completado" in t and "evaluados" in t for t in textos)


def test_alertas_vacio_y_error(win, app_admin, espera, monkeypatch):
    from shared.schemas import AlertasOut
    v = ir(win, espera, "alertas")
    monkeypatch.setattr(app_admin.api, "alertas_riesgo", lambda: AlertasOut())
    v.recargar()
    assert espera(lambda: v.pagina == 1)

    def caido():
        raise ErrorConexion("x")
    monkeypatch.setattr(app_admin.api, "alertas_riesgo", caido)
    v.recargar()
    assert espera(lambda: v.pagina == 2)
    monkeypatch.setattr(app_admin.api, "alertas_riesgo", lambda: AlertasOut())
    v.estado_error.boton.click()
    assert espera(lambda: v.pagina == 1)


# ---------------------------------------------------------------------------------------------
# Usuarios
# ---------------------------------------------------------------------------------------------
def fila_usuario(v, usuario):
    for r in range(v.tabla.rowCount()):
        if v.tabla.texto(r, 2) == usuario:
            return r
    return None


def test_usuarios_crear_validar_activar_y_password(win, app_admin, espera, confirma, servidor):
    v = ir(win, espera, "usuarios")
    assert fila_usuario(v, "admin") is not None
    assert "(tú)" in v.tabla.texto(fila_usuario(v, "admin"), 1)
    u = f"cajero{uuid.uuid4().hex[:5]}"
    v.btn_nuevo.click()
    dlg = v._dialogo
    dlg.btn_guardar.click()
    assert dlg.texto_error_campo("nombre") and dlg.texto_error_campo("usuario")
    assert "8" in dlg.texto_error_campo("password")
    dlg.nombre.setText("Cajero Prueba")
    dlg.usuario.setText("a b")
    dlg.password.setText("corta")
    dlg.confirmacion.setText("otra")
    dlg.btn_guardar.click()
    assert "sin espacios" in dlg.texto_error_campo("usuario")
    assert "8" in dlg.texto_error_campo("password")
    assert "no coinciden" in dlg.texto_error_campo("confirmacion")
    dlg.usuario.setText(u)
    dlg.password.setText("clave-segura-1")
    dlg.confirmacion.setText("clave-segura-1")
    assert dlg.rol.currentData() == "comprador"
    dlg.btn_guardar.click()
    assert espera(lambda: fila_usuario(v, u) is not None)
    r = fila_usuario(v, u)
    assert v.tabla.texto(r, 3) == "Comprador" and v.tabla.texto(r, 4) == "Activo"

    # duplicado: 409 con el mensaje del servidor dentro del dialogo
    v.btn_nuevo.click()
    dlg = v._dialogo
    dlg.nombre.setText("Otro")
    dlg.usuario.setText(u)
    dlg.password.setText("clave-segura-1")
    dlg.confirmacion.setText("clave-segura-1")
    dlg.btn_guardar.click()
    assert espera(lambda: not dlg.lbl_error.isHidden())
    assert dlg.lbl_error.text()
    dlg.btn_cancelar.click()

    # desactivar / activar con confirmacion
    assert v.seleccionar(next(x.id for x in v._usuarios if x.usuario == u))
    assert v.btn_estado.text() == "Desactivar"
    confirma["respuesta"] = False
    v.btn_estado.click()
    assert v.seleccionado().activo
    confirma["respuesta"] = True
    v.btn_estado.click()
    assert espera(lambda: v.tabla.texto(fila_usuario(v, u), 4) == "Inactivo")
    assert v.seleccionar(next(x.id for x in v._usuarios if x.usuario == u))
    assert v.btn_estado.text() == "Activar"
    v.btn_estado.click()
    assert espera(lambda: v.tabla.texto(fila_usuario(v, u), 4) == "Activo")

    # cambiar contraseña y entrar con la nueva
    assert v.seleccionar(next(x.id for x in v._usuarios if x.usuario == u))
    v.btn_password.click()
    dlg = v._dialogo
    dlg.password.setText("nueva-clave-99")
    dlg.confirmacion.setText("distinta-clave")
    dlg.btn_guardar.click()
    assert "no coinciden" in dlg.texto_error_campo("confirmacion")
    dlg.confirmacion.setText("nueva-clave-99")
    dlg.btn_guardar.click()
    assert espera(lambda: v._dialogo is None)
    c = ApiClient(servidor.url)
    try:
        c.login(u, "nueva-clave-99")
    finally:
        c.cerrar()


def test_usuarios_admin_no_puede_desactivarse_a_si_mismo(win, app_admin, espera, confirma):
    v = ir(win, espera, "usuarios")
    assert v.seleccionar(app_admin.sesion.usuario_id)
    v.btn_estado.click()
    assert espera(lambda: any(t.tipo == "error" for t in Toast.activos(win)))
    assert app_admin.sesion is not None                          # sigue con sesion
    assert v.seleccionado().activo


def test_usuarios_botones_sin_seleccion(win, espera):
    v = ir(win, espera, "usuarios")
    v.tabla.clearSelection()
    assert not v.btn_estado.isEnabled() and not v.btn_password.isEnabled()


# ---------------------------------------------------------------------------------------------
# Configuracion
# ---------------------------------------------------------------------------------------------
@pytest.fixture
def restaurar_config(api_admin):
    antes = api_admin.obtener_config()
    yield antes
    api_admin.actualizar_config({
        k: getattr(antes, k) for k in (
            "inactividad_segundos", "aviso_segundos", "descuento_critico", "descuento_alto",
            "descuento_sobrestock", "dias_alerta_vencimiento",
            "dias_critico_vencimiento", "umbral_stock_bajo", "intervalo_escaneo_segundos",
            "nombre_negocio", "iva_pct", "nit", "direccion", "telefono", "moneda")})


def test_config_carga_valores_y_preview(win, espera, restaurar_config):
    v = ir(win, espera, "configuracion")
    assert v.valores()["inactividad_segundos"] == restaurar_config.inactividad_segundos
    assert v._widgets["nombre_negocio"].text() == restaurar_config.nombre_negocio
    assert not v.btn_guardar.isEnabled()                         # sin cambios
    v._widgets["inactividad_segundos"].setText("180")
    v._widgets["aviso_segundos"].setText("30")
    assert v.lbl_previa.text() == "Se cerrará la sesión tras 3 min 0 s sin actividad; aviso 30 s antes"
    assert duracion(45) == "45 s" and vista_previa(90, 10).startswith("Se cerrará la sesión tras 1 min 30 s")


def test_config_sin_campo_nivel_medio(win, espera, restaurar_config):
    from client.presentation.views import config_view as cv
    v = ir(win, espera, "configuracion")
    assert "descuento_medio" not in v._widgets and "descuento_medio" not in v.valores()
    assert "descuento_medio" not in cv.DEFECTOS and "descuento_medio" not in cv.DECIMALES
    assert {"descuento_critico", "descuento_alto", "descuento_sobrestock"} <= set(v._widgets)


def test_config_validacion_de_rangos_en_vivo(win, espera, restaurar_config):
    v = ir(win, espera, "configuracion")
    ina, avi = v._widgets["inactividad_segundos"], v._widgets["aviso_segundos"]
    ina.setText("10")
    assert "entre 30 y 3600" in v._errores["inactividad_segundos"].text()
    assert not v._errores["inactividad_segundos"].isHidden()
    assert ina.property("error") == "true" and not v.btn_guardar.isEnabled()
    assert "Corrige" in v.lbl_previa.text()
    ina.setText("5000")
    assert "entre 30 y 3600" in v._errores["inactividad_segundos"].text()
    ina.setText("")
    assert v._errores["inactividad_segundos"].text()
    ina.setText("120")
    assert v._errores["inactividad_segundos"].isHidden() and ina.property("error") == "false"
    avi.setText("3")
    assert "al menos 5" in v._errores["aviso_segundos"].text()
    avi.setText("120")
    assert "menor que" in v._errores["aviso_segundos"].text() and not v.btn_guardar.isEnabled()
    avi.setText("60")
    assert v._errores["aviso_segundos"].isHidden() and v.btn_guardar.isEnabled()
    assert v.lbl_previa.text() == "Se cerrará la sesión tras 2 min 0 s sin actividad; aviso 1 min 0 s antes"
    v.descartar()
    assert ina.text() == str(restaurar_config.inactividad_segundos) and not v.btn_guardar.isEnabled()
    v._widgets["dias_critico_vencimiento"].setValue(v._widgets["dias_alerta_vencimiento"].value() + 1)
    assert "No puede superar" in v._errores["dias_critico_vencimiento"].text()


def test_config_guarda_inactividad_y_llega_al_idle_monitor(win, app_admin, espera, api_admin,
                                                           restaurar_config):
    v = ir(win, espera, "configuracion")
    v._widgets["inactividad_segundos"].setText("60")
    v._widgets["aviso_segundos"].setText("15")
    assert v.btn_guardar.isEnabled()
    v.btn_guardar.click()
    assert espera(lambda: api_admin.obtener_config().inactividad_segundos == 60)
    cfg = api_admin.obtener_config()
    assert cfg.aviso_segundos == 15
    assert espera(lambda: any("guardada" in t.text() for t in Toast.activos(win)))
    # el IdleMonitor del app_ctx recibe el cambio (evento config_cambiada -> /auth/sesion)
    assert espera(lambda: app_admin.idle.inactividad_segundos == 60 and app_admin.idle.aviso_segundos == 15)
    assert app_admin.sesion.inactividad_segundos == 60
    assert espera(lambda: "Aplicado a tu sesión actual" in v.lbl_vigente.text())
    assert "1 min 0 s" in v.lbl_vigente.text()
    assert not v.btn_guardar.isEnabled()                         # ya sin cambios pendientes


def test_config_respaldo_si_no_llega_el_evento(win, app_admin, espera, api_admin, restaurar_config, monkeypatch):
    """Si el WebSocket no entrega config_cambiada, la vista hace una consulta de respaldo."""
    v = ir(win, espera, "configuracion")
    monkeypatch.setattr(app_admin, "_refrescar_parametros_sesion", lambda: None)
    v._widgets["inactividad_segundos"].setText("75")
    v._widgets["aviso_segundos"].setText("20")
    # sin respaldo inmediato: se espera el tiempo de vigilancia
    v.btn_guardar.click()
    assert espera(lambda: app_admin.idle.inactividad_segundos == 75, timeout=10)


def test_config_error_422_del_servidor_junto_al_campo(win, app_admin, espera, monkeypatch, restaurar_config):
    v = ir(win, espera, "configuracion")

    def rechaza(_c):
        raise ApiError("VALIDACION", "'descuento_critico' fuera de rango [0, 100]", 422,
                       {"clave": "descuento_critico", "minimo": 0, "maximo": 100})
    monkeypatch.setattr(app_admin.api, "actualizar_config", rechaza)
    v._widgets["descuento_critico"].setValue(40)
    v.btn_guardar.click()
    err = v._errores["descuento_critico"]
    assert espera(lambda: not err.isHidden())
    assert "fuera de rango" in err.text()
    assert v._widgets["descuento_critico"].property("error") == "true"
    assert any(t.tipo == "error" for t in Toast.activos(win))
    v._widgets["descuento_critico"].setValue(45)                 # editar el campo limpia el error
    assert err.isHidden()

    def cruzada(_c):
        raise ApiError("VALIDACION", "aviso_segundos debe ser menor que inactividad_segundos", 422,
                       {"aviso_segundos": 60, "inactividad_segundos": 60})
    monkeypatch.setattr(app_admin.api, "actualizar_config", cruzada)
    v.btn_guardar.click()
    assert espera(lambda: not v._errores["aviso_segundos"].isHidden())


def test_config_restablecer_defectos_con_confirmacion(win, espera, api_admin, confirma, restaurar_config):
    api_admin.actualizar_config({"descuento_critico": 44, "inactividad_segundos": 90, "aviso_segundos": 20,
                                 "umbral_stock_bajo": 33})
    v = ir(win, espera, "configuracion")
    v.recargar()
    assert espera(lambda: v.valores()["descuento_critico"] == 44)
    confirma["respuesta"] = False
    v.btn_defectos.click()
    assert api_admin.obtener_config().descuento_critico == 44
    confirma["respuesta"] = True
    v.btn_defectos.click()
    assert espera(lambda: api_admin.obtener_config().descuento_critico == 50)
    cfg = api_admin.obtener_config()
    assert (cfg.inactividad_segundos, cfg.aviso_segundos, cfg.umbral_stock_bajo) == (180, 30, 10)
    assert espera(lambda: v.valores()["inactividad_segundos"] == 180)
    assert len(confirma["llamadas"]) == 2


def test_defectos_coinciden_con_el_servidor():
    from server.infrastructure.db.seed import CONFIG_POR_DEFECTO
    for k, v in DEFECTOS.items():
        assert float(CONFIG_POR_DEFECTO[k]) == float(v), k


def test_config_no_pisa_ediciones_sin_guardar(win, app_admin, espera, restaurar_config):
    v = ir(win, espera, "configuracion")
    v._widgets["nombre_negocio"].setText("Editando…")
    v.recargar(silencioso=True)
    app_admin.evento_ws.emit("config_cambiada", {"claves": ["nit"]})
    QApplication.processEvents()
    assert espera(lambda: not win._pendientes and not win._debounce.isActive())
    assert v._widgets["nombre_negocio"].text() == "Editando…"
    v.descartar()
    assert v._widgets["nombre_negocio"].text() == restaurar_config.nombre_negocio


def test_error_de_campo_se_limpia_al_corregirlo(win, espera):
    v = ir(win, espera, "inventario")
    v.btn_agregar.click()
    dlg = v._dialogo
    dlg.btn_guardar.click()
    assert dlg.texto_error_campo("nombre") and dlg.nombre.property("error") == "true"
    dlg.nombre.setText("Ya escrito")
    assert dlg.texto_error_campo("nombre") == "" and dlg.nombre.property("error") == "false"
    assert dlg.texto_error_campo("precio_base")                 # los demas siguen hasta corregirse
    dlg.btn_cancelar.click()


# ---------------------------------------------------------------------------------------------
# vencimiento "sin hora" y reactivacion
# ---------------------------------------------------------------------------------------------
def test_dialogo_nota_y_sin_falso_cambio_por_normalizacion(win, espera, api_admin):
    from PyQt6.QtWidgets import QLabel
    v = ir(win, espera, "inventario")
    nombre = f"Hoy {uuid.uuid4().hex[:6]}"
    hoy = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    p = api_admin.crear_producto(ProductoIn(nombre=nombre, precio_base=100, stock=5, stock_maximo=50,
                                            fecha_vencimiento=hoy))
    try:
        # el servidor lo guardo a las 23:59:59 de hoy
        assert p.fecha_vencimiento.strftime("%H:%M:%S") == "23:59:59"
        v.recargar()
        assert espera(lambda: nombre in filas_inventario(v))
        r = filas_inventario(v)[nombre]
        assert v.tabla.texto(r, 7) == hoy.date().isoformat()
        assert "23:59" in v.tabla.item(r, 7).toolTip()
        assert v.seleccionar(p.id)
        v.btn_editar.click()
        dlg = v._dialogo
        assert any(inv_mod.NOTA_VENCIMIENTO == w.text() for w in dlg.findChildren(QLabel))
        assert "23:59" in inv_mod.NOTA_VENCIMIENTO
        dlg.btn_guardar.click()                                 # hoy no es "fecha pasada" y no hay cambios
        assert dlg.texto_error_campo("fecha_vencimiento") == ""
        assert "No hay cambios" in dlg.lbl_error.text()
        dlg.btn_cancelar.click()
    finally:
        api_admin.eliminar_producto(p.id)


def test_reactivar_producto_inactivo_con_confirmacion(win, espera, confirma, api_admin):
    v = ir(win, espera, "inventario")
    nombre = f"Baja {uuid.uuid4().hex[:6]}"
    p = api_admin.crear_producto(ProductoIn(nombre=nombre, precio_base=100, stock=40, stock_maximo=50))
    try:
        api_admin.eliminar_producto(p.id)
        v.recargar()
        assert espera(lambda: v.cargada)
        assert nombre not in filas_inventario(v)
        v.chk_inactivos.setChecked(True)
        assert espera(lambda: nombre in filas_inventario(v))
        r = filas_inventario(v)[nombre]
        assert v.tabla.texto(r, 8) == "Inactivo"
        assert v.seleccionar(p.id)
        assert v.btn_reactivar.isEnabled() and not v.btn_baja.isEnabled()
        confirma["respuesta"] = False                           # cancelar no reactiva
        v.btn_reactivar.click()
        assert confirma["llamadas"] and nombre in confirma["llamadas"][-1][1]
        assert not any(x.id == p.id for x in api_admin.listar_productos())
        confirma["respuesta"] = True
        v.btn_reactivar.click()
        assert espera(lambda: any(x.id == p.id for x in api_admin.listar_productos()))
        assert espera(lambda: any("reactivado" in t.text() for t in Toast.activos(win)))
        assert espera(lambda: v.tabla.texto(filas_inventario(v)[nombre], 8) == "Normal")
        v.chk_inactivos.setChecked(False)
        assert espera(lambda: nombre in filas_inventario(v))
    finally:
        api_admin.eliminar_producto(p.id)


def test_reactivar_vencido_pide_fecha_nueva(win, espera, api_admin):
    v = ir(win, espera, "inventario")
    nombre = f"Vencido {uuid.uuid4().hex[:6]}"
    ayer = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=2)
    p = api_admin.crear_producto(ProductoIn(nombre=nombre, precio_base=100, stock=5, stock_maximo=50,
                                            fecha_vencimiento=ayer, activo=False))
    try:
        v.chk_inactivos.setChecked(True)
        assert espera(lambda: nombre in filas_inventario(v))
        assert v.seleccionar(p.id)
        v.btn_reactivar.click()
        dlg = v._dialogo
        assert dlg is not None and dlg.windowTitle() == "Reactivar producto"
        dlg.vencimiento.setDate(QDate.currentDate().addDays(-1))   # sigue vencida: no sale
        dlg.btn_guardar.click()
        assert "pasó" in dlg.texto_error_campo("fecha_vencimiento")
        assert not any(x.id == p.id for x in api_admin.listar_productos())
        dlg.vencimiento.setDate(QDate.currentDate().addDays(10))
        dlg.btn_guardar.click()
        assert espera(lambda: any(x.id == p.id for x in api_admin.listar_productos()))
        nuevo = next(x for x in api_admin.listar_productos() if x.id == p.id)
        assert nuevo.activo and nuevo.fecha_vencimiento.date() == (datetime.now() + timedelta(days=10)).date()
        assert espera(lambda: v._dialogo is None)
        v.chk_inactivos.setChecked(False)
    finally:
        api_admin.eliminar_producto(p.id)


def test_exportacion_muestra_fecha_y_hora_solo_si_no_es_cierre_de_dia():
    from client.presentation.views._exportar import FilaInventario, _venc
    base = dict(id=1, nombre="x", categoria="c", precio_base=1, precio_final=1, descuento=0,
                stock=1, stock_maximo=2, nivel="normal")
    assert _venc(FilaInventario(vencimiento="2030-01-05", hora_venc="23:59", **base)) == "2030-01-05"
    assert _venc(FilaInventario(vencimiento="2030-01-05", hora_venc="15:30", **base)) == "2030-01-05 15:30"
    assert _venc(FilaInventario(vencimiento=None, **base)) == "Sin vencimiento"
