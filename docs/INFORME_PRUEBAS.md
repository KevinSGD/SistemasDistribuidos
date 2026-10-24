# Informe de pruebas end-to-end: cliente PyQt6 en Windows contra servidor FastAPI en Ubuntu/WSL2

Fecha de ejecución: 2026-10-24. Todo lo que aparece abajo salió de ejecuciones reales (comandos y cifras de la salida de pytest y de los `print` de cada test).

## 1. Entorno

| Componente | Versión |
|---|---|
| Cliente: SO | Windows 11 Home Single Language 10.0.26300 |
| Cliente: Python / Qt | Python 3.13.15; PyQt6 6.7.0, Qt 6.7.3 (plataforma `offscreen` en los tests, `windows` en las capturas) |
| Cliente: otras | httpx 0.28.1, pydantic 2.14.1, reportlab 4.2.0, websockets 17.3, pytest 9.1.1 |
| WSL | WSL 2.6.3.0, kernel 6.6.87.2-1 (`uname`: `Linux KevinG 6.6.87.2-microsoft-standard-WSL2`) |
| Servidor: SO | Ubuntu 26.04.1 LTS (WSL2) |
| Servidor: Python / libs | Python 3.14.4 (`~/.inventario/venv`); FastAPI 0.162.0, uvicorn 0.54.0, starlette 1.10.0, SQLAlchemy 2.0.48, PyJWT 2.15.1, argon2-cffi 25.1.0 |
| Red | HTTP + WebSocket por el reenvío de `localhost` de WSL2 (el cliente usa `http://127.0.0.1:<puerto>`, ver hallazgo H-3) |

La prueba de que son dos sistemas operativos distintos está en `test_01_entorno.py`: el proceso de pruebas dice `platform.system() == "Windows"` y `GET /api/v1/health` devuelve `{"estado":"ok","version":"1.0.0","so":"Linux"}`; además `/proc/<pid>/cmdline` del servidor muestra `~/.inventario/venv/bin/python -m server.main` con `cwd=/tmp/inv_e2e_*/app`.

## 2. Cómo está montada la prueba (aislamiento)

- **No se usa el servidor de demo** (puerto 8000, `~/.inventario/data`). Cada escenario levanta su propia instancia con `tests/e2e/wsl_server.sh`: copia de `server/` y `shared/` por rsync a `/tmp/inv_e2e_<id>/app`, BD/datos/logs/PID en `/tmp/inv_e2e_<id>`, puerto desde 8010 (si está ocupado prueba el siguiente), contraseñas aleatorias generadas por el test (`INVENTARIO_ADMIN_PASSWORD`, `INVENTARIO_COMPRADOR_PASSWORD`) y el venv de `~/.inventario/venv` en solo lectura.
- Se detiene **solo el PID registrado** (el script comprueba que el proceso sea `server.main` con `cwd` = la copia propia) y se borra `/tmp/inv_e2e_<id>` al terminar. Un `atexit` lo repite como red de seguridad. Tras la suite completa: `/tmp` sin `inv_e2e_*`, sin procesos `server.main` propios, sin puertos 80xx abiertos.
- Una fixture de sesión (`demo_intacta`) compara tamaño y fecha de modificación de la BD de demo antes y después de la suite; la suite pasa, o sea que no la tocó. (Nota: durante el trabajo vi un listener en `:8000` que no es mío; al final ya no estaba. No lo toqué.)
- Los ajustes del cliente (URL guardada, PDFs) van a un directorio temporal (`INVENTARIO_CLIENT_DIR`), no al perfil real.
- `pytest.ini`: `addopts = -m "not e2e"`. La suite normal los deselecciona; se ejecutan con `-m e2e`.
- Los clientes son la raíz real del cliente (`Aplicacion` + `LoginView` + `MainWindow`/`BuyerWindow`, `ApiClient`, `IdleMonitor`, `EventClient`) con las **opciones de producción sin tocar** (throttle de actividad 10 s, tick 1 s, health 10 s, `solo_espontaneos=True`). Los eventos de `QTest` llegan como espontáneos de Qt (verificado), así que el `IdleMonitor` real los cuenta; un `sendEvent` sintético no (test 9c).

## 3. Comandos para reproducir

