# Contrato API — InventarioApp (versión implementada)

Base: `http://<host>:8000/api/v1`. JSON UTF-8. Auth: `Authorization: Bearer <JWT>` salvo `/auth/login` y `/health`.

## Errores
`{"codigo": "STOCK_INSUFICIENTE", "mensaje": "...", "detalle": {...}}`

| HTTP | codigo | Cuándo |
|---|---|---|
| 401 | `CREDENCIALES_INVALIDAS` / `TOKEN_INVALIDO` / `SESION_INACTIVA` / `SESION_CERRADA` | auth |
| 403 | `ROL_NO_PERMITIDO` | rol insuficiente |
| 404 | `NO_ENCONTRADO` | recurso inexistente |
| 409 | `STOCK_INSUFICIENTE` / `PRODUCTO_VENCIDO` / `PRODUCTO_INACTIVO` | compra inválida |
| 409 | `USUARIO_DUPLICADO` | crear usuario con un nombre de usuario ya existente |
| 422 | `VALIDACION` | datos mal formados, rangos de configuración, contraseña < 8 caracteres. `detalle.errores` lista `{campo, mensaje, tipo}` en errores de forma |
| 422 | `EFECTIVO_INSUFICIENTE` | pago en efectivo menor que el total (`detalle`: total, efectivo, faltante) |
| 429 | `TOO_MANY_ATTEMPTS` | 5 logins fallidos por usuario → bloqueo 60 s. `detalle.reintentar_en_segundos` y cabecera `Retry-After` |
| 500 | `ERROR_INTERNO` | error no controlado (sin detalles internos) |

Rutas inexistentes responden 404 `NO_ENCONTRADO` y métodos no admitidos 405 `METODO_NO_PERMITIDO` con el mismo formato. Los modelos de petición/respuesta están en `shared/schemas.py`.

## Autenticación y sesión
| Método | Ruta | Rol | Descripción |
|---|---|---|---|
| POST | `/auth/login` | público | `{usuario, password}` → `{token, expira_en, usuario{id,nombre,rol}, sesion{inactividad_segundos, aviso_segundos}}` |
| POST | `/auth/actividad` | autenticado | Renueva `ultima_actividad`. Solo lo llama el cliente ante input real del usuario (throttle ~10 s). Devuelve `{segundos_restantes}` |
| GET | `/auth/sesion` | autenticado | Estado sin renovar: `{segundos_restantes, inactividad_segundos, aviso_segundos}` |
| POST | `/auth/logout` | autenticado | Revoca la sesión |

Regla: ninguna otra ruta ni el WebSocket renuevan `ultima_actividad`. Al validar cada petición se lee `inactividad_segundos` vigente de configuración, por lo que un cambio del admin aplica también a sesiones abiertas.

## Productos (escritura admin; `GET /productos` y `/ofertas` también comprador)
| Método | Ruta | Descripción |
|---|---|---|
| GET | `/productos?activos=true` | Lista de inventario (admin y comprador; `activos=false` solo inactivos, omitir = activos) |
| POST | `/productos` | Crear (201) |
| PUT | `/productos/{id}` | Editar |
| DELETE | `/productos/{id}` | Baja lógica (204) |
| GET | `/ofertas` | (comprador/admin) productos con descuento activo, con precio final y motivo |

## Riesgo (admin)
| Método | Ruta | Descripción |
|---|---|---|
| GET | `/riesgo/resumen` | Conteos por nivel + lista de atención (dashboard) |
| GET | `/riesgo/alertas` | Productos agrupados por severidad |
| POST | `/riesgo/escaneo` | Fuerza un escaneo; devuelve retirados y descuentos aplicados |

