"""
Generador de facturas PDF.
Recibe el mismo dict `datos_factura` que usa InvoicePreviewDialog.
"""
from pathlib import Path

from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle,
    Paragraph, Spacer, HRFlowable
)
from config import REPORTS_DIR, CONFIG


def generar_factura(datos: dict) -> Path:
    """
    Genera el PDF de la factura y lo guarda en REPORTS_DIR.

    Parámetro `datos` — mismo dict que usa InvoicePreviewDialog:
        numero, fecha, usuario, carrito,
        monto_recibido, cambio,
        subtotal_orig, total_desc, ahorro
    """
    numero    = datos["numero"]
    fecha     = datos["fecha"]
    usuario   = datos["usuario"]
    carrito   = datos["carrito"]
    monto_rec = datos["monto_recibido"]
    cambio    = datos["cambio"]
    sub_orig  = datos["subtotal_orig"]
    total_d   = datos["total_desc"]
    ahorro    = datos["ahorro"]

    negocio = CONFIG.get("nombre_negocio", "Inventario App")
    nit     = CONFIG.get("nit", "N/A")
    dir_neg = CONFIG.get("direccion", "")
    m       = CONFIG.get("moneda", "$")

    nombre_pdf = f"factura_{numero}.pdf"
    ruta       = REPORTS_DIR / nombre_pdf

    doc = SimpleDocTemplate(
        str(ruta),
        pagesize=letter,
        leftMargin=2*cm, rightMargin=2*cm,
        topMargin=2*cm,  bottomMargin=2*cm,
    )

    estilos = getSampleStyleSheet()

    # ── Estilos personalizados ────────────────────────────────────────────
    def estilo(nombre, base="Normal", **kw):
        return ParagraphStyle(nombre, parent=estilos[base], **kw)

    st_neg    = estilo("neg",    fontSize=22, fontName="Helvetica-Bold",
                       textColor=colors.HexColor("#1E40AF"), alignment=TA_LEFT)
    st_sub    = estilo("sub",    fontSize=11, fontName="Helvetica",
                       textColor=colors.HexColor("#6B7280"), alignment=TA_LEFT)
    st_campo  = estilo("campo",  fontSize=9,  fontName="Helvetica-Bold",
                       textColor=colors.HexColor("#374151"))
    st_valor  = estilo("valor",  fontSize=9,  fontName="Helvetica",
                       textColor=colors.HexColor("#111827"))
    st_gris   = estilo("gris",   fontSize=9,  fontName="Helvetica",
                       textColor=colors.HexColor("#6B7280"), alignment=TA_RIGHT)
    st_verde  = estilo("verde",  fontSize=9,  fontName="Helvetica-Bold",
                       textColor=colors.HexColor("#16A34A"), alignment=TA_RIGHT)
    st_total_l= estilo("tl",     fontSize=13, fontName="Helvetica-Bold",
                       textColor=colors.HexColor("#111827"), alignment=TA_RIGHT)
    st_total_v= estilo("tv",     fontSize=15, fontName="Helvetica-Bold",
                       textColor=colors.HexColor("#1E40AF"), alignment=TA_RIGHT)
    st_pago_t = estilo("pt",     fontSize=9,  fontName="Helvetica-Bold",
                       textColor=colors.HexColor("#166534"), alignment=TA_LEFT)
    st_pago_l = estilo("pl",     fontSize=9,  fontName="Helvetica",
                       textColor=colors.HexColor("#374151"))
    st_cambio = estilo("cam",    fontSize=9,  fontName="Helvetica-Bold",
                       textColor=colors.HexColor("#16A34A"), alignment=TA_RIGHT)
    st_footer = estilo("foot",   fontSize=9,  fontName="Helvetica",
                       textColor=colors.HexColor("#9CA3AF"), alignment=TA_CENTER)
    st_gracias= estilo("grac",   fontSize=13, fontName="Helvetica-Bold",
                       textColor=colors.HexColor("#374151"), alignment=TA_CENTER)

    elementos = []

    # ── Encabezado ────────────────────────────────────────────────────────
    elementos += [
        Paragraph(negocio, st_neg),
        Paragraph("Factura de Venta", st_sub),
        Spacer(1, 0.3*cm),
        HRFlowable(width="100%", thickness=2, color=colors.HexColor("#1E40AF")),
        Spacer(1, 0.4*cm),
    ]

    # ── Datos de factura + cliente ────────────────────────────────────────
    cab_datos = [
        [Paragraph("No. Factura", st_campo), Paragraph(numero, st_valor),
         Paragraph(""),
         Paragraph("Cliente", st_campo),  Paragraph(usuario.nombre, st_valor)],
        [Paragraph("Fecha", st_campo), Paragraph(fecha.strftime("%d/%m/%Y"), st_valor),
         Paragraph(""),
         Paragraph("Usuario", st_campo), Paragraph(usuario.usuario, st_valor)],
        [Paragraph("Hora",  st_campo), Paragraph(fecha.strftime("%H:%M:%S"), st_valor),
         Paragraph(""), Paragraph(""), Paragraph("")],
    ]
    tbl_cab = Table(cab_datos, colWidths=[2.8*cm, 4.5*cm, 0.8*cm, 2.8*cm, 4.5*cm])
    tbl_cab.setStyle(TableStyle([
        ("VALIGN",      (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING",  (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING",(0,0), (-1, -1), 4),
        ("ROWBACKGROUNDS", (0,0), (-1,-1), [colors.white, colors.HexColor("#F9FAFB")]),
    ]))
    elementos += [tbl_cab, Spacer(1, 0.4*cm),
                  HRFlowable(width="100%", thickness=0.5,
                             color=colors.HexColor("#E5E7EB")),
                  Spacer(1, 0.4*cm)]

    # ── Tabla de productos ────────────────────────────────────────────────
    enc_tbl = ["#", "Producto", "Cant.", "Precio unit.",
               "Descuento", "P. c/desc.", "Subtotal"]
    filas   = [enc_tbl]

    for idx, (pid, entrada) in enumerate(carrito.items(), 1):
        item     = entrada["item"]
        cantidad = entrada["cantidad"]
        sub      = item["precio_sugerido"] * cantidad
        filas.append([
            str(idx),
            item["nombre"],
            str(cantidad),
            f"{m}{item['precio_original']:,.0f}",
            f"-{item['descuento_sugerido']:.0f}%",
            f"{m}{item['precio_sugerido']:,.2f}",
            f"{m}{sub:,.2f}",
        ])

    col_w = [0.7*cm, 4.5*cm, 1.2*cm, 2.5*cm, 2*cm, 2.5*cm, 2.5*cm]
    tbl_prod = Table(filas, colWidths=col_w, repeatRows=1)
    tbl_prod.setStyle(TableStyle([
        ("BACKGROUND",   (0,0), (-1,0), colors.HexColor("#1E40AF")),
        ("TEXTCOLOR",    (0,0), (-1,0), colors.white),
        ("FONTNAME",     (0,0), (-1,0), "Helvetica-Bold"),
        ("FONTSIZE",     (0,0), (-1,-1), 8),
        ("ALIGN",        (0,0), (0,-1), "CENTER"),
        ("ALIGN",        (2,0), (2,-1), "CENTER"),
        ("ALIGN",        (3,0), (-1,-1), "RIGHT"),
        ("ALIGN",        (4,1), (4,-1), "CENTER"),
        ("TOPPADDING",   (0,0), (-1,-1), 7),
        ("BOTTOMPADDING",(0,0), (-1,-1), 7),
        ("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.white, colors.HexColor("#F9FAFB")]),
        ("GRID",         (0,0), (-1,-1), 0.4, colors.HexColor("#E5E7EB")),
        ("TEXTCOLOR",    (4,1), (4,-1), colors.HexColor("#DC2626")),
        ("FONTNAME",     (4,1), (4,-1), "Helvetica-Bold"),
    ]))
    elementos += [tbl_prod, Spacer(1, 0.5*cm)]

    # ── Resumen de totales ────────────────────────────────────────────────
    ancho_l = 11.5*cm
    ancho_v = 4*cm

    resumen = [
        [Paragraph("Subtotal sin descuento:", st_gris),
         Paragraph(f"{m}{sub_orig:,.2f}", st_gris)],
        [Paragraph("Ahorro total:", st_verde),
         Paragraph(f"- {m}{ahorro:,.2f}", st_verde)],
    ]
    tbl_res = Table(resumen, colWidths=[ancho_l, ancho_v])
    tbl_res.setStyle(TableStyle([
        ("TOPPADDING",    (0,0), (-1,-1), 4),
        ("BOTTOMPADDING", (0,0), (-1,-1), 4),
    ]))
    elementos.append(tbl_res)
    elementos.append(HRFlowable(width="100%", thickness=1.5,
                                color=colors.HexColor("#1E40AF")))
    elementos.append(Spacer(1, 0.1*cm))

    tbl_total = Table(
        [[Paragraph("TOTAL A PAGAR:", st_total_l),
          Paragraph(f"{m}{total_d:,.2f}", st_total_v)]],
        colWidths=[ancho_l, ancho_v]
    )
    tbl_total.setStyle(TableStyle([
        ("TOPPADDING",    (0,0), (-1,-1), 6),
        ("BOTTOMPADDING", (0,0), (-1,-1), 6),
    ]))
    elementos += [tbl_total, Spacer(1, 0.5*cm)]

    # ── Sección de pago ───────────────────────────────────────────────────
    pago_filas = [
        [Paragraph("PAGO RECIBIDO", st_pago_t), Paragraph("")],
        [Paragraph("Efectivo recibido:", st_pago_l),
         Paragraph(f"{m}{monto_rec:,.2f}", st_valor)],
        [Paragraph("Cambio:", st_pago_l),
         Paragraph(f"{m}{cambio:,.2f}", st_cambio)],
    ]
    tbl_pago = Table(pago_filas, colWidths=[ancho_l, ancho_v])
    tbl_pago.setStyle(TableStyle([
        ("BACKGROUND",    (0,0), (-1,-1), colors.HexColor("#F0FDF4")),
        ("BOX",           (0,0), (-1,-1), 0.5, colors.HexColor("#BBF7D0")),
        ("TOPPADDING",    (0,0), (-1,-1), 5),
        ("BOTTOMPADDING", (0,0), (-1,-1), 5),
        ("LEFTPADDING",   (0,0), (-1,-1), 8),
        ("RIGHTPADDING",  (0,0), (-1,-1), 8),
        ("SPAN",          (0,0), (1,0)),
    ]))
    elementos += [tbl_pago, Spacer(1, 0.6*cm)]

    # ── Pie de página ────────────────────────────────────────────────────
    elementos += [
        HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#E5E7EB")),
        Spacer(1, 0.3*cm),
        Paragraph("Gracias por su compra", st_gracias),
        Spacer(1, 0.15*cm),
        Paragraph(f"{negocio}  ·  {dir_neg}  ·  NIT: {nit}", st_footer),
        Paragraph(
            f"Documento generado el {fecha.strftime('%d/%m/%Y a las %H:%M:%S')}",
            st_footer
        ),
    ]

    doc.build(elementos)
    return ruta