```powershell
# E2E (instancia WSL aislada; ~3 min, de los cuales ~1 min es la línea de tiempo de inactividad)
.venv\Scripts\python.exe -m pytest tests/e2e -m e2e -p no:cacheprovider -v -s -rx --durations=0
# un escenario
.venv\Scripts\python.exe -m pytest tests/e2e/test_02_inactividad.py -m e2e -p no:cacheprovider -s
# suite normal (los e2e quedan deseleccionados)
$env:QT_QPA_PLATFORM='offscreen'; .venv\Scripts\python.exe -m pytest tests -q -p no:cacheprovider
# capturas reales (plataforma windows, abre ventanas ~45 s; se ejecuta APARTE de pytest)
.venv\Scripts\python.exe -m tests.e2e.capturas
```
Variables opcionales: `INVENTARIO_E2E_PUERTO` (puerto base, 8010), `INVENTARIO_WSL_DISTRO` (Ubuntu).

## 4. Resultados

### 4.1 Corridas completas

| Comando | Resultado real |
|---|---|
| `QT_QPA_PLATFORM=offscreen .venv\Scripts\python.exe -m pytest tests -q -p no:cacheprovider` | **398 passed, 32 deselected, 6 warnings in 145.22s** (los 398 de antes; los 32 son los e2e) |
| `.venv\Scripts\python.exe -m pytest tests/e2e -m e2e -p no:cacheprovider -v -rx --durations=0` | **32 passed, 0 xfailed in 191.44s (0:03:11)** (tras corregir H-1, H-2 y H-3; antes: 29 passed, 3 xfailed) |

### 4.2 Tabla de escenarios

Duración = la de pytest en la corrida completa (`call`, y `setup` donde ahí está el trabajo). Los tests de inactividad comparten una línea de tiempo que se ejecuta una vez (fixture de módulo): 56,46 s de `setup` en el primer test; cada aserción individual dura < 10 ms.

