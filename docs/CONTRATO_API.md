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

**Semántica de `fecha_vencimiento`.** Una fecha SIN hora (medianoche exacta, `00:00:00`, p. ej. `"2026-10-24"` o `"2026-10-24T00:00:00"`) significa "válido hasta el final de ese día": el servidor la normaliza y guarda como `23:59:59` del mismo día, en `POST` y `PUT` (fuente única de verdad, válida para cualquier cliente). Un producto que vence hoy sigue en ofertas (nivel crítico, "Vence hoy") y se puede vender hasta las 23:59:59; solo se considera vencido y se retira cuando pasa ese instante. Las fechas con hora explícita distinta de `00:00:00` se respetan tal cual. Al arrancar, el servidor normaliza de forma idempotente los productos activos ya guardados a medianoche con fecha de hoy o futura.

**Reactivar.** `PUT /productos/{id}` con `{"activo": true}` reactiva un producto inactivo. Si su fecha de vencimiento ya pasó se rechaza con 422 (`fecha_vencimiento`): hay que enviar en la misma petición una fecha nueva. Para listar todos hay que pedir `activos=true` y `activos=false`.
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
| GET | `/facturas?desde=&hasta=&q=&metodo_pago=&usuario_id=&limite=&offset=` | Historial, más recientes primero (admin: todas; comprador: solo las suyas). Ver filtros abajo |
| GET | `/facturas/resumen?desde=&hasta=&q=&metodo_pago=&usuario_id=` | **Solo admin** (403 `ROL_NO_PERMITIDO` al comprador). Totales del mismo filtro, calculados con SUM/COUNT en SQL |

**Filtros de `GET /facturas` y `/facturas/resumen`** (todos opcionales y combinables con AND):
- `desde`, `hasta`: fechas ISO 8601, límites inclusivos sobre la fecha de la factura. Una fecha sin hora (`2026-06-30`) equivale a las 00:00:00; para incluir todo un día hasta el final envíe `2026-06-30T23:59:59.999999` (el cliente de escritorio lo hace así).
- `q`: texto (máx. 100) que se busca como subcadena en número (`FAC-000012`), nombre del cliente y documento del cliente, sin distinguir mayúsculas ni tildes (`jose` encuentra «José»); `%` y `_` se toman literalmente. No busca en el nombre de la cuenta.
- `metodo_pago`: `efectivo` o `tarjeta_simulada` (otro valor: 422).
- `usuario_id`: solo para admin; filtra por la cuenta que hizo la compra. Un comprador siempre ve únicamente las suyas y este parámetro se ignora.
- `limite` (def. 200, 1 a 1000) y `offset` (def. 0, >= 0), solo en la lista. Valores fuera de rango: 422 `VALIDACION`.

`GET /facturas/resumen` responde `{cantidad, subtotal, ahorro, iva, total, ticket_promedio, por_metodo:[{metodo, cantidad, total}], top_productos:[{nombre, unidades, total}], desde, hasta}`. Montos enteros (pesos). `subtotal` es sin descuento; `total` es la suma de los totales de factura (con IVA); `por_metodo` va de mayor a menor total; `top_productos` son los 5 más vendidos por unidades (suma de `total` = subtotal de líneas, sin IVA); `desde`/`hasta` son la fecha de la factura más antigua y de la más reciente que cumplen el filtro (`null` si no hay). `ticket_promedio` = `total / cantidad` redondeado (0 si no hay facturas). La ruta se declara antes de `/facturas/{numero}`.

Las facturas son **inmutables**: no existen rutas para anularlas, editarlas ni borrarlas (cualquier `PUT`/`PATCH`/`DELETE` sobre `/facturas...` responde 404/405).

La factura incluye: número consecutivo, fecha/hora, datos del negocio (de configuración), cliente, ítems (precio original, % descuento, precio final, subtotal), subtotal sin descuento, ahorro, total, método de pago, efectivo recibido y cambio. Además `usuario_id` y `usuario_nombre`: la cuenta que realizó la compra (`null` en facturas históricas migradas sin usuario); no confundir con `cliente`, que es lo que digitó el comprador.

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
| `factura_creada` | `{numero, total, metodo_pago}` | admin |
| `sesion_cerrada` | `{motivo}` | el usuario afectado |

`factura_creada` se publica DESPUÉS de confirmar la transacción de `POST /compras` (nunca si la compra falla) y solo al admin (`para="admin"`): es la señal para refrescar la pantalla Facturas en vivo; el comprador no lo recibe. `stock_actualizado` se publica al crear, vender, dar de baja y al editar CUALQUIER campo de un producto (precio_base, stock_maximo, fecha_vencimiento, nombre, categoria, stock, activo), no solo stock/activo: es la señal de "vuelve a pedir este producto" y los clientes refrescan su lista al recibirlo. Al desactivar un producto con descuento vigente se publica además `descuento_cambiado` con `porcentaje: 0`. No se añadió un evento nuevo. `sesion_cerrada.motivo`: `logout`, `inactividad`, `usuario_desactivado`, `password_cambiada`, `rol_cambiado`, `usuario_inactivo`, `revocada` (valor por defecto de `cerrar_sesiones_de`), `token_invalido`. Un `sesion_cerrada` solo cierra el socket si ESA sesión ya no es válida (cerrar otra sesión del mismo usuario no lo afecta).

Cierre con código 4401 (tras aceptar la conexión) si el token es inválido o la sesión caducó. El servidor revalida cada ~5 s los sockets abiertos (sin renovar actividad) y cierra con 4401, tras enviar `sesion_cerrada`, si caducó por inactividad o por `sesion_maxima_minutos`. Si el cliente pierde el socket, reconecta con backoff y mientras tanto usa polling cada 60 s.
