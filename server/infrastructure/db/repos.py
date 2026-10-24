"""Repositorios con sesion inyectada. Devuelven entidades de dominio o DTOs inmutables,
nunca objetos ORM. No hacen commit: la transaccion la controla quien abre la sesion."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import select, text, update
from sqlalchemy.orm import Session

from server.domain.entities import ProductoDominio

from .orm import (
    ConfiguracionORM, DescuentoORM, DetalleFacturaORM, FacturaORM, ProductoORM,
    SesionORM, UsuarioORM,
)
from .seed import CONFIG_POR_DEFECTO


# ── DTOs ───────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class UsuarioDTO:
    id: int
    nombre: str
    usuario: str
    password_hash: str
    rol: str
    activo: bool


@dataclass(frozen=True)
class DescuentoDTO:
    id: int
    producto_id: int
    porcentaje: float
    motivo: str
    activo: bool
    fecha_inicio: datetime
    fecha_fin: datetime | None


@dataclass(frozen=True)
class SesionDTO:
    id: int
    jti: str
    usuario_id: int
    creada: datetime
    ultima_actividad: datetime
    cerrada: bool
    motivo_cierre: str | None


@dataclass(frozen=True)
class DetalleDTO:
    producto_id: int
    nombre_producto: str
    cantidad: int
    precio_unitario: float
    descuento_pct: float
    precio_final: float
    subtotal: float


@dataclass(frozen=True)
class FacturaDTO:
    id: int
    numero: str
    fecha: datetime
    cliente_nombre: str
    cliente_documento: str
    metodo_pago: str
    subtotal: float
    ahorro: float
    iva: float
    total: float
    efectivo_recibido: float | None
    cambio: float | None
    usuario_id: int | None
    detalles: tuple[DetalleDTO, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class NuevaFactura:
    """Datos de entrada para crear una factura (el numero lo asigna el repositorio)."""
    metodo_pago: str
    subtotal: float
    ahorro: float
    iva: float
    total: float
    usuario_id: int | None
    detalles: tuple[DetalleDTO, ...]
    cliente_nombre: str = ""
    cliente_documento: str = ""
    efectivo_recibido: float | None = None
    cambio: float | None = None
    fecha: datetime | None = None


# ── Conversores ────────────────────────────────────────────────────────────
def _producto(o: ProductoORM) -> ProductoDominio:
    return ProductoDominio(
        id=o.id, nombre=o.nombre, categoria=o.categoria, precio_base=o.precio_base,
        stock=o.stock, stock_maximo=o.stock_maximo,
        fecha_vencimiento=o.fecha_vencimiento, activo=bool(o.activo),
    )


def _usuario(o: UsuarioORM) -> UsuarioDTO:
    return UsuarioDTO(o.id, o.nombre, o.usuario, o.password_hash, o.rol, bool(o.activo))


def _descuento(o: DescuentoORM) -> DescuentoDTO:
    return DescuentoDTO(o.id, o.producto_id, o.porcentaje, o.motivo, bool(o.activo),
                        o.fecha_inicio, o.fecha_fin)


def _sesion(o: SesionORM) -> SesionDTO:
    return SesionDTO(o.id, o.jti, o.usuario_id, o.creada, o.ultima_actividad,
                     bool(o.cerrada), o.motivo_cierre)


def _factura(o: FacturaORM) -> FacturaDTO:
    return FacturaDTO(
        id=o.id, numero=o.numero, fecha=o.fecha, cliente_nombre=o.cliente_nombre,
        cliente_documento=o.cliente_documento, metodo_pago=o.metodo_pago,
        subtotal=o.subtotal, ahorro=o.ahorro, iva=o.iva, total=o.total,
        efectivo_recibido=o.efectivo_recibido, cambio=o.cambio, usuario_id=o.usuario_id,
        detalles=tuple(
            DetalleDTO(d.producto_id, d.nombre_producto, d.cantidad, d.precio_unitario,
                       d.descuento_pct, d.precio_final, d.subtotal)
            for d in o.detalles
        ),
    )


# ── Repositorios ───────────────────────────────────────────────────────────
class ProductoRepo:
    def __init__(self, s: Session):
        self.s = s

    def listar_activos(self) -> list[ProductoDominio]:
        q = select(ProductoORM).where(ProductoORM.activo.is_(True)).order_by(ProductoORM.nombre)
        return [_producto(p) for p in self.s.scalars(q)]

    def obtener(self, id: int) -> ProductoDominio | None:
        o = self.s.get(ProductoORM, id)
        return _producto(o) if o else None

    def crear(self, p: ProductoDominio) -> ProductoDominio:
        o = ProductoORM(
            nombre=p.nombre, categoria=p.categoria, precio_base=p.precio_base,
            stock=p.stock, stock_maximo=p.stock_maximo,
            fecha_vencimiento=p.fecha_vencimiento, activo=p.activo,
        )
        self.s.add(o)
        self.s.flush()
        return _producto(o)

    def actualizar(self, p: ProductoDominio) -> ProductoDominio | None:
        o = self.s.get(ProductoORM, p.id)
        if o is None:
            return None
        o.nombre, o.categoria, o.precio_base = p.nombre, p.categoria, p.precio_base
        o.stock, o.stock_maximo = p.stock, p.stock_maximo
        o.fecha_vencimiento, o.activo = p.fecha_vencimiento, p.activo
        self.s.flush()
        return _producto(o)

    def baja_logica(self, id: int) -> bool:
        r = self.s.execute(update(ProductoORM).where(ProductoORM.id == id).values(activo=False))
        return r.rowcount > 0

    def descontar_stock_atomico(self, id: int, cantidad: int) -> bool:
        """UPDATE condicional: nunca deja stock negativo. False si no alcanza o no esta activo."""
        if cantidad <= 0:
            return False
        r = self.s.execute(
            update(ProductoORM)
            .where(ProductoORM.id == id, ProductoORM.activo.is_(True),
                   ProductoORM.stock >= cantidad)
            .values(stock=ProductoORM.stock - cantidad)
            .execution_options(synchronize_session=False)
        )
        return r.rowcount == 1

    def retirar_vencidos(self, ahora: datetime) -> list[ProductoDominio]:
        """Baja logica de productos activos ya vencidos. Devuelve los retirados."""
        q = select(ProductoORM).where(
            ProductoORM.activo.is_(True),
            ProductoORM.fecha_vencimiento.is_not(None),
            ProductoORM.fecha_vencimiento < ahora,
        )
        retirados = list(self.s.scalars(q))
        for o in retirados:
            o.activo = False
        self.s.flush()
        return [_producto(o) for o in retirados]


class DescuentoRepo:
    def __init__(self, s: Session):
        self.s = s

    def activo_de(self, producto_id: int) -> DescuentoDTO | None:
        q = (select(DescuentoORM)
             .where(DescuentoORM.producto_id == producto_id, DescuentoORM.activo.is_(True))
             .order_by(DescuentoORM.id.desc()))
        o = self.s.scalars(q).first()
        return _descuento(o) if o else None

    def listar_activos(self) -> list[DescuentoDTO]:
        q = select(DescuentoORM).where(DescuentoORM.activo.is_(True)).order_by(DescuentoORM.id)
        return [_descuento(o) for o in self.s.scalars(q)]

    def reemplazar_activo(self, producto_id: int, porcentaje: float, motivo: str,
                          fecha_fin: datetime | None = None) -> DescuentoDTO:
        """Desactiva los descuentos activos del producto y crea uno nuevo."""
        self.s.execute(
            update(DescuentoORM)
            .where(DescuentoORM.producto_id == producto_id, DescuentoORM.activo.is_(True))
            .values(activo=False)
        )
        o = DescuentoORM(producto_id=producto_id, porcentaje=porcentaje, motivo=motivo,
                         activo=True, fecha_inicio=datetime.now(), fecha_fin=fecha_fin)
        self.s.add(o)
        self.s.flush()
        return _descuento(o)

    def desactivar(self, producto_id: int) -> int:
        r = self.s.execute(
            update(DescuentoORM)
            .where(DescuentoORM.producto_id == producto_id, DescuentoORM.activo.is_(True))
            .values(activo=False)
        )
        return r.rowcount


class FacturaRepo:
    PREFIJO = "FAC-"

    def __init__(self, s: Session):
        self.s = s

    def siguiente_numero(self) -> str:
        """Consecutivo seguro: el UPDATE toma el bloqueo de escritura de SQLite y la
        asignacion queda ligada a la transaccion (si hace rollback, no se consume)."""
        self.s.execute(text("INSERT OR IGNORE INTO contadores (nombre, valor) VALUES ('factura', 0)"))
        n = self.s.execute(
            text("UPDATE contadores SET valor = valor + 1 WHERE nombre = 'factura' RETURNING valor")
        ).scalar_one()
        return f"{self.PREFIJO}{n:06d}"

    def crear(self, nf: NuevaFactura) -> FacturaDTO:
        o = FacturaORM(
            numero=self.siguiente_numero(), fecha=nf.fecha or datetime.now(),
            cliente_nombre=nf.cliente_nombre, cliente_documento=nf.cliente_documento,
            metodo_pago=nf.metodo_pago, subtotal=nf.subtotal, ahorro=nf.ahorro, iva=nf.iva,
            total=nf.total, efectivo_recibido=nf.efectivo_recibido, cambio=nf.cambio,
            usuario_id=nf.usuario_id,
            detalles=[DetalleFacturaORM(
                producto_id=d.producto_id, nombre_producto=d.nombre_producto,
                cantidad=d.cantidad, precio_unitario=d.precio_unitario,
                descuento_pct=d.descuento_pct, precio_final=d.precio_final,
                subtotal=d.subtotal) for d in nf.detalles],
        )
        self.s.add(o)
        self.s.flush()
        return _factura(o)

    def obtener_por_numero(self, numero: str) -> FacturaDTO | None:
        o = self.s.scalars(select(FacturaORM).where(FacturaORM.numero == numero)).first()
        return _factura(o) if o else None

    def listar(self, desde: datetime | None = None, hasta: datetime | None = None,
               usuario_id: int | None = None, limite: int | None = None,
               offset: int = 0) -> list[FacturaDTO]:
        q = select(FacturaORM)
        if desde is not None:
            q = q.where(FacturaORM.fecha >= desde)
        if hasta is not None:
            q = q.where(FacturaORM.fecha <= hasta)
        if usuario_id is not None:
            q = q.where(FacturaORM.usuario_id == usuario_id)
        q = q.order_by(FacturaORM.fecha.desc(), FacturaORM.id.desc()).offset(offset)
        if limite is not None:
            q = q.limit(limite)
        return [_factura(o) for o in self.s.scalars(q)]


class UsuarioRepo:
    def __init__(self, s: Session):
        self.s = s

    def obtener(self, id: int) -> UsuarioDTO | None:
        o = self.s.get(UsuarioORM, id)
        return _usuario(o) if o else None

    def obtener_por_usuario(self, usuario: str) -> UsuarioDTO | None:
        o = self.s.scalars(select(UsuarioORM).where(UsuarioORM.usuario == usuario)).first()
        return _usuario(o) if o else None

    def listar(self) -> list[UsuarioDTO]:
        return [_usuario(o) for o in self.s.scalars(select(UsuarioORM).order_by(UsuarioORM.id))]

    def crear(self, nombre: str, usuario: str, password_hash: str,
              rol: str = "comprador", activo: bool = True) -> UsuarioDTO:
        o = UsuarioORM(nombre=nombre, usuario=usuario, password_hash=password_hash,
                       rol=rol, activo=activo)
        self.s.add(o)
        self.s.flush()
        return _usuario(o)

    def actualizar(self, id: int, *, nombre: str | None = None, rol: str | None = None,
                   activo: bool | None = None, password_hash: str | None = None
                   ) -> UsuarioDTO | None:
        o = self.s.get(UsuarioORM, id)
        if o is None:
            return None
        if nombre is not None:
            o.nombre = nombre
        if rol is not None:
            o.rol = rol
        if activo is not None:
            o.activo = activo
        if password_hash is not None:
            o.password_hash = password_hash
        self.s.flush()
        return _usuario(o)


class SesionRepo:
    def __init__(self, s: Session):
        self.s = s

    def crear(self, jti: str, usuario_id: int, ahora: datetime | None = None) -> SesionDTO:
        ahora = ahora or datetime.now()
        o = SesionORM(jti=jti, usuario_id=usuario_id, creada=ahora, ultima_actividad=ahora,
                      cerrada=False)
        self.s.add(o)
        self.s.flush()
        return _sesion(o)

    def obtener_por_jti(self, jti: str) -> SesionDTO | None:
        o = self.s.scalars(select(SesionORM).where(SesionORM.jti == jti)).first()
        return _sesion(o) if o else None

    def tocar(self, jti: str, ahora: datetime | None = None) -> bool:
        """Actualiza ultima_actividad solo si la sesion sigue abierta."""
        r = self.s.execute(
            update(SesionORM).where(SesionORM.jti == jti, SesionORM.cerrada.is_(False))
            .values(ultima_actividad=ahora or datetime.now())
        )
        return r.rowcount == 1

    def cerrar(self, jti: str, motivo: str) -> bool:
        r = self.s.execute(
            update(SesionORM).where(SesionORM.jti == jti, SesionORM.cerrada.is_(False))
            .values(cerrada=True, motivo_cierre=motivo)
        )
        return r.rowcount == 1

    def cerrar_todas_de_usuario(self, usuario_id: int, motivo: str) -> int:
        r = self.s.execute(
            update(SesionORM)
            .where(SesionORM.usuario_id == usuario_id, SesionORM.cerrada.is_(False))
            .values(cerrada=True, motivo_cierre=motivo)
        )
        return r.rowcount

    def listar_abiertas(self) -> list[SesionDTO]:
        q = select(SesionORM).where(SesionORM.cerrada.is_(False)).order_by(SesionORM.id)
        return [_sesion(o) for o in self.s.scalars(q)]


class ConfigRepo:
    def __init__(self, s: Session):
        self.s = s

    def get(self, clave: str, defecto: str | None = None) -> str | None:
        o = self.s.get(ConfiguracionORM, clave)
        if o is not None:
            return o.valor
        return CONFIG_POR_DEFECTO.get(clave, defecto)

    def set(self, clave: str, valor: object) -> None:
        o = self.s.get(ConfiguracionORM, clave)
        if o is None:
            self.s.add(ConfiguracionORM(clave=clave, valor=str(valor)))
        else:
            o.valor = str(valor)
        self.s.flush()

    def todos(self) -> dict[str, str]:
        """Defaults mezclados con lo almacenado (lo almacenado gana)."""
        d = dict(CONFIG_POR_DEFECTO)
        for o in self.s.scalars(select(ConfiguracionORM)):
            d[o.clave] = o.valor
        return d
