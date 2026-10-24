"""Reglas de riesgo (RF-08/RF-09). Funciones puras: sin BD, sin reloj global."""
from datetime import datetime

from .entities import EvaluacionRiesgo, NivelRiesgo, PoliticaRiesgo, ProductoDominio

_ORDEN = {NivelRiesgo.NORMAL: 0, NivelRiesgo.MEDIO: 1, NivelRiesgo.ALTO: 2, NivelRiesgo.CRITICO: 3}

MOTIVO_VENCIDO = "Vencido"


def dias_para_vencer(p: ProductoDominio, ahora: datetime) -> int | None:
    """Diferencia en dias de calendario (vence manana = 1, hoy = 0, ayer = -1).
    None si no tiene fecha de vencimiento."""
    if p.fecha_vencimiento is None:
        return None
    return (p.fecha_vencimiento.date() - ahora.date()).days


def esta_vencido(p: ProductoDominio, ahora: datetime) -> bool:
    """Vencido solo cuando `ahora` supera estrictamente la fecha/hora de vencimiento."""
    return p.fecha_vencimiento is not None and ahora > p.fecha_vencimiento


def _por_vencimiento(p, pol, ahora) -> tuple[NivelRiesgo, str, float]:
    if esta_vencido(p, ahora):
        return NivelRiesgo.CRITICO, MOTIVO_VENCIDO, 0.0
    dias = dias_para_vencer(p, ahora)
    if dias is None:
        return NivelRiesgo.NORMAL, "", 0.0
    texto = "Vence hoy" if dias <= 0 else f"Vence en {dias} día(s)"
    if dias <= pol.dias_critico:
        return NivelRiesgo.CRITICO, texto, pol.descuento_critico
    if dias <= pol.dias_alerta:
        return NivelRiesgo.ALTO, texto, pol.descuento_alto
    return NivelRiesgo.NORMAL, "", 0.0


def _por_stock(p, pol) -> tuple[NivelRiesgo, str, float]:
    """Sobrestock (liquidacion, con descuento) y stock bajo (solo alerta) son casos distintos."""
    if p.stock_maximo and p.stock >= p.stock_maximo * pol.proporcion_sobrestock:
        return (NivelRiesgo.MEDIO, f"Sobrestock: {p.stock}/{p.stock_maximo} unidades",
                pol.descuento_sobrestock)
    if 0 < p.stock <= pol.umbral_stock_bajo:
        return NivelRiesgo.MEDIO, f"Stock bajo: {p.stock} unidades restantes", 0.0
    return NivelRiesgo.NORMAL, "", 0.0


def evaluar_producto(p: ProductoDominio, politica: PoliticaRiesgo,
                     ahora: datetime) -> EvaluacionRiesgo:
    n_v, m_v, d_v = _por_vencimiento(p, politica, ahora)
    n_s, m_s, d_s = _por_stock(p, politica)
    nivel = n_v if _ORDEN[n_v] >= _ORDEN[n_s] else n_s
    vencido = esta_vencido(p, ahora)
    # Un vencido no se vende (se retira): ningun descuento aplicable.
    descuento = 0.0 if vencido else max(d_v, d_s)
    motivo = " | ".join(m for m in (m_v, m_s) if m) or "Sin riesgo"
    return EvaluacionRiesgo(
        producto_id=p.id, nivel=nivel, motivo=motivo, descuento=descuento,
        precio_original=p.precio_base,
        precio_final=round(p.precio_base * (1 - descuento / 100), 2),
        dias_para_vencer=dias_para_vencer(p, ahora), vencido=vencido,
    )
