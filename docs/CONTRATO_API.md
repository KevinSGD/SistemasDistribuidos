# Contrato API — InventarioApp (borrador para aprobación)

Base: `http://<host>:8000/api/v1`. JSON UTF-8. Auth: `Authorization: Bearer <JWT>` salvo `/auth/login` y `/health`.

## Errores
`{"codigo": "STOCK_INSUFICIENTE", "mensaje": "...", "detalle": {...}}`

| HTTP | codigo | Cuándo |
|---|---|---|
| 401 | `CREDENCIALES_INVALIDAS` / `TOKEN_INVALIDO` / `SESION_INACTIVA` / `SESION_CERRADA` | auth |
| 403 | `ROL_NO_PERMITIDO` | rol insuficiente |
| 404 | `NO_ENCONTRADO` | recurso inexistente |
| 409 | `STOCK_INSUFICIENTE` / `PRODUCTO_VENCIDO` / `PRODUCTO_INACTIVO` | compra inválida |
| 422 | `VALIDACION` | datos mal formados |

## Autenticación y sesión
| Método | Ruta | Rol | Descripción |
|---|---|---|---|
| POST | `/auth/login` | público | `{usuario, password}` → `{token, expira_en, usuario{id,nombre,rol}, sesion{inactividad_segundos, aviso_segundos}}` |
| POST | `/auth/actividad` | autenticado | Renueva `ultima_actividad`. Solo lo llama el cliente ante input real del usuario (throttle ~10 s). Devuelve `{segundos_restantes}` |
| GET | `/auth/sesion` | autenticado | Estado sin renovar: `{segundos_restantes, inactividad_segundos, aviso_segundos}` |
| POST | `/auth/logout` | autenticado | Revoca la sesión |

Regla: ninguna otra ruta ni el WebSocket renuevan `ultima_actividad`. Al validar cada petición se lee `inactividad_segundos` vigente de configuración, por lo que un cambio del admin aplica también a sesiones abiertas.

## Productos (admin; GET también comprador)
| Método | Ruta | Descripción |
|---|---|---|
| GET | `/productos?activos=true` | Lista de inventario (admin) |
| POST | `/productos` | Crear |
| PUT | `/productos/{id}` | Editar |
| DELETE | `/productos/{id}` | Baja lógica |
| GET | `/ofertas` | (comprador/admin) productos con descuento activo, con precio final y motivo |

## Riesgo (admin)
| Método | Ruta | Descripción |
|---|---|---|
| GET | `/riesgo/resumen` | Conteos por nivel + lista de atención (dashboard) |
| GET | `/riesgo/alertas` | Productos agrupados por severidad |
| POST | `/riesgo/escaneo` | Fuerza un escaneo; devuelve retirados y descuentos aplicados |

## Ventas / facturas (comprador)
| Método | Ruta | Descripción |
|---|---|---|
| POST | `/compras` | `{items:[{producto_id,cantidad}], cliente{nombre,documento}, pago{metodo, efectivo_recibido}}` → factura completa. Atómico; falla entero si algún ítem es inválido |
| GET | `/facturas/{numero}` | Datos de factura para vista previa y PDF |
| GET | `/facturas?desde=&hasta=` | Historial (admin: todas; comprador: las suyas) |

La factura incluye: número consecutivo, fecha/hora, datos del negocio (de configuración), cliente, ítems (precio original, % descuento, precio final, subtotal), subtotal sin descuento, ahorro, total, método de pago, efectivo recibido y cambio.

## Configuración (admin escribe; resto lee lo que necesita)
| Método | Ruta | Descripción |
|---|---|---|
| GET | `/config` | Toda la configuración (admin) |
| PUT | `/config` | Actualiza claves (validadas por rango). Emite evento `config_cambiada` |
| GET | `/config/publica` | Moneda, nombre del negocio (todos los roles) |

Claves nuevas de sesión: `inactividad_segundos` (def. **180**, rango 30–3600), `aviso_segundos` (def. **30**, debe ser < inactividad), `sesion_maxima_minutos` (def. 480).

## Usuarios (admin)
`GET/POST /usuarios`, `PUT /usuarios/{id}` (activar/desactivar, cambiar contraseña).

## Salud
`GET /health` → `{estado, version, so}` (útil para mostrar "servidor en línea" y el SO del nodo en la demo).

## WebSocket `/ws?token=<JWT>`
Servidor → cliente (no renueva actividad):
| evento | payload | quién lo recibe |
|---|---|---|
| `stock_actualizado` | `{producto_id, stock}` | todos |
| `descuento_cambiado` | `{producto_id, porcentaje, motivo}` | todos |
| `productos_retirados` | `{nombres:[...]}` | admin |
| `config_cambiada` | `{claves:[...]}` | todos |
| `sesion_cerrada` | `{motivo}` | el usuario afectado |

Cierre con código 4401 si el token es inválido o la sesión caducó. Si el cliente pierde el socket, reconecta con backoff y mientras tanto usa polling cada 60 s.
