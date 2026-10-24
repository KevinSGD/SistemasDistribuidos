"""Modelos ORM (SQLAlchemy 2.0 declarativo). Nunca salen de la capa de repositorios."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean, CheckConstraint, DateTime, Float, ForeignKey, Index, Integer, String, Text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class UsuarioORM(Base):
    __tablename__ = "usuarios"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    nombre: Mapped[str] = mapped_column(String(100))
    usuario: Mapped[str] = mapped_column(String(50), unique=True)
    # Hash autodescriptivo: "$argon2id$..." o "sha256$<hex>" (legacy, a re-hashear).
    password_hash: Mapped[str] = mapped_column(String(255))
    rol: Mapped[str] = mapped_column(String(20), default="comprador")
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    creado: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class ProductoORM(Base):
    __tablename__ = "productos"
    __table_args__ = (
        CheckConstraint("precio_base >= 0", name="ck_producto_precio_base"),
        CheckConstraint("stock >= 0", name="ck_producto_stock"),
        CheckConstraint("stock_maximo >= 0", name="ck_producto_stock_maximo"),
        Index("ix_productos_activo_vencimiento", "activo", "fecha_vencimiento"),
        Index("ix_productos_nombre", "nombre"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    nombre: Mapped[str] = mapped_column(String(100))
    categoria: Mapped[str] = mapped_column(String(50))
    precio_base: Mapped[float] = mapped_column(Float)
    stock: Mapped[int] = mapped_column(Integer, default=0)
    stock_maximo: Mapped[int] = mapped_column(Integer, default=100)
    fecha_vencimiento: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    fecha_ingreso: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)


class DescuentoORM(Base):
    __tablename__ = "descuentos"
    __table_args__ = (
        CheckConstraint("porcentaje >= 0 AND porcentaje <= 100", name="ck_descuento_porcentaje"),
        Index("ix_descuentos_producto_activo", "producto_id", "activo"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    producto_id: Mapped[int] = mapped_column(ForeignKey("productos.id"))
    porcentaje: Mapped[float] = mapped_column(Float)
    motivo: Mapped[str] = mapped_column(String(200))
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    fecha_inicio: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    fecha_fin: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class FacturaORM(Base):
    __tablename__ = "facturas"
    __table_args__ = (
        CheckConstraint("subtotal >= 0 AND ahorro >= 0 AND iva >= 0 AND total >= 0",
                        name="ck_factura_montos"),
        Index("ix_facturas_fecha", "fecha"),
        Index("ix_facturas_usuario_fecha", "usuario_id", "fecha"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    numero: Mapped[str] = mapped_column(String(30), unique=True)
    fecha: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    cliente_nombre: Mapped[str] = mapped_column(String(150), default="")
    cliente_documento: Mapped[str] = mapped_column(String(50), default="")
    metodo_pago: Mapped[str] = mapped_column(String(30))
    subtotal: Mapped[float] = mapped_column(Float)  # sin descuento
    ahorro: Mapped[float] = mapped_column(Float, default=0.0)
    iva: Mapped[float] = mapped_column(Float, default=0.0)
    total: Mapped[float] = mapped_column(Float)
    efectivo_recibido: Mapped[float | None] = mapped_column(Float, nullable=True)
    cambio: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Nulo solo en facturas historicas migradas (legacy no registraba al usuario).
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"), nullable=True)

    detalles: Mapped[list["DetalleFacturaORM"]] = relationship(
        back_populates="factura", cascade="all, delete-orphan", order_by="DetalleFacturaORM.id"
    )


class DetalleFacturaORM(Base):
    __tablename__ = "detalle_factura"
    __table_args__ = (
        CheckConstraint("cantidad > 0", name="ck_detalle_cantidad"),
        CheckConstraint("descuento_pct >= 0 AND descuento_pct <= 100", name="ck_detalle_descuento"),
        CheckConstraint("precio_unitario >= 0 AND precio_final >= 0 AND subtotal >= 0",
                        name="ck_detalle_montos"),
        Index("ix_detalle_factura", "factura_id"),
        Index("ix_detalle_producto", "producto_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    factura_id: Mapped[int] = mapped_column(ForeignKey("facturas.id"))
    producto_id: Mapped[int] = mapped_column(ForeignKey("productos.id"))
    nombre_producto: Mapped[str] = mapped_column(String(100))  # snapshot
    cantidad: Mapped[int] = mapped_column(Integer)
    precio_unitario: Mapped[float] = mapped_column(Float)  # precio base
    descuento_pct: Mapped[float] = mapped_column(Float, default=0.0)
    precio_final: Mapped[float] = mapped_column(Float)  # unitario con descuento
    subtotal: Mapped[float] = mapped_column(Float)  # precio_final * cantidad

    factura: Mapped[FacturaORM] = relationship(back_populates="detalles")


class SesionORM(Base):
    __tablename__ = "sesiones"
    __table_args__ = (Index("ix_sesiones_usuario_cerrada", "usuario_id", "cerrada"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    jti: Mapped[str] = mapped_column(String(64), unique=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"))
    creada: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    ultima_actividad: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    cerrada: Mapped[bool] = mapped_column(Boolean, default=False)
    motivo_cierre: Mapped[str | None] = mapped_column(String(50), nullable=True)


class ConfiguracionORM(Base):
    __tablename__ = "configuracion"

    clave: Mapped[str] = mapped_column(String(100), primary_key=True)
    valor: Mapped[str] = mapped_column(Text)


class ContadorORM(Base):
    """Contadores atomicos (p. ej. consecutivo de facturas)."""
    __tablename__ = "contadores"

    nombre: Mapped[str] = mapped_column(String(50), primary_key=True)
    valor: Mapped[int] = mapped_column(Integer, default=0)
