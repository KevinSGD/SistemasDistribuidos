"""Generacion del PDF de la factura EN EL CLIENTE, con los datos que devuelve el servidor.

No recalcula montos: imprime lo recibido (`FacturaOut`). Mismo diseno y mismos textos que el
widget `DocumentoFactura`. El PDF solo se genera cuando el usuario lo pide."""
from __future__ import annotations

import os
import platform
import re
import subprocess
from pathlib import Path
from typing import Any

from platformdirs import user_data_dir
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import HRFlowable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from xml.sax.saxutils import escape

from client.infrastructure.config import ENV_DIR
from client.presentation.styles.theme import COLORES, fmt_moneda

METODOS = {"efectivo": "Efectivo", "tarjeta_simulada": "Tarjeta (simulada)"}
PIE = "Documento generado por Inventario App. Resolución simulada, sin validez fiscal."


def carpeta_reportes() -> Path:
    base = Path(os.environ.get(ENV_DIR) or user_data_dir("InventarioApp"))
    return base / "reportes"


def ruta_pdf(numero: str, carpeta: Path | None = None) -> Path:
    limpio = re.sub(r"[^A-Za-z0-9._-]+", "_", str(numero)).strip("._") or "factura"
    return (carpeta or carpeta_reportes()) / f"{limpio}.pdf"


# -- modelo de presentacion (testeable sin PDF) -------------------------------------------
def a_dict(factura: Any) -> dict:
    return factura.model_dump() if hasattr(factura, "model_dump") else dict(factura)


def modelo_factura(factura: Any, iva_pct: float | None = None) -> dict:
    """Textos ya formateados, identicos a los del widget. `iva_pct` solo rotula la linea de IVA."""
    d = a_dict(factura)
    neg = d.get("negocio") or {}
    cli = d.get("cliente") or {}
    m = neg.get("moneda") or "$"
    fecha = d.get("fecha", "")
    if hasattr(fecha, "strftime"):
        fecha = fecha.strftime("%Y-%m-%d %H:%M")
    cliente = cli.get("nombre", "")
    if cli.get("documento"):
        cliente += f"  ({cli['documento']})"
    filas = []
    for it in d.get("items", []):
        pct = it.get("descuento_pct", 0)
        filas.append([it["nombre"], str(it["cantidad"]), fmt_moneda(it["precio_original"], m),
                      f"-{pct:g}%" if pct else "—", fmt_moneda(it["subtotal"], m)])
    subtotal, ahorro, iva = d.get("subtotal", 0), d.get("ahorro", 0) or 0, d.get("iva", 0) or 0
    totales = [("Subtotal sin descuento", fmt_moneda(subtotal, m), "normal")]
    if ahorro:
        totales.append(("Ahorro total", "-" + fmt_moneda(ahorro, m), "ahorro"))
    if iva:
        totales.append(("Base gravable", fmt_moneda(subtotal - ahorro, m), "normal"))
        totales.append((f"IVA {iva_pct:g}%" if iva_pct else "IVA", fmt_moneda(iva, m), "normal"))
    pago = None
    if d.get("efectivo_recibido") is not None:
        pago = {"recibido": fmt_moneda(d["efectivo_recibido"], m),
                "cambio": fmt_moneda(d.get("cambio") or 0, m)}
    return {
        "negocio": neg.get("nombre_negocio", ""), "nit": f"NIT {neg.get('nit', '')}",
        "direccion": neg.get("direccion", ""), "telefono": neg.get("telefono", ""),
        "numero": f"No. {d.get('numero', '')}", "numero_raw": str(d.get("numero", "")),
        "fecha": str(fecha), "cliente": cliente,
        "metodo": METODOS.get(d.get("metodo_pago", ""), str(d.get("metodo_pago", ""))),
        "columnas": ["Producto", "Cant.", "Precio", "Desc.", "Subtotal"], "filas": filas,
        "totales": totales, "total": fmt_moneda(d.get("total", 0), m), "pago": pago,
        "pie": PIE,
    }


# -- fuentes (tildes y enie) ---------------------------------------------------------------
_CANDIDATAS = [
    ("C:/Windows/Fonts/segoeui.ttf", "C:/Windows/Fonts/segoeuib.ttf"),
    ("C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/arialbd.ttf"),
    ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
     "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    ("/usr/share/fonts/dejavu/DejaVuSans.ttf", "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf"),
    ("/Library/Fonts/Arial.ttf", "/Library/Fonts/Arial Bold.ttf"),
    ("/System/Library/Fonts/Supplemental/Arial.ttf",
     "/System/Library/Fonts/Supplemental/Arial Bold.ttf"),
]
_fuentes: tuple[str, str] | None = None


