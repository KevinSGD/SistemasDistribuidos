"""Escenario 6: factura con IVA 19 % (servidor Linux calcula, cliente Windows muestra y genera el PDF).

Montos enteros (moneda sin decimales), total = base + IVA, PDF valido (estructura y tabla xref) y
numero consecutivo."""
import re
import zlib

import pytest

from client.presentation.views.buyer_window import BuyerWindow
from tests.e2e.pdfcheck import texto_pdf, validar_pdf
from tests.e2e.helpers import crear_oferta, entrar, esperar, esperar_ofertas, llenar_pago

pytestmark = pytest.mark.e2e


def _comprar_por_ui(v, espera, p, cantidad, nombre, doc, efectivo=None):
    v.cargar()
    assert esperar_ofertas(v, p)
    for _ in range(cantidad):
        v.tarjetas[p.id].btn_agregar.click()
    v.panel_carrito.btn_pagar.click()
    d = v.dialogo_pago
    assert d is not None
    llenar_pago(d, nombre, doc)
    if efectivo is None:
        d.radio_tarjeta.setChecked(True)
    else:
        d.input_monto.setText(str(efectivo))
    vista = dict(d.vista)
    assert d.btn_confirmar.isEnabled()
    d.btn_confirmar.click()
    assert espera(lambda: v.dialogo_factura is not None, 15)
    return v.dialogo_factura, vista


def test_factura_iva_19_enteros_pdf_y_consecutivo(servidor, crear_app, api_admin, api_comprador, espera,
                                                  sin_visor):
    api_admin.actualizar_config({"iva_pct": 19, "descuento_critico": 15})
    try:
        a = crear_app(servidor)
        entrar(a, "comprador", servidor.comp_pw)
        v = a.ventana
        assert isinstance(v, BuyerWindow)
        assert espera(lambda: v.config.iva_pct == 19, 10)
        p = crear_oferta(api_admin, stock=20, precio=4990, nombre="Jugo factura E2E")

        # --- compra 1: efectivo. 4.990 con 15 % = 4.241,5 -> 4.242 (half-up); 3 uds: base 12.726, IVA 2.418
        fd, vista = _comprar_por_ui(v, espera, p, 3, "María Núñez", "1020304050", efectivo=20000)
        f = fd.factura
        assert vista == {"subtotal": 14970, "ahorro": 2244, "base": 12726, "iva": 2418, "total": 15144}
        for campo in (f.subtotal, f.ahorro, f.iva, f.total, f.efectivo_recibido, f.cambio,
                      f.items[0].precio_original, f.items[0].precio_final, f.items[0].subtotal):
            assert float(campo).is_integer(), f"monto no entero: {campo}"          # moneda sin decimales
        assert (f.subtotal, f.ahorro, f.iva, f.total) == (14970, 2244, 2418, 15144)
        assert f.subtotal - f.ahorro + f.iva == f.total                              # total = base + IVA
        assert f.items[0].precio_final == 4242 and f.items[0].subtotal == 12726
        assert f.items[0].subtotal * 19 / 100 - f.iva < 1                            # IVA = 19 % de la base
        assert f.efectivo_recibido == 20000 and f.cambio == 20000 - 15144
        assert f.cliente.nombre == "María Núñez" and f.cliente.documento == "1020304050"
        assert re.fullmatch(r"[A-Z]+-\d{6}", f.numero), f.numero
        # la vista (Windows) coincide con lo que calculo el servidor (Linux)
        from PyQt6.QtWidgets import QLabel
        textos = " ".join(l.text() for l in fd.documento.findChildren(QLabel))
        for esperado in (f.numero, "$15.144", "$2.418", "IVA 19%", "$4.856", "-$2.244"):
            assert esperado in textos, (esperado, textos)

        # --- PDF: solo al pulsar el boton; estructura valida
        assert fd.ruta_pdf is None
        fd.btn_pdf.click()
        assert espera(lambda: fd.ruta_pdf is not None, 15)
        ruta = fd.ruta_pdf
        assert ruta.name == f"{f.numero}.pdf" and sin_visor == [ruta]
        info = validar_pdf(ruta.read_bytes())
        assert info["paginas"] >= 1 and info["bytes"] > 2000 and info["streams_decodificados"] >= 1
        texto = texto_pdf(ruta.read_bytes())
        for esperado in (f.numero, "15.144", "2.418", "IVA 19%", "4.856"):
            assert esperado in texto, (esperado, texto[:300])      # el PDF trae las mismas cifras
        fd.btn_cerrar.click()

        # --- compra 2: tarjeta. El numero es el siguiente
        fd2, _ = _comprar_por_ui(v, espera, p, 1, "Carlos Peña", "900.123.456-7")
        f2 = fd2.factura
        n1, n2 = int(f.numero.split("-")[1]), int(f2.numero.split("-")[1])
        assert f.numero.split("-")[0] == f2.numero.split("-")[0] and n2 == n1 + 1, (f.numero, f2.numero)
        assert f2.metodo_pago == "tarjeta_simulada" and f2.efectivo_recibido is None
        assert (f2.subtotal, f2.ahorro, f2.iva, f2.total) == (4990, 748, 806, 5048)  # 4.242 + 19 % = 806 (806,0 -> 806)
        assert f2.subtotal - f2.ahorro + f2.iva == f2.total
        fd2.btn_cerrar.click()

        # --- el servidor conserva ambas, el comprador solo ve las suyas, el admin ve todas
        assert api_comprador.obtener_factura(f.numero).total == 15144
        numeros_admin = [x.numero for x in api_admin.listar_facturas()]
        assert f.numero in numeros_admin and f2.numero in numeros_admin
        todos = sorted(int(n.split("-")[1]) for n in numeros_admin)
        assert todos == list(range(todos[0], todos[0] + len(todos))), "numeracion con huecos"
        print(f"\n[6] {f.numero}: subtotal {f.subtotal:.0f} - ahorro {f.ahorro:.0f} + IVA {f.iva:.0f} = total {f.total:.0f} "
              f"(cambio {f.cambio:.0f}); {f2.numero} consecutiva; PDF {ruta.name}: {info}; "
              f"numeracion de {len(todos)} facturas sin huecos")
    finally:
        api_admin.actualizar_config({"iva_pct": 0, "descuento_critico": 50})