| # | Qué se probó | Test | Resultado | Duración |
|---|---|---|---|---|
| 1 | Dos SO distintos: health desde Windows dice `Linux`; proceso `server.main` en Linux aislado; credenciales propias | `test_01_entorno.py` (3) | PASSED | 2,0 s setup + 0,5/0,7/0,4 s |
| 2a | Comprador inicia con inactividad 180 / aviso 30 (defecto), también en la sesión local y en la barra (Sesión: 03:00) | `test_02::test_a` | PASSED | ver fixture |
| 2b | Admin cambia a 30/10 **por la UI** (Configuración > Seguridad de sesión): "✓ Aplicado a tu sesión actual…" a 0,32 s; el servidor devuelve 30/10 | `test_b` | PASSED | ver fixture |
| 2c | El IdleMonitor de las sesiones **ya abiertas** recibe el cambio por WS en 0,34–0,37 s, **sin reconectar**: mismo `EventClient`, mismo `ApiClient`/token, 0 eventos de conexión, el servidor vio 5 sockets antes y 5 después | `test_c` | PASSED | ver fixture |
| 2d | Sin actividad: aviso (DialogoInactividad) a 20,18 s con cuenta 10,9,…,1; cierre a 30,29 s; login muestra "Sesión cerrada por inactividad"; servidor rechaza el token con 401 (ver nota 1) | `test_d` | PASSED | ver fixture |
| 2e | Actividad **real** (tecla + clic de Qt sobre el aviso, en un proceso cliente aparte) a 21,1 s: aviso se cierra, reloj vuelve a 30, el servidor reporta 29/28/26 s a +0,5/+1,5/+3 s, la sesión sigue viva pasados los 30 s originales y cierra 30,3 s después de la actividad (51,5 s tras el login) | `test_e` | PASSED | ver fixture |
| 2f | Refresco automático NO renueva: 11 eventos WS, 5 sondeos, 19 recargas de catálogo, 3 health; 0 llamadas a `/auth/actividad`; el servidor solo descuenta (25,21,17,13,9,5,1 s) y la sesión cierra a 30,20 s | `test_f` | PASSED | ver fixture |
| 2g | "Seguir conectado" renueva: servidor 29/28/26 s tras el clic; cierre natural 30,1 s después | `test_g` | PASSED | ver fixture |
| 2h | La sesión del admin (UI) también cierra con la nueva política (31,3 s tras su login) | `test_h` | PASSED | ver fixture |
| 2i | Filtro de actividad del IdleMonitor de producción: `sendEvent` sintético y movimiento < 8 px no renuevan; tecla, clic y movimiento amplio sí; sondeo/evento WS no | `test_09::test_filtro…` | PASSED | 2,4 s |
| 3 | Servidor caído con comprador conectado: WS cae a +0,15 s y el indicador pasa a rojo; el texto "Servidor desconectado" lo confirma el health a +12,0 s; aviso a 20,02 s y cierre LOCAL a 30,02 s con el mensaje de inactividad; QTimer de 50 ms en el hilo GUI: 477 muestras, hueco máximo **83 ms**; login con servidor caído muestra "No se pudo conectar…" con hueco máximo 190 ms; al volver el servidor el login funciona | `test_03` | PASSED | 38,9 s |
| 4 | Dos clientes pagan el último ítem (stock 1) a la vez: gana uno (FAC-000001), el otro ve el toast "Stock insuficiente para '…'. Disponible: 0, pedido: 1" sin cerrar la app y recibe por WS `stock_actualizado` stock 0; las dos peticiones HTTP se solaparon 58 ms; stock final 0 y una sola factura | `test_04::test_dos_clientes…` | PASSED | 1,4 s |
| 4b | 8 rondas de 2 compradores (hilos + barrera): siempre 1 éxito + 1 `STOCK_INSUFICIENTE`/409 | `test_04::test_carreras_api…` | PASSED | 7,3 s |
| 4c | 6 compradores simultáneos sobre stock 3: 3 éxitos, 3 rechazos, stock 0, 3 facturas distintas | `test_04::test_carrera_seis…` | PASSED | 2,5 s |
| 5 | Admin crea/edita (stock, regla de descuento, desactiva) y el comprador ve el cambio por WS sin refrescar: crear 0,34 s, stock 0,00 s, descuento 0,34 s, desactivar 0,34 s | `test_05::test_admin_crea…` | PASSED | 3,6 s |
| 5b | Admin desactiva al comprador: su sesión cae a los 0,02 s con "Tu usuario fue desactivado por un administrador"; token viejo → 401 `SESION_CERRADA` motivo `usuario_desactivado`; relogin → 401 | `test_05::test_admin_desactiva…` | PASSED | 1,2 s |
| 6 | Factura IVA 19 %: 14.970 − 2.244 + 2.418 = **15.144** (cambio 4.856), todos los montos enteros, vista previa = servidor = widget; PDF `FAC-000001.pdf` válido (cabecera, `%%EOF`, tabla xref con 15 objetos bien ubicados, 1 página, 5 streams decodificados, y el texto del PDF contiene número, 15.144, 2.418, "IVA 19%" y 4.856); 2ª compra = FAC-000002 (consecutiva); numeración sin huecos | `test_06` | PASSED | 1,2 s |
| 7 | Reinicio con la misma BD: PID cambia; WS cae +0,11 s, servidor arriba +1,47 s, WS reconectado +1,52 s (mismo `EventClient`, sesión intacta, 1 sondeo de resincronización); productos, usuarios, factura y consecutivo persisten; **el token emitido antes del reinicio sigue válido** (168 s restantes, y permite operar); el WS reconectado entrega eventos; el bloqueo de login (en memoria) se reinició | `test_07` | PASSED | 15,6 s |
| 8a | Comprar más que el stock → 409 `STOCK_INSUFICIENTE` (`disponible 2, solicitado 3`), stock y facturas intactos | `test_08` | PASSED | 0,07 s |
| 8b | Comprar vencido → 409 `PRODUCTO_VENCIDO` | `test_08` | PASSED | 0,03 s |
| 8c | Rollback total: ítem B falla → A conserva stock 5, sin factura y sin consumir el consecutivo | `test_08` | PASSED | 0,20 s |
| 8d | Login correcto; incorrecto / usuario inexistente / inactivo → 401 `CREDENCIALES_INVALIDAS` con el mismo mensaje (sin enumeración); 6 fallos → 429 `TOO_MANY_ATTEMPTS` (reintentar en 60 s) | `test_08` | PASSED | 4,7 s |
| 8e | Migración SHA-256 → argon2id en la BD de Linux: `sha256$0833…` → `$argon2id$v=19$m=65536,t=3,p=4…` solo tras login correcto; un fallo no migra; no se re-hashea dos veces | `test_08` | PASSED | 2,5 s |
| 8f | Token con firma alterada, payload alterado (rol=admin), `alg=none`, basura, expirado (forjado con el secreto del servidor) y sin cabecera → 401 `TOKEN_INVALIDO` (el expirado con `motivo: expirado`); el WS cierra con 4401 | `test_08` | PASSED | 2,8 s |
| 8g | FK y CHECK activos en la BD de Linux (`PRAGMA foreign_keys=1`, WAL): 2 FK (`FOREIGN KEY constraint failed`) y 4 CHECK (`ck_producto_stock`, `ck_producto_precio_base`, `ck_descuento_porcentaje`, `ck_detalle_cantidad`) rechazan; y por API un stock negativo da 422 | `test_08` | PASSED | 0,75 s |
| 8h | El WebSocket entrega el evento al otro cliente: `{"evento":"stock_actualizado","payload":{"producto_id":6,"stock":3,"activo":true}}` en 49 ms | `test_08` | PASSED | 0,09 s |
| 8i | Flujo del administrador por la UI: login, las 5 vistas cargan, barra "Servidor en línea · Linux" | `test_08` | PASSED | 1,1 s |
| H-1 | Editar precio/vencimiento no notifica por WS | `test_05::test_editar_precio_notifica_por_ws` | **CORREGIDO** (pasa) | 8,4 s |
| H-2 | El JWT aparece en los logs del servidor | `test_09::test_el_jwt_no_debe…` | **CORREGIDO** (pasa) | 1,0 s |
| H-3 | Conexión nueva a `localhost` tarda ~2,2 s | `test_09::test_conexion_nueva…` | **CORREGIDO** (pasa) | 13,1 s |

