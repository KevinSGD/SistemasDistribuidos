from datetime import datetime
from models import Producto, Descuento, NivelRiesgo
from database import get_session
from config import CONFIG

# ── Motor principal de detección de riesgo ─────────────────────────────────
class RiskEngine:

    def __init__(self):
        self.session = get_session()

    # ── 1. Calcular días hasta vencimiento ─────────────────────────────────
    def dias_para_vencer(self, producto: Producto) -> int | None:
        """Retorna los días restantes antes de vencer. None si no tiene vencimiento."""
        if producto.fecha_vencimiento is None:
            return None
        delta = producto.fecha_vencimiento - datetime.now()
        return delta.days

    # ── 2. Detectar nivel de riesgo por vencimiento ────────────────────────
    def riesgo_por_vencimiento(self, producto: Producto) -> tuple[str, str, float]:
        """
        Retorna (nivel, motivo, descuento) según días para vencer.
        """
        dias = self.dias_para_vencer(producto)

        if dias is None:
            return NivelRiesgo.NORMAL.value, "", 0.0

        if dias <= 0:
            return (
                NivelRiesgo.CRITICO.value,
                f"Producto VENCIDO hace {abs(dias)} días",
                CONFIG["descuento_critico"]
            )
        elif dias <= CONFIG["dias_critico_vencimiento"]:
            return (
                NivelRiesgo.CRITICO.value,
                f"Vence en {dias} día(s)",
                CONFIG["descuento_critico"]
            )
        elif dias <= CONFIG["dias_alerta_vencimiento"]:
            return (
                NivelRiesgo.ALTO.value,
                f"Vence en {dias} día(s)",
                CONFIG["descuento_alto"]
            )
        
        return NivelRiesgo.NORMAL.value, "", 0.0

    # ── 3. Detectar riesgo por sobrestock ──────────────────────────────────
    def riesgo_por_stock(self, producto: Producto) -> tuple[str, str, float]:
        """
        Retorna (nivel, motivo, descuento) si hay sobrestock.
        """
        if producto.stock_maximo and producto.stock >= producto.stock_maximo * 0.9:
            return (
                NivelRiesgo.MEDIO.value,
                f"Sobrestock: {producto.stock}/{producto.stock_maximo} unidades",
                CONFIG["descuento_sobrestock"]
            )
        elif producto.stock <= CONFIG["umbral_stock_bajo"] and producto.stock > 0:
            return (
                NivelRiesgo.MEDIO.value,
                f"Stock bajo: {producto.stock} unidades restantes",
                0.0  # Stock bajo no genera descuento, solo alerta
            )

        return NivelRiesgo.NORMAL.value, "", 0.0

    # ── 4. Evaluar un producto completo ────────────────────────────────────
    def evaluar_producto(self, producto: Producto) -> dict:
        """
        Evalúa todas las reglas de riesgo sobre un producto.
        Retorna un diccionario con el resultado completo.
        """
        nivel_venc,  motivo_venc,  desc_venc  = self.riesgo_por_vencimiento(producto)
        nivel_stock, motivo_stock, desc_stock = self.riesgo_por_stock(producto)

        # El nivel más grave gana
        niveles = [NivelRiesgo.NORMAL.value, NivelRiesgo.MEDIO.value,
                   NivelRiesgo.ALTO.value,   NivelRiesgo.CRITICO.value]

        nivel_final   = nivel_venc if niveles.index(nivel_venc) >= niveles.index(nivel_stock) else nivel_stock
        descuento_final = max(desc_venc, desc_stock)

        # Combinar motivos
        motivos = [m for m in [motivo_venc, motivo_stock] if m]
        motivo_final = " | ".join(motivos) if motivos else "Sin riesgo"

        # Precio con descuento
        precio_con_descuento = producto.precio_base * (1 - descuento_final / 100)

        return {
            "producto_id"        : producto.id,
            "nombre"             : producto.nombre,
            "categoria"          : producto.categoria,
            "nivel_riesgo"       : nivel_final,
            "motivo"             : motivo_final,
            "descuento_sugerido" : descuento_final,
            "precio_original"    : producto.precio_base,
            "precio_sugerido"    : round(precio_con_descuento, 2),
            "dias_para_vencer"   : self.dias_para_vencer(producto),
            "stock"              : producto.stock,
        }

    # ── 5. Eliminar productos vencidos ─────────────────────────────────────
    def eliminar_vencidos(self) -> list[str]:
        """
        Desactiva (soft-delete) todos los productos cuya fecha de
        vencimiento ya pasó. Retorna la lista de nombres eliminados.
        """
        ahora    = datetime.now()
        vencidos = self.session.query(Producto).filter(
            Producto.activo            == 1,
            Producto.fecha_vencimiento != None,
            Producto.fecha_vencimiento <= ahora
        ).all()

        nombres = []
        for p in vencidos:
            p.activo = 0
            nombres.append(p.nombre)

        if nombres:
            self.session.commit()

        return nombres

    # ── 6. Escanear todos los productos ────────────────────────────────────
    def escanear_inventario(self) -> dict:
        """
        Primero elimina vencidos, luego evalúa los productos activos y los
        agrupa por nivel de riesgo. Los nombres eliminados quedan en
        self.ultimos_eliminados para que la UI pueda notificarlos.
        """
        self.ultimos_eliminados = self.eliminar_vencidos()

        productos = self.session.query(Producto).filter(Producto.activo == 1).all()

        resultados = {
            NivelRiesgo.CRITICO.value : [],
            NivelRiesgo.ALTO.value    : [],
            NivelRiesgo.MEDIO.value   : [],
            NivelRiesgo.NORMAL.value  : [],
        }

        for producto in productos:
            evaluacion = self.evaluar_producto(producto)
            resultados[evaluacion["nivel_riesgo"]].append(evaluacion)

            # Actualizar nivel de riesgo en la BD
            producto.nivel_riesgo = evaluacion["nivel_riesgo"]

        self.session.commit()
        return resultados

    # ── 7. Aplicar descuentos automáticamente ──────────────────────────────
    def aplicar_descuentos(self, resultados: dict) -> int:
        """
        Crea registros de descuento en la BD para productos en riesgo.
        Retorna la cantidad de descuentos aplicados.
        """
        aplicados = 0
        niveles_con_descuento = [
            NivelRiesgo.CRITICO.value,
            NivelRiesgo.ALTO.value,
            NivelRiesgo.MEDIO.value
        ]

        for nivel in niveles_con_descuento:
            for item in resultados[nivel]:
                if item["descuento_sugerido"] > 0:

                    # Desactivar descuentos anteriores del mismo producto
                    self.session.query(Descuento).filter(
                        Descuento.producto_id == item["producto_id"],
                        Descuento.activo == 1
                    ).update({"activo": 0})

                    # Crear nuevo descuento
                    nuevo_descuento = Descuento(
                        producto_id = item["producto_id"],
                        porcentaje  = item["descuento_sugerido"],
                        motivo      = item["motivo"],
                        activo      = 1
                    )
                    self.session.add(nuevo_descuento)
                    aplicados += 1

        self.session.commit()
        return aplicados

    def cerrar(self):
        self.session.close()