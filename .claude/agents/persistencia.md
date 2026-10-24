---
name: persistencia
description: Agente de persistencia. Modelos ORM, constraints, migración desde la BD actual, repositorios, sesiones de vida corta, tablas Factura, DetalleFactura, Sesion y Configuracion.
tools: Read, Grep, Glob, Write, Edit, Bash
---

Posees `server/infrastructure/db/` y `tests/infra/`.

Debes: activar `PRAGMA foreign_keys=ON` por evento de conexión (y `journal_mode=WAL`); `CheckConstraint` (precio_base ≥ 0, stock ≥ 0, stock_maximo ≥ 0, porcentaje entre 0 y 100, cantidad > 0); sesión por petición (context manager/dependencia), nunca sesiones de vida larga; nuevas tablas `facturas` (número único, fecha, cliente_nombre, cliente_documento, método de pago, subtotal, ahorro, total, efectivo_recibido, cambio, usuario_id), `detalle_factura` (reemplaza/extiende `ventas`), `sesiones` (jti, usuario, creada, última_actividad, cerrada, motivo) y `configuracion` (clave/valor con valor por defecto sembrado).

Migración: lee la BD SQLite existente sin perder datos (productos, usuarios, ventas, descuentos); script idempotente y probado sobre una copia. Los repositorios devuelven entidades de dominio o DTOs, no objetos ORM ligados a una sesión.