Nota 1 (2d): al expirar, el cliente hace `logout` y ese primer contacto ya cierra la sesión en el servidor por inactividad; por eso el token de ese cliente responde después `401 SESION_CERRADA` con `detalle.motivo = "inactividad"`. La respuesta literal `401 SESION_INACTIVA` ("Sesión cerrada por inactividad") la da el servidor a una sesión sin cliente (la sonda HTTP): a los 25 s seguía viva con 4 s restantes y a los 31,5 s devolvió exactamente `401 SESION_INACTIVA`. Ambos casos están asertados.

### 4.3 Salida real de los escenarios clave (extractos de `-s`)

```
[a] sesiones abiertas con 180/30 (inact, aviso, sesion.inact, sesion.aviso, reloj): {'B1 inactivo': (180, 30, 180, 30, 180), 'B3 …': (180, 30, 180, 30, 180), 'B4 …': (180, 30, 180, 30, 180), 'B2 actividad real': (180, 30, 180, 30, 180)}
[b] UI admin: '✓ Aplicado a tu sesión actual. Se cerrará la sesión tras 30 s sin actividad; aviso 10 s antes' en 0.32 s; servidor: 30/10
[c] latencia de aplicacion tras pulsar Guardar: B1=0.34s, B3=0.34s, B4=0.34s, B2=0.37s; sockets WS aceptados por el servidor antes/despues: 5/5
[d] B1: aviso a 20.18 s, cuenta regresiva [10, 9, 8, 7, 6, 5, 4, 3, 2, 1], cierre a 30.29 s, login muestra 'Sesión cerrada por inactividad'; token de B1 -> (401, 'SESION_CERRADA', 'La sesion fue cerrada', 'inactividad'); sonda a los 25 s: 4 s restantes; a los 31,5 s: (401, 'SESION_INACTIVA', 'Sesion cerrada por inactividad')
[e] B2 (proceso aparte): actividad real a 21.1 s del login (aviso visible, 9 s restantes) -> reloj 30 s; servidor a +0,5/+1,5/+3 s: [29, 28, 26]; cierre natural 30.3 s despues de la actividad (51.5 s tras el login)
[f] B3: 11 eventos WS, 5 sondeos, 19 recargas de catalogo, 3 health; renovaciones enviadas: 0; segundos restantes en el servidor: [25, 21, 17, 13, 9, 5, 1]; cierre a 30.20 s
[g] B4: 'Seguir conectado' a 21.1 s del login -> servidor [29, 28, 26] s, cierre natural a 30.1 s del clic
[3] WS cae +0.15 s; indicador rojo +0.15 s; texto 'Servidor desconectado' +12.00 s; aviso a 20.02 s; cierre local a 30.02 s con mensaje 'Sesión cerrada por inactividad'; latido GUI: 477 muestras, hueco maximo 83 ms (intervalo 50 ms)
[4] ganador A factura FAC-000001; perdedor B: toast 'Stock insuficiente para 'Ultima unidad E2E'. Disponible: 0, pedido: 1. Revisa tu carrito.'; solape 58 ms; stock final 0
[7] reinicio PID 32598 -> 33177; WS cae +0.11 s, servidor arriba +1.47 s, WS reconectado +1.52 s; token previo al reinicio: ('valido', 168); bloqueo de login tras reinicio: reiniciado: login permitido
```
(Las cifras son de la última corrida individual de cada módulo con `-s`; la corrida completa con `-v` pasó con las mismas tolerancias: aviso 19,5–22,5 s, cierre 29,5–33,0 s.)

