"""VentaService: compra atomica (una transaccion) y consulta de facturas."""
from __future__ import annotations

from datetime import datetime
from typing import Callable

from server.domain.errors import NoEncontrado, StockInsuficiente
from server.domain.facturacion import calcular_pago, calcular_totales
from server.domain.riesgo import evaluar_producto
from server.domain.ventas import calcular_linea, validar_linea
from server.infrastructure.db.engine import sesion
from server.infrastructure.db.repos import (
    DetalleDTO, FacturaDTO, FacturaRepo, NuevaFactura, ProductoRepo,
)

from .config_service import ConfigService
from .errores import ROL_ADMIN, ROL_COMPRADOR, ErrorValidacion, exigir_admin, exigir_autenticado
from .eventos import FACTURA_CREADA, STOCK_ACTUALIZADO, EventBus, evento

LIMITE_DEFECTO = 200
LIMITE_MAXIMO = 1000
EFECTIVO = "efectivo"
TARJETA = "tarjeta_simulada"
METODOS = (EFECTIVO, TARJETA)


def factura_a_dict(f: FacturaDTO, negocio: dict) -> dict:
    return {
        "numero": f.numero, "fecha": f.fecha.isoformat(), "negocio": negocio,
        "cliente": {"nombre": f.cliente_nombre, "documento": f.cliente_documento},
        "items": [{
            "producto_id": d.producto_id, "nombre": d.nombre_producto, "cantidad": d.cantidad,
            "precio_original": d.precio_unitario, "descuento_pct": d.descuento_pct,
            "precio_final": d.precio_final, "subtotal": d.subtotal,
        } for d in f.detalles],
        "subtotal": f.subtotal, "ahorro": f.ahorro, "iva": f.iva, "total": f.total,
        "metodo_pago": f.metodo_pago, "efectivo_recibido": f.efectivo_recibido,
        "cambio": f.cambio, "usuario_id": f.usuario_id,
        "usuario_nombre": f.usuario_nombre,
    }


def _consolidar(items) -> dict[int, int]:
    if not isinstance(items, (list, tuple)) or not items:
        raise ErrorValidacion("La compra no tiene líneas")
    out: dict[int, int] = {}
    for it in items:
        try:
            pid, cant = it["producto_id"], it["cantidad"]
        except (KeyError, TypeError):
            raise ErrorValidacion("Cada línea requiere producto_id y cantidad") from None
        if isinstance(pid, bool) or not isinstance(pid, int):
            raise ErrorValidacion("producto_id inválido", {"producto_id": pid})
        if isinstance(cant, bool) or not isinstance(cant, int) or cant <= 0:
            raise ErrorValidacion("La cantidad debe ser un entero mayor que 0",
                                  {"producto_id": pid, "solicitado": cant})
        out[pid] = out.get(pid, 0) + cant
    return out