def _registrar_fuentes() -> tuple[str, str]:
    """(normal, negrita). TTF del sistema si existe (cobertura Unicode amplia); si no, Helvetica,
    que ya cubre Latin-1 (tildes, enie, signos de apertura)."""
    global _fuentes
    if _fuentes is None:
        _fuentes = ("Helvetica", "Helvetica-Bold")
        for i, (normal, negrita) in enumerate(_CANDIDATAS):
            if Path(normal).exists() and Path(negrita).exists():
                try:
                    pdfmetrics.registerFont(TTFont(f"InvCli{i}", normal))
                    pdfmetrics.registerFont(TTFont(f"InvCli{i}-B", negrita))
                    _fuentes = (f"InvCli{i}", f"InvCli{i}-B")
                    break
                except Exception:  # noqa: BLE001  (fuente danada: probar la siguiente)
                    continue
    return _fuentes


def _p(texto: str) -> str:
    return escape(str(texto))


# -- PDF -------------------------------------------------------------------------------------
def generar_factura_pdf(factura: Any, carpeta: Path | None = None,
                        iva_pct: float | None = None) -> Path:
    """Escribe `<carpeta>/<numero>.pdf` (carpeta de reportes del usuario por defecto) y devuelve la
    ruta. Sobrescribe si ya existia (misma factura = mismo archivo)."""
    mod = modelo_factura(factura, iva_pct)
    ruta = ruta_pdf(mod["numero_raw"], carpeta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    fn, fb = _registrar_fuentes()

    def hexc(nombre: str):
        return colors.HexColor(COLORES[nombre])

    def estilo(nombre, tam, color, negrita=False, alinea=TA_LEFT, lead=None):
        return ParagraphStyle(nombre, fontName=fb if negrita else fn, fontSize=tam,
                              textColor=hexc(color), alignment=alinea, leading=lead or tam * 1.25)

    doc = SimpleDocTemplate(str(ruta), pagesize=letter, leftMargin=2 * cm, rightMargin=2 * cm,
                            topMargin=1.8 * cm, bottomMargin=1.8 * cm,
                            title=f"Factura {mod['numero_raw']}", author=mod["negocio"] or "Inventario App")
    ancho = letter[0] - 4 * cm
    el: list = []

    # Encabezado: monograma + negocio/NIT + titulo/numero
    inicial = (mod["negocio"] or "?")[0].upper()
    logo = Table([[Paragraph(_p(inicial), estilo("logo", 20, "texto_sobre_primario", True, TA_CENTER))]],
                 colWidths=[1.3 * cm], rowHeights=[1.3 * cm])
    logo.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), hexc("primario_texto")),
                              ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                              ("ROUNDEDCORNERS", [6, 6, 6, 6])]))
    izq = [Paragraph(_p(mod["negocio"]), estilo("neg", 18, "primario_texto", True)),
           Paragraph(_p(mod["nit"]), estilo("nit", 9, "texto_suave"))]
    der = [Paragraph("Factura de Venta", estilo("fv", 10, "texto_suave", False, TA_RIGHT)),
           Paragraph(_p(mod["numero"]), estilo("num", 11, "primario_texto", True, TA_RIGHT))]
    cab = Table([[logo, izq, der]], colWidths=[1.7 * cm, ancho - 1.7 * cm - 5 * cm, 5 * cm])
    cab.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                             ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
    el += [cab, Spacer(1, 0.25 * cm),
           HRFlowable(width="100%", thickness=0.8, color=hexc("borde")), Spacer(1, 0.25 * cm)]

    # Fecha / cliente / pago
    k, v = estilo("k", 9, "texto_suave"), estilo("v", 9, "texto", True)
    datos = Table([[Paragraph("Fecha", k), Paragraph(_p(mod["fecha"]), v)],
                   [Paragraph("Cliente", k), Paragraph(_p(mod["cliente"]), v)],
                   [Paragraph("Método de pago", k), Paragraph(_p(mod["metodo"]), v)]],
                  colWidths=[3 * cm, ancho - 3 * cm])
    datos.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                               ("LEFTPADDING", (0, 0), (-1, -1), 0),
                               ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2)]))
    el += [datos, Spacer(1, 0.3 * cm)]

    # Tabla de items
    enc = [Paragraph(_p(h), estilo(f"h{i}", 10, "primario_texto", True, TA_LEFT if i == 0 else TA_RIGHT))
           for i, h in enumerate(mod["columnas"])]
    celda = estilo("c", 9.5, "texto_secundario")
    celda_der = estilo("cd", 9.5, "texto_secundario", False, TA_RIGHT)
    celda_desc = estilo("cdd", 9.5, "peligro", True, TA_RIGHT)
    filas = [enc]
    for f in mod["filas"]:
        filas.append([Paragraph(_p(f[0]), celda), Paragraph(_p(f[1]), celda_der),
                      Paragraph(_p(f[2]), celda_der),
                      Paragraph(_p(f[3]), celda_desc if f[3] != "—" else
                                estilo("cds", 9.5, "texto_suave", False, TA_RIGHT)),
                      Paragraph(_p(f[4]), celda_der)])
    tabla = Table(filas, colWidths=[ancho - 11 * cm, 1.6 * cm, 3.4 * cm, 2.4 * cm, 3.6 * cm], repeatRows=1)
    tabla.setStyle(TableStyle([
        ("LINEBELOW", (0, 0), (-1, 0), 1.2, hexc("borde")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [hexc("superficie"), hexc("fondo")]),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ]))
    el += [tabla, Spacer(1, 0.2 * cm),
           HRFlowable(width="100%", thickness=0.8, color=hexc("borde")), Spacer(1, 0.15 * cm)]

    # Totales
    filas_t = []
    for etiqueta, valor, tipo in mod["totales"]:
        if tipo == "ahorro":
            el_, ev_ = estilo("ta", 10, "exito_texto", True, TA_RIGHT), estilo("tav", 10, "exito_texto", True, TA_RIGHT)
        else:
            el_, ev_ = estilo("tn", 10, "texto_suave", False, TA_RIGHT), estilo("tnv", 10, "texto_suave", False, TA_RIGHT)
        filas_t.append([Paragraph(_p(etiqueta), el_), Paragraph(_p(valor), ev_)])
    filas_t.append([Paragraph("TOTAL A PAGAR", estilo("tl", 12, "texto", True, TA_RIGHT)),
                    Paragraph(_p(mod["total"]), estilo("tv", 14, "primario_texto", True, TA_RIGHT))])
    tt = Table(filas_t, colWidths=[ancho - 4.5 * cm, 4.5 * cm])
    tt.setStyle(TableStyle([("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("RIGHTPADDING", (0, 0), (-1, -1), 4)]))
    el += [tt, Spacer(1, 0.3 * cm)]

    # Pago recibido
    if mod["pago"]:
        pk, pv = estilo("pk", 9.5, "texto_suave", True), estilo("pv", 9.5, "texto", True, TA_RIGHT)
        pc = estilo("pc", 9.5, "exito_texto", True, TA_RIGHT)
        caja = Table([[Paragraph("PAGO RECIBIDO", estilo("pt", 9, "exito_oscuro", True)), ""],
                      [Paragraph("Efectivo recibido", pk), Paragraph(_p(mod["pago"]["recibido"]), pv)],
                      [Paragraph("Cambio", pk), Paragraph(_p(mod["pago"]["cambio"]), pc)]],
                     colWidths=[ancho * 0.6, ancho * 0.4])
        caja.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), hexc("exito_fondo")),
                                  ("BOX", (0, 0), (-1, -1), 0.8, hexc("exito_borde")),
                                  ("SPAN", (0, 0), (1, 0)),
                                  ("LEFTPADDING", (0, 0), (-1, -1), 10), ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                                  ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
        el += [caja, Spacer(1, 0.4 * cm)]

    el += [Spacer(1, 0.2 * cm),
           Paragraph("Gracias por su compra", estilo("gr", 12, "texto_secundario", True, TA_CENTER)),
           Paragraph(_p(mod["pie"]), estilo("pie", 8.5, "texto_suave", False, TA_CENTER))]
    doc.build(el)
    return ruta


# -- abrir con el visor del SO -------------------------------------------------------------
def abrir_archivo(ruta: Path | str) -> bool:
    """Abre el archivo con la aplicacion predeterminada. Devuelve False si no se pudo."""
    try:
        sistema = platform.system()
        if sistema == "Windows":
            os.startfile(str(ruta))          # type: ignore[attr-defined]
        elif sistema == "Darwin":
            subprocess.Popen(["open", str(ruta)])
        else:
            subprocess.Popen(["xdg-open", str(ruta)])
        return True
    except Exception:  # noqa: BLE001  (no poder abrir el visor no es critico)
        return False