### 4.4 Cómo se paralelizó la inactividad

Todos los clientes de §2 viven a la vez en una sola línea de tiempo (~50 s tras el cambio de configuración, 56 s con el arranque). Dos detalles de diseño del propio harness, aprendidos con fallos reales durante el desarrollo:

1. **El filtro de actividad es del `QApplication` (uno por proceso).** Con varios usuarios simulados en el mismo proceso, el teclado/ratón de uno renovaba la sesión de todos (primer intento: 5 fallos). El cliente que recibe teclado/ratón (B2) corre ahora en un proceso aparte (`tests/e2e/cliente_worker.py`), como en producción. No es un bug del producto.
2. **Las llamadas HTTP de la propia prueba corren en hilos.** Una conexión nueva a WSL cuesta 0,2 s (2,2 s con `localhost`); hechas en el hilo GUI retrasaban los ticks de los clientes y falseaban los 30 s (cierre a 36 s en el segundo intento). Con hilos y `127.0.0.1` los tiempos medidos son los del producto.

## 5. Bugs y hallazgos (con evidencia y test que los reproduce)

No se modificó `client/` ni `server/`.

**H-1 (CORREGIDO; bug de servidor, media): editar precio, vencimiento, nombre, categoría o stock máximo de un producto no emite ningún evento WS.**
`server/application/inventario_service.py`, `InventarioService.editar`: solo llama a `_publicar_stock` si cambia `stock` o `activo`. Reproducción: con el comprador conectado, `PUT /productos/{id}` con `fecha_vencimiento` a 1,5 días (el producto pasa a oferta crítica; `GET /ofertas` ya lo incluye) → el cliente recibe 0 eventos y la tarjeta no aparece tras 6–8 s. Idem con `precio_base`. El sondeo de respaldo del cliente solo corre con el socket caído, así que el comprador ve datos obsoletos hasta el siguiente evento no relacionado (en un primer intento un cambio de precio "pasó" solo porque coincidió con la recarga diferida de un evento de stock anterior). Test: `test_05_tiempo_real.py::test_bug_editar_precio_o_vencimiento_no_notifica_por_ws` (xfail, `strict=False`).

**H-2 (CORREGIDO; bug de seguridad, media): el JWT queda en los logs del servidor.**
El WS se autentica con `/ws?token=<JWT>` y uvicorn registra la URL completa: `INFO uvicorn.error: … "WebSocket /ws?token=eyJhbGciOi…" [accepted]`. Verificado en `stdout.log` y en `servidor.log` de la instancia. Quien lea los logs puede reutilizar el token mientras la sesión viva. Test: `test_09_hallazgos.py::test_el_jwt_no_debe_aparecer_en_los_logs_del_servidor` (xfail). Mitigación: filtrar la query string en el log, o autenticar con un primer mensaje/subprotocolo.

**H-3 (CORREGIDO; rendimiento de despliegue, media): `localhost` cuesta ~2,2 s por conexión nueva en Windows 11 + WSL2.**
Medido: conexión nueva a `http://localhost:<p>`: mediana 2.240 ms (máx 2.259); a `http://127.0.0.1:<p>`: mediana 206 ms; conexión a `::1`: `ConnectionRefusedError` tras 2,02 s (Windows intenta IPv6 primero). Con conexión reutilizada ambos dan ~1 ms. Afecta a `URL_POR_DEFECTO = "http://localhost:8000"` (client/infrastructure/config.py) y a `deploy/windows/*.ps1`: cada login (conexión nueva) y cada reconexión del WS pagan ~2 s. Mitigación: `127.0.0.1` por defecto. Test: `test_09_hallazgos.py::test_conexion_nueva_a_localhost_deberia_tardar_menos_de_1s` (xfail). Las fixtures E2E usan `127.0.0.1` por esta razón.

