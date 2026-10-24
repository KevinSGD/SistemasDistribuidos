"""Vistas del comprador contra el servidor REAL: catalogo, carrito, pago, factura y PDF."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import pytest
from PyQt6.QtWidgets import QApplication, QLabel

from client.application.sesion import Aplicacion, OpcionesCliente
from client.infrastructure import factura_pdf
from client.infrastructure.api_client import ApiError, ErrorConexion
from client.presentation.views.buyer_window import BuyerWindow
from client.presentation.views.carrito_modelo import (
    TIPO_NO_DISPONIBLE, TIPO_PRECIO, TIPO_STOCK_REDUCIDO, Carrito)
from client.presentation.views.pago_dialog import (
    PagoDialog, calcular_vista_previa, parsear_monto, validar_documento, validar_nombre)
from client.presentation.widgets import DocumentoFactura, Toast
from shared.schemas import (
    ClienteIn, CompraIn, FacturaOut, ItemCompraIn, PagoIn, ProductoIn, ProductoUpdate)
from tests.client.conftest import COMP_PW

RAPIDO = OpcionesCliente(throttle_actividad=0.2, tick_ms=100, health_ms=500, sondeo_ms=60000,
                         ping_ms=60000, backoff=(0.1, 0.2), solo_espontaneos=False,
                         cierre_logout_ms=200)


# -- helpers -------------------------------------------------------------------------------
def oferta(pid=1, nombre="Leche", stock=5, original=1000.0, final=500.0, desc=50.0, nivel="critico"):
    return {"producto_id": pid, "nombre": nombre, "categoria": "Lacteos", "stock": stock,
            "precio_original": original, "precio_final": final, "descuento": desc,
            "motivo": "Vence en 1 día(s)", "nivel": nivel}


def crear_oferta(api_admin, stock=10, precio=10000.0, nombre=None, categoria="Lácteos", dias=1):
    """Producto que vence pronto: el servidor lo evalua como oferta (critico, 50%)."""
    nombre = nombre or f"Leche {uuid.uuid4().hex[:6]}"
    return api_admin.crear_producto(ProductoIn(
        nombre=nombre, categoria=categoria, precio_base=precio, stock=stock, stock_maximo=1000,
        fecha_vencimiento=datetime.now() + timedelta(days=dias, hours=12)))


@pytest.fixture
def comprador(qapp, servidor, espera):
    app = Aplicacion(servidor.url, RAPIDO, timeout=3.0)
    app.iniciar()
    app.login.input_usuario.setText("comprador")
    app.login.input_password.setText(COMP_PW)
    app.login.btn_login.click()
    assert espera(lambda: app.sesion is not None and isinstance(app.ventana, BuyerWindow))
    yield app
    # deja terminar las peticiones en vuelo (refrescos por eventos) antes de cerrar el cliente HTTP
    espera(lambda: False, timeout=0.8)
    if app.sesion is not None:
        app._cerrando = False
        app._cerrar_sesion_local("fin", avisar_servidor=False)
    if app.login is not None:
        app.login.cerrada.disconnect()
        app.login.close()
        app.login.deleteLater()
    app.deleteLater()
    QApplication.processEvents()


@pytest.fixture
def sin_visor(monkeypatch):
    abiertos = []
    monkeypatch.setattr("client.presentation.views.factura_view.abrir_archivo",
                        lambda ruta: abiertos.append(ruta) or True)
    return abiertos


def esperar_ofertas(v, espera, *productos):
    assert espera(lambda: v.estado == "lista" and all(p.id in v.tarjetas for p in productos))


def llenar_pago(dlg, nombre="María Núñez", doc="1020304050"):
    dlg.input_nombre.setText(nombre)
    dlg.input_documento.setText(doc)


# -- logica pura del carrito ---------------------------------------------------------------
def test_carrito_agregar_respeta_stock():
    c = Carrito()
    o = oferta(stock=2)
    assert c.agregar(o).ok and c.agregar(o).ok
    r = c.agregar(o)
    assert not r.ok and "2" in r.mensaje and c.cantidad_de(1) == 2
    assert not Carrito().agregar(oferta(stock=0)).ok


def test_carrito_mas_menos_y_eliminacion():
    c = Carrito()
    c.agregar(oferta(stock=3))
    assert c.cambiar(1, +1).ok and c.cantidad_de(1) == 2
    assert c.cambiar(1, +1).ok and not c.cambiar(1, +1).ok and c.cantidad_de(1) == 3
    assert c.cambiar(1, -2).ok and c.cantidad_de(1) == 1
    assert c.cambiar(1, -1).ok and 1 not in c and len(c) == 0      # llega a 0: se elimina
    assert not c.cambiar(99, 1).ok


def test_carrito_totales_y_ahorro():
    c = Carrito(decimales=2)          # centavos solo cuando se piden explicitamente
    c.agregar(oferta(1, stock=5, original=1000, final=500, desc=50))
    c.agregar(oferta(1, stock=5, original=1000, final=500, desc=50))
    c.agregar(oferta(2, "Pan", stock=5, original=2500.5, final=2000.4, desc=20))
    assert c.cantidad_total == 3
    assert c.subtotal == 4500.5 and c.total == 3000.4 and c.ahorro == 1500.1
    assert c.items_compra() == [{"producto_id": 1, "cantidad": 2}, {"producto_id": 2, "cantidad": 1}]
    c.quitar(1)
    assert c.subtotal == 2500.5 and c.ahorro == 500.1
    c.vaciar()
    assert c.total == 0 and c.ahorro == 0 and not c.hay_problemas


def test_carrito_sincronizar_precio_stock_y_no_disponible():
    c = Carrito()
    c.agregar(oferta(1, stock=5))
    c.cambiar(1, +1)
    c.cambiar(1, +1)                                             # 3 unidades
    c.agregar(oferta(2, "Pan", stock=4))
    cambios = c.sincronizar([oferta(1, stock=2, final=400.0)])   # baja stock y precio; Pan sale
    tipos = {(x.producto_id, x.tipo) for x in cambios}
    assert (1, TIPO_PRECIO) in tipos and (1, TIPO_STOCK_REDUCIDO) in tipos
    assert (2, TIPO_NO_DISPONIBLE) in tipos
    assert c.cantidad_de(1) == 2 and c.linea(1).precio_anterior == 500.0
    assert c.linea(1).con_aviso and not c.linea(2).disponible and c.hay_problemas
    c.reconocer()
    assert c.linea(1).precio_anterior is None and c.hay_problemas
    c.quitar(2)
    assert not c.hay_problemas


def test_carrito_eventos_y_rechazo_servidor():
    c = Carrito()
    c.agregar(oferta(1, stock=5))
    c.cambiar(1, +1)
    c.cambiar(1, +1)
    assert [x.tipo for x in c.aplicar_stock(1, 2)] == [TIPO_STOCK_REDUCIDO] and c.cantidad_de(1) == 2
    assert c.aplicar_stock(7, 1) == []
    assert [x.tipo for x in c.rechazo_servidor(1, "STOCK_INSUFICIENTE", 1)] == [TIPO_STOCK_REDUCIDO]
    assert c.cantidad_de(1) == 1
    assert c.rechazo_servidor(1, "PRODUCTO_VENCIDO")[0].tipo == TIPO_NO_DISPONIBLE
    assert not c.linea(1).disponible


# -- utilidades de pago --------------------------------------------------------------------
@pytest.mark.parametrize("txt,esperado", [
    ("25000", 25000.0), ("25.000", 25000.0), ("25.000,50", 25000.5), ("25,000.50", 25000.5),
    ("25,5", 25.5), ("$ 1.234.567", 1234567.0), ("10.5", 10.5), ("", None), ("abc", None), (",", None)])
def test_parsear_monto_con_centavos_explicitos(txt, esperado):
    # El criterio por defecto es 0 decimales; la capacidad de centavos se prueba con decimales=2.
    assert parsear_monto(txt, 2) == esperado


@pytest.mark.parametrize("txt,esperado", [
    ("25000", 25000), ("25.000", 25000), ("$ 1.234.567", 1234567), ("25.000,50", 25001),
    ("25,5", 26), ("10.5", 11), ("10.4", 10), ("", None), ("abc", None)])
def test_parsear_monto_pesos_enteros(txt, esperado):
    r = parsear_monto(txt)
    assert r == esperado and (r is None or isinstance(r, int))


def test_validaciones_cliente():
    assert validar_nombre("María Núñez") is None and validar_nombre("Tienda 24 S.A.S.") is None
    assert validar_nombre("") and validar_nombre("a") and validar_nombre("12345") and validar_nombre("x<y>")
    assert validar_documento("1020304050") is None and validar_documento("900.123.456-7") is None
    assert validar_documento("") and validar_documento("12") and validar_documento("12 34 5")
    assert validar_documento("1" * 21)


def test_vista_previa_iva_sobre_precio_con_descuento():
    c = Carrito()
    c.agregar(oferta(1, stock=5, original=1000, final=500, desc=50))
    v = calcular_vista_previa(c.lineas, 19)
    assert v == {"subtotal": 1000.0, "ahorro": 500.0, "base": 500.0, "iva": 95.0, "total": 595.0}


def test_carrito_pesos_enteros_redondea_half_up_como_el_servidor():
    c = Carrito()                                       # decimales_moneda = 0
    c.agregar(oferta(1, stock=9, original=1001, final=500.5, desc=50))
    c.cambiar(1, +1)
    assert c.linea(1).subtotal_final == 1001 and isinstance(c.total, int)
    c2 = Carrito()
    c2.agregar(oferta(2, "Pan", stock=9, original=5, final=2.5, desc=50))
    assert c2.total == 3 and c2.subtotal == 5 and c2.ahorro == 2     # 2,5 -> 3 (no 2)


def test_vista_previa_iva_19_de_28320_coincide_con_servidor():
    c = Carrito()
    c.agregar(oferta(1, stock=5, original=28320, final=28320, desc=0))
    v = calcular_vista_previa(c.lineas, 19)
    assert v == {"subtotal": 28320, "ahorro": 0, "base": 28320, "iva": 5381, "total": 33701}
    assert v["base"] + v["iva"] == v["total"]
    assert all(isinstance(x, int) for x in v.values())


def test_vista_previa_4500_con_15_por_ciento_y_cantidad():
    c = Carrito()
    for _ in range(3):
        c.agregar(oferta(1, stock=9, original=4500, final=3825, desc=15))
    v = calcular_vista_previa(c.lineas, 19)
    assert v["base"] == 11475 and v["ahorro"] == 2025 and v["iva"] == 2180 and v["total"] == 13655


# -- catalogo ------------------------------------------------------------------------------
def test_catalogo_muestra_ofertas_reales(comprador, espera, api_admin):
    p = crear_oferta(api_admin, stock=7, precio=12000, nombre=f"Yogur {uuid.uuid4().hex[:5]}")
    sin_oferta = api_admin.crear_producto(ProductoIn(
        nombre=f"Arroz {uuid.uuid4().hex[:5]}", precio_base=3000, stock=10, stock_maximo=1000))
    v = comprador.ventana
    v.cargar()
    esperar_ofertas(v, espera, p)
    assert sin_oferta.id not in v.tarjetas
    t = v.tarjetas[p.id]
    assert t.stock == 7 and "7" in t.lbl_detalle.text()
    assert t.lbl_descuento.text() == "-50%"
    assert t.lbl_original.text() == "$12.000" and t.lbl_final.text() == "$6.000"
    assert "text-decoration: line-through" in t.lbl_original.styleSheet()
    assert t.lbl_motivo.text() and t.btn_agregar.isEnabled()
    assert "#DC2626" in t.styleSheet() or "#D97706" in t.styleSheet()    # borde por nivel
    assert v.barra.lbl_usuario.text().startswith("Hola, ")
    assert v.panel_carrito.btn_pagar.isEnabled() is False                 # carrito vacio


def test_buscador_y_filtro_por_categoria(comprador, espera, api_admin):
    a = crear_oferta(api_admin, nombre=f"Manzana verde {uuid.uuid4().hex[:4]}", categoria="Frutería")
    b = crear_oferta(api_admin, nombre=f"Queso fresco {uuid.uuid4().hex[:4]}", categoria="Lácteos")
    v = comprador.ventana
    v.cargar()
    esperar_ofertas(v, espera, a, b)
    assert "Frutería" in [v.filtro_categoria.itemText(i) for i in range(v.filtro_categoria.count())]
    v.buscador.setText("manzana")                       # sin tildes ni mayusculas
    assert a.id in v.tarjetas and b.id not in v.tarjetas
    v.buscador.setText("")
    v.filtro_categoria.setCurrentIndex(v.filtro_categoria.findText("Lácteos"))
    assert b.id in v.tarjetas and a.id not in v.tarjetas
    v.buscador.setText("zzz-no-existe")
    assert v.estado == "sin_resultados"
    v.limpiar_filtros()
    assert v.estado == "lista" and a.id in v.tarjetas and b.id in v.tarjetas


def test_estado_error_y_reintento(comprador, espera, api_admin, monkeypatch):
    v = comprador.ventana
    assert espera(lambda: v.estado in ("lista", "vacio"))
    real = v.ctx.api.listar_ofertas

    def falla():
        raise ErrorConexion("sin red")
    monkeypatch.setattr(v.ctx.api, "listar_ofertas", falla)
    v._cargado = False
    v.cargar()
    assert espera(lambda: v.estado == "error")
    monkeypatch.setattr(v.ctx.api, "listar_ofertas", real)
    v.vista_error.boton.click()
    assert espera(lambda: v.estado in ("lista", "vacio"))


def test_error_en_refresco_conserva_ultimo_estado(comprador, espera, api_admin, monkeypatch):
    p = crear_oferta(api_admin)
    v = comprador.ventana
    v.cargar()
    esperar_ofertas(v, espera, p)
    monkeypatch.setattr(v.ctx.api, "listar_ofertas", lambda: (_ for _ in ()).throw(ErrorConexion("x")))
    v.cargar(silencioso=True)
    espera(lambda: False, timeout=0.5)
    assert v.estado == "lista" and p.id in v.tarjetas


# -- carrito en la ventana -----------------------------------------------------------------
def test_agregar_no_supera_stock_y_avisa_con_toast(comprador, espera, api_admin):
    p = crear_oferta(api_admin, stock=2)
    v = comprador.ventana
    v.cargar()
    esperar_ofertas(v, espera, p)
    t = v.tarjetas[p.id]
    t.btn_agregar.click()
    t.btn_agregar.click()
    assert v.carrito.cantidad_de(p.id) == 2 and not Toast.activos(v)
    t.btn_agregar.click()
    assert v.carrito.cantidad_de(p.id) == 2
    assert any("Solo hay 2" in x.text() for x in Toast.activos(v))
    fila = v.panel_carrito.filas()[0]
    assert fila.lbl_cantidad.text() == "2" and fila.btn_mas.isEnabled()
    fila.btn_mas.click()                                  # + en el carrito tambien respeta el stock
    assert v.carrito.cantidad_de(p.id) == 2
    fila.btn_menos.click()
    assert v.carrito.cantidad_de(p.id) == 1
    v.panel_carrito.filas()[0].btn_menos.click()          # llega a 0: se elimina
    assert len(v.carrito) == 0 and not v.panel_carrito.btn_pagar.isEnabled()
    t.btn_agregar.click()
    v.panel_carrito.filas()[0].btn_quitar.click()
    assert len(v.carrito) == 0


def test_resumen_del_carrito_y_vaciar_con_confirmacion(comprador, espera, api_admin, monkeypatch):
    p = crear_oferta(api_admin, stock=5, precio=10000)
    v = comprador.ventana
    v.cargar()
    esperar_ofertas(v, espera, p)
    for _ in range(2):
        v.tarjetas[p.id].btn_agregar.click()
    pc = v.panel_carrito
    assert pc.val_subtotal.text() == "$20.000" and pc.val_ahorro.text() == "-$10.000"
    assert pc.val_total.text() == "$10.000" and pc.lbl_items.text() == "2 items"
    assert pc.btn_pagar.isEnabled() and v.tarjetas[p.id].lbl_en_carrito.text() == "En tu carrito: 2"
    monkeypatch.setattr(BuyerWindow, "_confirmar", lambda self, t, x: False)
    pc.btn_vaciar.click()
    assert len(v.carrito) == 1
    monkeypatch.setattr(BuyerWindow, "_confirmar", lambda self, t, x: True)
    pc.btn_vaciar.click()
    assert len(v.carrito) == 0 and pc.val_total.text() == "—" and not pc.btn_pagar.isEnabled()


def test_cerrar_sesion_pide_confirmacion(comprador, espera, monkeypatch):
    v = comprador.ventana
    espera(lambda: v.estado in ("lista", "vacio"))
    monkeypatch.setattr(BuyerWindow, "_confirmar", lambda self, t, x: False)
    v.barra.btn_salir.click()
    assert comprador.sesion is not None
    monkeypatch.setattr(BuyerWindow, "_confirmar", lambda self, t, x: True)
    v.barra.btn_salir.click()
    assert comprador.sesion is None and comprador.login.isVisible()


# -- pago: validaciones del dialogo ---------------------------------------------------------
def test_confirmar_deshabilitado_con_efectivo_insuficiente_muestra_faltante(comprador, espera, api_admin):
    p = crear_oferta(api_admin, stock=5, precio=10000)           # 5.000 c/u con descuento
    v = comprador.ventana
    v.cargar()
    esperar_ofertas(v, espera, p)
    v.tarjetas[p.id].btn_agregar.click()
    v.panel_carrito.btn_pagar.click()
    d = v.dialogo_pago
    assert d is not None and d.isVisible()
    assert not d.btn_confirmar.isEnabled()                        # sin datos ni monto
    llenar_pago(d)
    assert not d.btn_confirmar.isEnabled()                        # falta el monto
    d.input_monto.setText("3000")
    assert not d.btn_confirmar.isEnabled()
    assert d.lbl_faltante.text() == "Faltan $2.000 para completar el pago"
    d.input_monto.setText("4999")
    assert d.lbl_faltante.text() == "Faltan $1 para completar el pago"        # pesos enteros
    d.input_monto.setText("5.000")
    assert d.btn_confirmar.isEnabled() and d.lbl_cambio.text() == "$0" and not d.lbl_faltante.text()
    d.input_monto.setText("10000")
    assert d.btn_confirmar.isEnabled() and d.lbl_cambio.text() == "$5.000"
    d.input_nombre.setText("")
    assert not d.btn_confirmar.isEnabled() and d.err_nombre.text()
    d.input_nombre.setText("Ana")
    d.input_documento.setText("12")
    assert not d.btn_confirmar.isEnabled() and d.err_documento.text()
    d.input_documento.setText("1234567")
    assert d.btn_confirmar.isEnabled()
    d.radio_tarjeta.setChecked(True)                              # tarjeta: sin monto ni numeros
    assert d.btn_confirmar.isEnabled() and not d.panel_efectivo.isVisible()
    assert d.construir_compra().pago.metodo == "tarjeta_simulada"
    assert d.construir_compra().pago.efectivo_recibido is None
    d.btn_cancelar.click()
    assert v.dialogo_pago is None and v.carrito.cantidad_de(p.id) == 1


# -- flujo completo ------------------------------------------------------------------------
def test_flujo_completo_efectivo_factura_pdf_y_stock(comprador, espera, api_admin, api_comprador,
                                                     sin_visor):
    api_admin.actualizar_config({"iva_pct": 19})
    try:
        p = crear_oferta(api_admin, stock=10, precio=10000, nombre=f"Café {uuid.uuid4().hex[:5]}")
        v = comprador.ventana
        v._cargar_config()
        v.cargar()
        esperar_ofertas(v, espera, p)
        assert espera(lambda: v.config.iva_pct == 19)
        for _ in range(3):
            v.tarjetas[p.id].btn_agregar.click()
        assert "IVA (19%)" in v.panel_carrito.lbl_nota_iva.text()
        v.panel_carrito.btn_pagar.click()
        d = v.dialogo_pago
        # 3 x 5.000 = 15.000 base; IVA 19% = 2.850; total 17.850
        assert d.lbl_total.text() == "$17.850"
        llenar_pago(d, "María Núñez", "1020304050")
        d.input_monto.setText("20000")
        assert d.btn_confirmar.isEnabled()
        d.btn_confirmar.click()
        assert d.procesando and d.btn_confirmar.text() == "Procesando…" and not d.btn_confirmar.isEnabled()
        d._confirmar()                                            # doble clic: se ignora
        assert espera(lambda: v.dialogo_factura is not None)
        fd = v.dialogo_factura
        f: FacturaOut = fd.factura
        assert f.total == 17850.0 and f.iva == 2850.0 and f.subtotal == 30000.0 and f.ahorro == 15000.0
        assert f.cambio == 2150.0 and f.efectivo_recibido == 20000.0
        assert f.cliente.nombre == "María Núñez" and f.cliente.documento == "1020304050"
        assert isinstance(fd.documento, DocumentoFactura)
        textos = " ".join(l.text() for l in fd.documento.findChildren(QLabel))
        for esperado in (f.numero, "María Núñez", "$17.850", "$2.850", "IVA 19%", "$2.150", "-$15.000"):
            assert esperado in textos
        # un solo cobro, carrito vacio, stock descontado en el servidor
        assert len(v.carrito) == 0
        assert api_comprador.obtener_factura(f.numero).total == f.total
        assert [x for x in api_comprador.listar_facturas(limite=50) if x.numero == f.numero] != []
        assert next(x for x in api_admin.listar_productos() if x.id == p.id).stock == 7
        assert espera(lambda: p.id in v.tarjetas and v.tarjetas[p.id].stock == 7)
        # PDF solo al pulsar el boton
        assert fd.ruta_pdf is None and sin_visor == []
        fd.btn_pdf.click()
        assert espera(lambda: fd.ruta_pdf is not None)
        ruta = fd.ruta_pdf
        assert ruta.name == f"{f.numero}.pdf" and ruta.parent.name == "reportes"
        datos = ruta.read_bytes()
        assert datos.startswith(b"%PDF") and datos.rstrip().endswith(b"%%EOF") and len(datos) > 2000
        assert sin_visor == [ruta] and fd.btn_pdf.isEnabled()
        fd.btn_cerrar.click()
        assert v.dialogo_factura is None and len(v.carrito) == 0
    finally:
        api_admin.actualizar_config({"iva_pct": 0})


def test_vista_previa_catalogo_y_pago_coinciden_con_la_factura_del_servidor(
        comprador, espera, api_admin, sin_visor):
    # 4.990 con 15 % = 4.241,5 -> 4.242 (half-up); 3 uds: base 12.726, IVA 19 % = 2.417,94 -> 2.418
    api_admin.actualizar_config({"iva_pct": 19, "descuento_critico": 15})
    try:
        p = crear_oferta(api_admin, stock=10, precio=4990, nombre=f"Jugo {uuid.uuid4().hex[:5]}")
        v = comprador.ventana
        v._cargar_config()
        v.cargar()
        esperar_ofertas(v, espera, p)
        assert espera(lambda: v.config.iva_pct == 19) and v.config.decimales_moneda == 0
        t = v.tarjetas[p.id]
        assert t.lbl_final.text() == "$4.242" and t.lbl_original.text() == "$4.990"
        for _ in range(3):
            t.btn_agregar.click()
        v.panel_carrito.btn_pagar.click()
        d = v.dialogo_pago
        assert d.vista == {"subtotal": 14970, "ahorro": 2244, "base": 12726, "iva": 2418,
                           "total": 15144}
        assert d.lbl_total.text() == "$15.144"
        llenar_pago(d)
        d.input_monto.setText("20000")
        d.btn_confirmar.click()
        assert espera(lambda: v.dialogo_factura is not None)
        f = v.dialogo_factura.factura
        assert f.items[0].precio_final == 4242 and f.items[0].subtotal == 12726
        assert (f.subtotal, f.ahorro, f.iva, f.total, f.cambio) == (
            d.vista["subtotal"], d.vista["ahorro"], d.vista["iva"], d.vista["total"], 4856)
        assert f.subtotal - f.ahorro + f.iva == f.total
        v.dialogo_factura.btn_cerrar.click()
    finally:
        api_admin.actualizar_config({"iva_pct": 0, "descuento_critico": 50})


def test_pago_tarjeta_simulada_sin_numeros(comprador, espera, api_admin, api_comprador):
    p = crear_oferta(api_admin, stock=4, precio=8000)
    v = comprador.ventana
    v.cargar()
    esperar_ofertas(v, espera, p)
    v.tarjetas[p.id].btn_agregar.click()
    v.panel_carrito.btn_pagar.click()
    d = v.dialogo_pago
    llenar_pago(d, "Carlos Peña", "900.123.456-7")
    d.radio_tarjeta.setChecked(True)
    assert "No se solicitan" in d.lbl_tarjeta.text()
    d.btn_confirmar.click()
    assert espera(lambda: v.dialogo_factura is not None)
    f = v.dialogo_factura.factura
    assert f.metodo_pago == "tarjeta_simulada" and f.efectivo_recibido is None
    assert "autorizada" in v.dialogo_factura.lbl_estado.text()
    v.dialogo_factura.btn_cerrar.click()


def test_compra_supera_stock_por_compra_concurrente(comprador, espera, api_admin, api_comprador, monkeypatch):
    p = crear_oferta(api_admin, stock=3, precio=10000)
    v = comprador.ventana
    v.cargar()
    esperar_ofertas(v, espera, p)
    for _ in range(3):
        v.tarjetas[p.id].btn_agregar.click()
    # otro usuario compra 2 primero; se pausan los eventos para forzar el 409 en el servidor
    comprador.evento_ws.disconnect(v._al_evento)
    v._t_refresco.stop()
    api_admin.comprar(CompraIn(items=[ItemCompraIn(producto_id=p.id, cantidad=2)],
                               pago=PagoIn(metodo="tarjeta_simulada")))
    v.panel_carrito.btn_pagar.click()
    d = v.dialogo_pago
    llenar_pago(d)
    d.input_monto.setText("100000")
    d.btn_confirmar.click()
    assert espera(lambda: v.dialogo_pago is None)                 # el dialogo se cierra
    assert comprador.sesion is not None and v.isVisible()         # la app sigue viva
    assert v.dialogo_factura is None
    assert v.carrito.cantidad_de(p.id) == 1                       # ajustado a lo disponible
    assert v.carrito.linea(p.id).cantidad_anterior == 3
    textos = [x.text() for x in Toast.activos(v)]
    assert any("Stock insuficiente" in t and "Disponible: 1" in t for t in textos)
    assert v.panel_carrito.filas()[0].resaltada
    assert next(x for x in api_admin.listar_productos() if x.id == p.id).stock == 1   # no cobro nada
    assert espera(lambda: v.tarjetas[p.id].stock == 1)            # catalogo refrescado


def test_error_efectivo_insuficiente_del_servidor_deja_reintentar(comprador, espera, api_admin, monkeypatch):
    p = crear_oferta(api_admin, stock=3, precio=10000)
    v = comprador.ventana
    v.cargar()
    esperar_ofertas(v, espera, p)
    v.tarjetas[p.id].btn_agregar.click()
    v.panel_carrito.btn_pagar.click()
    d = v.dialogo_pago
    llenar_pago(d)
    d.input_monto.setText("4000")
    d.vista["total"] = 1.0                       # el cliente cree que alcanza; el servidor discrepa
    d._validar()
    assert d.btn_confirmar.isEnabled()
    d.btn_confirmar.click()
    assert espera(lambda: not d.procesando)
    assert d.isVisible() and "faltan" in d.lbl_error.text() and d.btn_confirmar.text() == "Confirmar pago"
    d.btn_cancelar.click()


def test_producto_del_carrito_ya_no_disponible_resalta_y_bloquea_pago(comprador, espera, api_admin):
    p = crear_oferta(api_admin, stock=2, precio=10000)
    v = comprador.ventana
    v.cargar()
    esperar_ofertas(v, espera, p)
    v.tarjetas[p.id].btn_agregar.click()
    api_admin.comprar(CompraIn(items=[ItemCompraIn(producto_id=p.id, cantidad=2)],
                               pago=PagoIn(metodo="tarjeta_simulada")))     # lo agota
    assert espera(lambda: v.carrito.hay_problemas)
    fila = v.panel_carrito.filas()[0]
    assert fila.resaltada and not fila.btn_mas.isEnabled() and "disponible" in fila.lbl_aviso.text()
    assert any("agot" in x.text() or "disponible" in x.text() for x in Toast.activos(v))
    v.panel_carrito.btn_pagar.click()
    assert v.dialogo_pago is None                                 # no se puede pagar
    assert espera(lambda: p.id not in v.tarjetas)                 # el catalogo ya no lo ofrece


def test_cambio_de_precio_avisa_con_toast(comprador, espera, api_admin):
    p = crear_oferta(api_admin, stock=5, precio=10000)
    v = comprador.ventana
    v.cargar()
    esperar_ofertas(v, espera, p)
    v.tarjetas[p.id].btn_agregar.click()
    api_admin.actualizar_producto(p.id, ProductoUpdate(precio_base=20000))
    v.cargar(silencioso=True)
    assert espera(lambda: v.carrito.linea(p.id).precio_final == 10000.0)
    assert v.carrito.linea(p.id).precio_anterior == 5000.0
    assert v.panel_carrito.filas()[0].resaltada
    assert any("precio cambió" in x.text() for x in Toast.activos(v))
    assert v.panel_carrito.val_total.text() == "$10.000"


# -- eventos y actividad --------------------------------------------------------------------
def test_evento_ws_de_otro_cliente_actualiza_stock_mostrado(comprador, espera, api_admin):
    p = crear_oferta(api_admin, stock=10)
    v = comprador.ventana
    v.cargar()
    esperar_ofertas(v, espera, p)
    assert espera(lambda: comprador.eventos.esta_conectado)
    api_admin.comprar(CompraIn(items=[ItemCompraIn(producto_id=p.id, cantidad=4)],
                               pago=PagoIn(metodo="tarjeta_simulada")))
    assert espera(lambda: v.tarjetas.get(p.id) is not None and v.tarjetas[p.id].stock == 6)
    assert "<b>6</b>" in v.tarjetas[p.id].lbl_detalle.text()


def test_eventos_y_refresco_no_cuentan_como_actividad(comprador, espera, api_admin, monkeypatch):
    p = crear_oferta(api_admin, stock=10)
    v = comprador.ventana
    v.cargar()
    esperar_ofertas(v, espera, p)
    llamadas = []
    monkeypatch.setattr(comprador, "marcar_actividad_vista", lambda: llamadas.append(1))
    comprador.evento_ws.emit("stock_actualizado", {"producto_id": p.id, "stock": 9, "activo": True})
    comprador.sondeo.emit()
    v.cargar(silencioso=True)
    espera(lambda: False, timeout=0.8)
    assert llamadas == []
    # acciones del usuario: cada una marca actividad de vista
    v.filtro_categoria.setCurrentIndex(0)
    n0 = len(llamadas)
    v.limpiar_filtros()
    v.tarjetas[p.id].btn_agregar.click()
    v.panel_carrito.filas()[0].btn_mas.click()
    v.btn_actualizar.click()
    v.panel_carrito.filas()[0].btn_menos.click()
    assert len(llamadas) >= n0 + 5
    v.panel_carrito.btn_pagar.click()
    assert v.dialogo_pago is not None
    v.dialogo_pago.btn_cancelar.click()


def test_cambio_de_categoria_marca_actividad(comprador, espera, api_admin, monkeypatch):
    a = crear_oferta(api_admin, categoria="Panadería")
    v = comprador.ventana
    v.cargar()
    esperar_ofertas(v, espera, a)
    llamadas = []
    monkeypatch.setattr(comprador, "marcar_actividad_vista", lambda: llamadas.append(1))
    v.filtro_categoria.setCurrentIndex(v.filtro_categoria.findText("Panadería"))
    assert llamadas == [1]


# -- factura / PDF -------------------------------------------------------------------------
def factura_demo(**extra) -> dict:
    d = {"numero": "FV-000124", "fecha": datetime(2026, 10, 24, 14, 32),
         "negocio": {"nombre_negocio": "Panadería Ñandú", "nit": "900.123.456-7",
                     "direccion": "Cra 7 # 12-34", "telefono": "300", "moneda": "$"},
         "cliente": {"nombre": "José Ángel Núñez", "documento": "1020304050"},
         "items": [{"producto_id": 1, "nombre": "Leche entera 1L", "cantidad": 2,
                    "precio_original": 4200, "descuento_pct": 30, "precio_final": 2940, "subtotal": 5880},
                   {"producto_id": 2, "nombre": "Pan tajado ñoño", "cantidad": 1,
                    "precio_original": 6900, "descuento_pct": 0, "precio_final": 6900, "subtotal": 6900}],
         "subtotal": 15300, "ahorro": 2520, "iva": 2428, "total": 15208,
         "metodo_pago": "efectivo", "efectivo_recibido": 20000, "cambio": 4792}
    d.update(extra)
    return d


def test_pdf_mismos_datos_que_el_widget_y_soporta_tildes(qapp, tmp_path):
    d = factura_demo()
    ruta = factura_pdf.generar_factura_pdf(d, tmp_path, iva_pct=19)
    assert ruta == tmp_path / "FV-000124.pdf"
    datos = ruta.read_bytes()
    assert datos.startswith(b"%PDF") and datos.rstrip().endswith(b"%%EOF") and len(datos) > 2000
    # mismas cifras y rotulos que muestra el widget (modelo compartido de formato)
    m = factura_pdf.modelo_factura(d, 19)
    widget = DocumentoFactura({**d, "iva_pct": 19})
    textos = {l.text() for l in widget.findChildren(QLabel)}
    esperado = {m["negocio"], m["nit"], m["numero"], m["fecha"], m["cliente"], m["total"],
                m["pago"]["recibido"], m["pago"]["cambio"]}
    for etiqueta, valor, _ in m["totales"]:
        esperado |= {etiqueta, valor}
    for fila in m["filas"]:
        esperado |= set(fila)
    assert esperado <= textos, esperado - textos
    assert m["cliente"] == "José Ángel Núñez  (1020304050)" and "$2.428" in str(m["totales"])
    assert m["total"] == "$15.208" and m["pago"]["cambio"] == "$4.792"


def test_pdf_tarjeta_sin_caja_de_pago_y_nombre_seguro(qapp, tmp_path):
    d = factura_demo(numero="FV/00:9?", metodo_pago="tarjeta_simulada", efectivo_recibido=None, cambio=None)
    ruta = factura_pdf.generar_factura_pdf(d, tmp_path)
    assert ruta.parent == tmp_path and ruta.name == "FV_00_9.pdf" and ruta.read_bytes().startswith(b"%PDF")
    assert factura_pdf.modelo_factura(d)["pago"] is None


def test_pdf_sin_fuentes_ttf_usa_helvetica_con_tildes(qapp, tmp_path, monkeypatch):
    monkeypatch.setattr(factura_pdf, "_fuentes", None)
    monkeypatch.setattr(factura_pdf, "_CANDIDATAS", [])
    ruta = factura_pdf.generar_factura_pdf(factura_demo(), tmp_path)
    assert ruta.read_bytes().startswith(b"%PDF")
    monkeypatch.setattr(factura_pdf, "_fuentes", None)           # no contaminar a otros tests


def test_foco_inicial_en_el_buscador(comprador):
    comprador.ventana.show()
    QApplication.processEvents()
    assert comprador.ventana.focusWidget() is comprador.ventana.buscador
    assert comprador.ventana.barra.btn_salir.hasFocus() is False