class VentaService:
    def __init__(self, sesion_factory, config: ConfigService, bus: EventBus | None = None,
                 reloj: Callable[[], datetime] = datetime.now):
        self._factory = sesion_factory
        self._config = config
        self._bus = bus
        self._reloj = reloj

    def _negocio(self, cfg: dict) -> dict:
        return {k: cfg[k] for k in ("nombre_negocio", "nit", "direccion", "telefono", "moneda")}

    def comprar(self, usuario_id: int, items: list[dict], cliente: dict | None,
                pago: dict | None, rol: str | None = ROL_COMPRADOR) -> dict:
        exigir_autenticado(rol)
        lineas_pedidas = _consolidar(items)
        cliente = cliente or {}
        nombre = str(cliente.get("nombre") or "").strip()[:150]
        documento = str(cliente.get("documento") or "").strip()[:50]
        pago = pago or {}
        metodo = pago.get("metodo")
        if metodo not in METODOS:
            raise ErrorValidacion("Método de pago inválido", {"validos": list(METODOS)})
        efectivo = pago.get("efectivo_recibido")
        if metodo == EFECTIVO:
            if (efectivo is None or isinstance(efectivo, bool)
                    or not isinstance(efectivo, (int, float))):
                raise ErrorValidacion("efectivo_recibido es obligatorio para pago en efectivo")

        cfg = self._config.valores()
        politica = self._config.politica_riesgo()
        tasa = float(cfg["iva_pct"])
        dec = politica.decimales_moneda
        ahora = self._reloj()
        cambiadas: list[int] = []

        with sesion(self._factory) as s:      # <- UNA transaccion: todo o nada
            prod = ProductoRepo(s)
            calculadas = []
            for pid, cant in lineas_pedidas.items():
                p = prod.obtener(pid)
                if p is None:
                    raise NoEncontrado("Producto no encontrado", {"producto_id": pid})
                validar_linea(p, cant, ahora)
                ev = evaluar_producto(p, politica, ahora)
                calculadas.append(calcular_linea(p, cant, ev, tasa, dec))
            totales = calcular_totales(calculadas, dec)
            totales = calcular_pago(totales, float(efectivo), dec) if metodo == EFECTIVO else totales

            for l in calculadas:      # el descuento condicional es la defensa real anti-sobreventa
                if not prod.descontar_stock_atomico(l.producto_id, l.cantidad):
                    actual = prod.stock_fresco(l.producto_id)
                    raise StockInsuficiente(
                        f"Stock insuficiente para '{l.nombre}'",
                        {"producto_id": l.producto_id, "disponible": actual or 0,
                         "solicitado": l.cantidad})
                cambiadas.append(l.producto_id)

            factura = FacturaRepo(s).crear(NuevaFactura(
                metodo_pago=metodo, subtotal=totales.subtotal_sin_descuento,
                ahorro=totales.ahorro, iva=totales.iva, total=totales.total,
                usuario_id=usuario_id, cliente_nombre=nombre, cliente_documento=documento,
                efectivo_recibido=totales.efectivo if metodo == EFECTIVO else None,
                cambio=totales.cambio if metodo == EFECTIVO else 0.0, fecha=ahora,
                detalles=tuple(DetalleDTO(
                    l.producto_id, l.nombre, l.cantidad, l.precio_original, l.descuento,
                    l.precio_unitario, l.subtotal) for l in calculadas)))
            stocks = {pid: prod.stock_fresco(pid) for pid in cambiadas}

        if self._bus is not None:
            for pid, stock in stocks.items():
                self._bus.publicar(evento(STOCK_ACTUALIZADO, {
                    "producto_id": pid, "stock": stock, "activo": True}))
            # Solo para el admin (refresco en vivo de su pantalla de facturas); tras el commit.
            self._bus.publicar(evento(FACTURA_CREADA, {
                "numero": factura.numero, "total": factura.total,
                "metodo_pago": factura.metodo_pago}, para="admin"))
        return factura_a_dict(factura, self._negocio(cfg))

    def obtener_factura(self, numero: str, usuario_id: int, rol: str | None) -> dict:
        exigir_autenticado(rol)
        with sesion(self._factory) as s:
            f = FacturaRepo(s).obtener_por_numero(numero)
        # 404 (no 403) para no revelar la existencia de facturas ajenas
        if f is None or (rol != ROL_ADMIN and f.usuario_id != usuario_id):
            raise NoEncontrado("Factura no encontrada", {"numero": numero})
        return factura_a_dict(f, self._negocio(self._config.valores()))

    @staticmethod
    def _filtro_usuario(usuario_id: int, rol: str | None, filtro_usuario: int | None):
        """Comprador: siempre solo las suyas (se ignora `filtro_usuario`). Admin: opcional."""
        return filtro_usuario if rol == ROL_ADMIN else usuario_id

    @staticmethod
    def _validar_metodo(metodo_pago: str | None) -> str | None:
        if metodo_pago in (None, ""):
            return None
        if metodo_pago not in METODOS:
            raise ErrorValidacion("Método de pago inválido", {"validos": list(METODOS)})
        return metodo_pago

    def listar_facturas(self, usuario_id: int, rol: str | None,
                        desde: datetime | None = None, hasta: datetime | None = None,
                        limite: int | None = None, offset: int = 0, q: str | None = None,
                        metodo_pago: str | None = None,
                        filtro_usuario_id: int | None = None) -> list[dict]:
        """Historial, mas recientes primero. Lectura solamente: las facturas son inmutables."""
        exigir_autenticado(rol)
        limite = LIMITE_DEFECTO if limite is None else limite
        if isinstance(limite, bool) or not 1 <= limite <= LIMITE_MAXIMO:
            raise ErrorValidacion(f"limite debe estar entre 1 y {LIMITE_MAXIMO}", {"limite": limite})
        if isinstance(offset, bool) or offset < 0:
            raise ErrorValidacion("offset debe ser >= 0", {"offset": offset})
        metodo_pago = self._validar_metodo(metodo_pago)
        filtro = self._filtro_usuario(usuario_id, rol, filtro_usuario_id)
        with sesion(self._factory) as s:
            fs = FacturaRepo(s).listar(desde, hasta, filtro, limite, offset, q, metodo_pago)
        negocio = self._negocio(self._config.valores())
        return [factura_a_dict(f, negocio) for f in fs]

    def resumen_facturas(self, rol: str | None, desde: datetime | None = None,
                         hasta: datetime | None = None, q: str | None = None,
                         metodo_pago: str | None = None,
                         filtro_usuario_id: int | None = None) -> dict:
        """Totales agregados (solo admin) con los mismos filtros que listar_facturas."""
        exigir_admin(rol)
        metodo_pago = self._validar_metodo(metodo_pago)
        with sesion(self._factory) as s:
            return FacturaRepo(s).resumen(desde, hasta, filtro_usuario_id, q, metodo_pago)