Observaciones menores (sin test):
- **Foco inicial en "Cerrar sesión" en `BuyerWindow`.** En las capturas reales (`06_catalogo_comprador.png`) el botón aparece con el anillo de foco; `MainWindow` ya evita esto a propósito (`central.setFocus()`), `BuyerWindow` no. Riesgo: un Enter accidental abre el diálogo de cerrar sesión.
- **Ruido en el log del cliente:** `WARNING client.infrastructure.workers: Error en tarea sin manejador: ApiError('SESION_CERRADA'…)` aparece tras cada cierre por inactividad con más de un socket del mismo usuario: `_verificar_sesion` lanza `estado_sesion` sin manejadores al recibir `sesion_cerrada`. Inofensivo.
- **El bloqueo de intentos de login es en memoria** (diseño documentado): un reinicio del servidor lo borra (verificado en el escenario 7). Es una limitación aceptable, no un defecto.
- Con `OpcionesCliente` por defecto el texto de la barra pasa a "Servidor desconectado" hasta 12 s después de caerse el servidor (health cada 10 s); el punto rojo y "Sin eventos en vivo (reconectando)" aparecen a los 0,15 s por el cierre del WS.

## 6. Limitaciones

- Los tiempos de inactividad son reales pero con el mínimo del servidor (30 s / aviso ≥ 5 s); no se probó la ventana por defecto de 180 s completa (sí que arrancan con 180/30 y que el cambio se aplica en caliente).
- Los tests corren con Qt `offscreen` (sin fuentes reales ni ventanas visibles); el teclado/ratón se inyecta con `QTest` (eventos espontáneos de Qt), no con entrada del sistema operativo (SendInput). Las capturas sí usan la plataforma `windows` y fuentes reales, pero tampoco con entrada física.
- Un solo equipo: Windows y WSL2 en la misma máquina vía el reenvío de `localhost`. No se probó otra PC en red, firewall ni `networkingMode=mirrored`.
- No se probó `wsl --shutdown` ni la caída de WSL completo (prohibido por las reglas de la tarea); el "servidor caído" es SIGTERM al proceso propio.
- Un solo worker de uvicorn (diseño); las carreras de compra se probaron con hasta 6 clientes concurrentes sobre SQLite/WAL, no con carga masiva.
- El visor de PDF se sustituyó por un doble (`sin_visor`); el PDF se valida estructuralmente y por texto, no visualmente.
- Correcciones: H-1 (`editar` publica `stock_actualizado` ante cualquier cambio visible), H-2 (`server/logfilter.py` redacta `token=` en los handlers y loggers uvicorn), H-3 (URL por defecto `http://127.0.0.1:8000`). Ya no quedan xfail.
- Las cifras de latencia dependen de la máquina (12 núcleos, 15,5 GB de RAM).

## 7. Capturas reales (`docs/capturas/`)

Generadas con `python -m tests.e2e.capturas`: cliente Windows (plataforma `windows`, fuentes del sistema, escala 125 %) conectado al servidor Linux, sembrado con una tienda de ejemplo ("Supermercado La Esperanza", 13 productos, 5 usuarios, IVA 19 %). Revisadas una a una; se corrigieron: panel "Servidor" desplegado en el login con "Servidor en línea (Linux)", usuarios de ejemplo (incl. uno inactivo) y la composición del aviso de inactividad (el rectángulo del diálogo no coincidía por el escalado de DPI).

| Archivo | Contenido |
|---|---|
| `01_login.png` | Login con el servidor probado: "Servidor en línea (Linux)" |
| `02_dashboard_admin.png` | Dashboard admin; barra: "Servidor en línea · Linux", "Sesión: 03:00" |
| `03_inventario_admin.png` | Inventario (13 productos, niveles de riesgo y precio con descuento) |
| `04_configuracion_seguridad_de_sesion.png` | Configuración con "Seguridad de sesión" (180 s / 30 s y vista previa) |
| `05_usuarios_admin.png` | Usuarios (activos e inactivo) |
| `06_catalogo_comprador.png` | Catálogo del comprador con ofertas |
| `07_catalogo_con_carrito.png` | Carrito con 3 líneas, ahorro y total |
| `08_pago.png` | Resumen y pago (IVA 19 %, total 24.788, cambio 25.212) |
| `09_factura.png` | Factura FAC-000004 (base 20.830 + IVA 3.958 = 24.788) |
| `10_aviso_inactividad.png` | Aviso con cuenta regresiva (7 s) y "Seguir conectado" |
| `11_login_sesion_cerrada_por_inactividad.png` | Login con "Sesión cerrada por inactividad" |

## 8. Archivos entregados

`pytest.ini` (marcador `e2e`, `-m "not e2e"` por defecto) y `tests/e2e/`: `wsl_server.sh`, `wsl.py` (instancia aislada), `conftest.py`, `helpers.py`, `cliente_worker.py`, `pdfcheck.py`, `test_01_entorno.py` … `test_09_hallazgos.py`, `capturas.py`.