## Ventas / facturas (comprador y admin)
| Método | Ruta | Descripción |
|---|---|---|
| POST | `/compras` | `{items:[{producto_id,cantidad}], cliente{nombre,documento}, pago{metodo, efectivo_recibido}}` → factura completa (201). `metodo`: `efectivo` \| `tarjeta_simulada`. Atómico; falla entero si algún ítem es inválido |
| GET | `/facturas/{numero}` | Datos de factura para vista previa y PDF |
| GET | `/facturas?desde=&hasta=&limite=` | Historial (fechas ISO 8601) (admin: todas; comprador: las suyas) |

La factura incluye: número consecutivo, fecha/hora, datos del negocio (de configuración), cliente, ítems (precio original, % descuento, precio final, subtotal), subtotal sin descuento, ahorro, total, método de pago, efectivo recibido y cambio.

## Configuración (admin escribe; resto lee lo que necesita)
| Método | Ruta | Descripción |
|---|---|---|
| GET | `/config` | Toda la configuración (admin) |
| PUT | `/config` | Cuerpo: objeto con solo las claves a cambiar. Validadas por rango y reglas cruzadas (422 `VALIDACION`). Emite `config_cambiada` y devuelve la configuración completa |
| GET | `/config/publica` | Moneda, datos del negocio e `iva_pct` (todos los roles) |

Claves nuevas de sesión: `inactividad_segundos` (def. **180**, rango 30–3600), `aviso_segundos` (def. **30**, debe ser < inactividad), `sesion_maxima_minutos` (def. 480).

## Usuarios (admin)
`GET /usuarios`, `POST /usuarios` (201; `{nombre, usuario, password, rol}`), `PUT /usuarios/{id}` (`{nombre?, rol?, activo?, password?}`). Contraseña mínima 8 caracteres, guardada con argon2id; nunca se devuelve el hash. Desactivar a un usuario, o cambiar la contraseña/rol de otro, cierra sus sesiones (evento `sesion_cerrada`). Un admin no puede desactivarse ni cambiar su propio rol.

## Salud
`GET /health` (público) → `{estado:"ok", version, so}` donde `so` es `platform.system()` (útil para mostrar "servidor en línea" y el SO del nodo en la demo).

## WebSocket `/ws?token=<JWT>`
(también disponible como `/api/v1/ws`). Cada mensaje es JSON `{"evento": <nombre>, "payload": {...}}`. Servidor → cliente (no renueva actividad; lo que envíe el cliente se ignora):
| evento | payload | quién lo recibe |
|---|---|---|
| `stock_actualizado` | `{producto_id, stock, activo}` | todos |
| `descuento_cambiado` | `{producto_id, porcentaje, motivo}` | todos |
| `productos_retirados` | `{nombres:[...]}` | admin |
| `config_cambiada` | `{claves:[...]}` | todos |
| `sesion_cerrada` | `{motivo}` | el usuario afectado |

`stock_actualizado` se publica al crear, vender, dar de baja y al editar CUALQUIER campo de un producto (precio_base, stock_maximo, fecha_vencimiento, nombre, categoria, stock, activo), no solo stock/activo: es la señal de "vuelve a pedir este producto" y los clientes refrescan su lista al recibirlo. Al desactivar un producto con descuento vigente se publica además `descuento_cambiado` con `porcentaje: 0`. No se añadió un evento nuevo. `sesion_cerrada.motivo`: `logout`, `inactividad`, `usuario_desactivado`, `password_cambiada`, `rol_cambiado`, `usuario_inactivo`, `revocada` (valor por defecto de `cerrar_sesiones_de`), `token_invalido`. Un `sesion_cerrada` solo cierra el socket si ESA sesión ya no es válida (cerrar otra sesión del mismo usuario no lo afecta).

Cierre con código 4401 (tras aceptar la conexión) si el token es inválido o la sesión caducó. El servidor revalida cada ~5 s los sockets abiertos (sin renovar actividad) y cierra con 4401, tras enviar `sesion_cerrada`, si caducó por inactividad o por `sesion_maxima_minutos`. Si el cliente pierde el socket, reconecta con backoff y mientras tanto usa polling cada 60 s.
