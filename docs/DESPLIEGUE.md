# Despliegue: servidor en WSL2 (Ubuntu) + cliente PyQt6 en Windows

Arquitectura: el servidor FastAPI/uvicorn corre en Ubuntu sobre WSL2 y el cliente PyQt6 en Windows;
hablan por HTTP + WebSocket reales (`http://localhost:8000`).

| Nodo | Dependencias | Archivo |
|---|---|---|
| Servidor (WSL) | FastAPI, uvicorn, SQLAlchemy, argon2, PyJWT... (sin PyQt/pandas/matplotlib) | `requirements-server.txt` |
| Cliente (Windows) | PyQt6, httpx, reportlab, openpyxl, pillow | `requirements-client.txt` |

## 1. Requisitos (los instala usted; los scripts no instalan nada del sistema ni usan sudo)

- Windows 11 con WSL2 y una distro Ubuntu (aqui: `Ubuntu`, usuario `kevin`). Si faltara WSL, en PowerShell de administrador:
  `wsl --install -d Ubuntu` (y reiniciar).
- En Ubuntu: `sudo apt update && sudo apt install -y python3 python3-venv python3-pip rsync`
- Windows: Python 3.13/3.14 y el `.venv` del proyecto:
  `py -m venv .venv ; .\.venv\Scripts\python.exe -m pip install -r requirements-client.txt`

## 2. Setup del servidor (una vez; es idempotente)

Desde PowerShell, en la raiz del repo:

```powershell
wsl -d Ubuntu -- bash -lc "bash /mnt/c/Users/kevin/Documents/App_Inventario/deploy/wsl/setup.sh"
```

Crea todo en el filesystem de Linux, en `~/.inventario/`:

- `venv/` entorno virtual con `requirements-server.txt`.
- `app/` copia del codigo (`server/` y `shared/`), mantenida por `deploy/wsl/sync.sh` (rsync).
  Decision: se ejecuta desde una copia en ext4 y no desde `/mnt/c` porque el acceso a `/mnt/c` es mucho mas lento
  (miles de imports en cada arranque) y asi se demuestra que el servidor corre solo sobre Linux.
  `start_server.sh` vuelve a sincronizar en cada arranque (`SIN_SYNC=1` lo desactiva).
- `data/` base SQLite (`inventario.db`) y secreto JWT.  `logs/` (`servidor.log`, `stdout.log`).  `run/servidor.pid`.
- `credenciales.env` (permisos 600) con contrasenas aleatorias de demo para `admin` y `comprador`. Se generan solo la primera vez
  y se muestran una vez; nunca se guardan en el repo.

## 3. Arranque, estado y parada

Desde Windows:

```powershell
.\deploy\windows\start_server_wsl.ps1     # arranca en WSL y comprueba health desde Windows
.\deploy\windows\stop_server_wsl.ps1      # detiene (SIGTERM solo a su PID)
```

Dentro de WSL (`bash .../deploy/wsl/start_server.sh | status.sh | stop_server.sh`). `status.sh` muestra PID, puerto, health, IP de WSL y log.
El servidor queda en segundo plano (nohup + setsid) y sobrevive al cierre de la terminal. Si WSL se reinicia, el PID file obsoleto se
detecta (se verifica que el PID siga vivo y sea `server.main`) y se limpia solo. Si el puerto esta ocupado por otro proceso, el script lo dice y sale con codigo 2
(use `INVENTARIO_PORT=8001`).

Verificacion de salud: `GET http://localhost:8000/api/v1/health` -> `{"estado":"ok","version":"1.0.0","so":"Linux"}`.

```powershell
Invoke-RestMethod http://localhost:8000/api/v1/health
```

## 4. Demo con dos clientes

```powershell
.\deploy\windows\demo.ps1
```

Arranca el servidor, comprueba health, muestra las credenciales (leidas de WSL) y abre dos clientes con `INVENTARIO_URL=http://localhost:8000`:
inicie sesion en uno como `admin` y en el otro como `comprador`. Con `.\deploy\windows\demo.ps1 -ConDatos` ademas carga ~25 productos de minimercado (ver "Datos de demostracion" y "Guion de demostracion" mas abajo)
despues del health y antes de abrir los clientes; sin `-ConDatos` el comportamiento no cambia.
Un solo cliente: `.\deploy\windows\start_client.ps1 [-Url http://IP:8000]`.
La URL tambien se puede escribir en el campo "Servidor" del login. Prioridad: variable `INVENTARIO_URL` > ajustes guardados > `http://localhost:8000`.

## 5. Red: como llega Windows a WSL

- Mismo equipo: WSL2 reenvia `localhost` de Windows al servidor de Linux (localhost forwarding, activo por defecto). Es lo que usan los scripts.
  Si no funcionara (`localhostForwarding=false` en `%UserProfile%\.wslconfig` o puerto 8000 ocupado en Windows), use la IP de WSL
  (`wsl -d Ubuntu -- hostname -I`; cambia en cada reinicio) como `INVENTARIO_URL=http://172.x.x.x:8000`.
- Otro portatil (defensa): `.\deploy\windows\red_info.ps1` muestra las IP de la PC y los comandos (no ejecuta nada). Resumen, en PowerShell de administrador:
  1. IP de la PC: `Get-NetIPAddress -AddressFamily IPv4` (la de su Wi-Fi/Ethernet, p. ej. 192.168.0.11).
  2. En modo NAT (por defecto) el puerto de la PC no llega a WSL; elija una de:
     - Modo espejo: en `%UserProfile%\.wslconfig` poner `[wsl2]` / `networkingMode=mirrored`, luego `wsl --shutdown` y reiniciar el servidor; o
     - `netsh interface portproxy add v4tov4 listenaddress=0.0.0.0 listenport=8000 connectaddress=<IP-WSL> connectport=8000` (repetir si cambia la IP de WSL).
  3. Firewall: `New-NetFirewallRule -DisplayName 'Inventario API 8000' -Direction Inbound -Protocol TCP -LocalPort 8000 -Action Allow -Profile Private`
     (al terminar: `Remove-NetFirewallRule -DisplayName 'Inventario API 8000'`; y `netsh interface portproxy delete v4tov4 listenaddress=0.0.0.0 listenport=8000`).
  4. En el otro portatil: `Invoke-RestMethod http://<IP-PC>:8000/api/v1/health` y luego el cliente con `$env:INVENTARIO_URL='http://<IP-PC>:8000'`.
  El servidor escucha en `0.0.0.0` (`INVENTARIO_HOST`). Use redes de confianza: el trafico es HTTP sin TLS.

## 6. Si algo falla

| Sintoma | Accion |
|---|---|
| `Faltan paquetes del sistema` | Ejecute el `sudo apt install ...` que indica el script. |
| `El puerto 8000 ya esta ocupado` | `ss -ltnp 'sport = :8000'` en WSL; o `INVENTARIO_PORT=8001` (y `-Url http://localhost:8001`). |
| Health OK en WSL pero no en Windows | Seccion 5 (forwarding / IP de WSL). |
| Timeout al arrancar | `tail -n 50 ~/.inventario/logs/stdout.log` (el script ya imprime las ultimas lineas). |
| Login falla con las credenciales | La BD ya existia antes de generar `credenciales.env`: borre los datos de demo (abajo). |
| Tras `wsl --shutdown`/reinicio | Basta con `start_server_wsl.ps1`; el PID obsoleto se limpia solo. |

Reiniciar: `stop_server_wsl.ps1` y luego `start_server_wsl.ps1`. Actualizar codigo: `bash .../deploy/wsl/sync.sh` y reiniciar (o simplemente reiniciar, ya sincroniza).

## 7. Borrar datos de demo (reinicia BD y usuarios)

```powershell
.\deploy\windows\stop_server_wsl.ps1
wsl -d Ubuntu -- bash -lc "rm -rf ~/.inventario/data"
```
Para generar tambien contrasenas nuevas: borre ademas `~/.inventario/credenciales.env` y vuelva a ejecutar `setup.sh`.
Todo el despliegue se elimina con `rm -rf ~/.inventario`.

## 8. Importar una BD legacy

Si existiera una base antigua (SQLite del sistema previo), con el servidor detenido y las variables del servidor cargadas:

```bash
wsl -d Ubuntu -- bash -lc "set -a; . ~/.inventario/credenciales.env; set +a; export INVENTARIO_DATA_DIR=~/.inventario/data INVENTARIO_DB=~/.inventario/data/inventario.db; cd ~/.inventario/app && ~/.inventario/venv/bin/python -m server.infrastructure.db.migrar_legacy /mnt/c/RUTA/legacy.db"
```

En esta maquina NO hay BD legacy, por lo que este paso no se ha ejecutado ni verificado aqui.

## 9. Datos de demostracion (`deploy/seed_demo.py`)

El servidor arranca con la BD vacia (solo `admin` y `comprador`). El script crea ~25 productos por el API real (httpx, login como admin; solo requiere `httpx`).
Los vencimientos son relativos a HOY y cubren todos los casos: critico (1-3 dias), alto (4-7 dias), sobrestock (stock >= 90 % del maximo), stock bajo (<= 10),
normales (12-200 dias), sin vencimiento, uno que vence hoy a las 23:59 y uno que vence en pocos minutos (retiro en vivo).

```powershell
.\.venv\Scripts\python.exe deploy\seed_demo.py --desde-wsl                 # carga (idempotente: omite los que ya existen por nombre)
.\.venv\Scripts\python.exe deploy\seed_demo.py --desde-wsl --reset-fechas  # re-arma precio, stock y fechas (reactiva los retirados)
.\.venv\Scripts\python.exe deploy\seed_demo.py --desde-wsl --limpiar       # da de baja los productos de la demo
```

- URL: `--url` o `INVENTARIO_URL` (por defecto `http://localhost:8000`). Clave: `--password`, `INVENTARIO_ADMIN_PASSWORD` o `--desde-wsl` (lee
  `~/.inventario/credenciales.env`); nunca se imprime. En Linux: `python3 deploy/seed_demo.py --password ...` (solo `pip install httpx`).
- Las fechas envejecen: **el mismo dia de la defensa ejecute `--reset-fechas`** (o `demo.ps1 -ConDatos`, que ya lo hace).
- `--minutos N` fija en cuanto vence el producto "Sandwich de pollo (retiro en vivo)" (por defecto 4). El escaneo automatico corre cada
  `intervalo_escaneo_segundos` (60 s por defecto), asi que el retiro ocurre hasta ~60 s despues del vencimiento.
- Al final imprime el resumen por nivel consultando `GET /riesgo/resumen`.

## 10. Guion de demostracion

Preparacion (5 min antes): `.\deploy\windows\demo.ps1 -ConDatos` (arranca el servidor en WSL, comprueba health, carga datos con `--reset-fechas`, abre dos clientes).
Para el retiro en vivo, haga la carga con `--minutos` acorde a su turno: el producto debe vencer cuando llegue a ese punto del guion
(p. ej. `seed_demo.py --desde-wsl --reset-fechas --minutos 10` justo antes de empezar). Si ya vencio, repita el comando.

1. **Arranque y salud.** Muestre el servidor corriendo en WSL y `Invoke-RestMethod http://localhost:8000/api/v1/health` -> `"so":"Linux"`. Los clientes son procesos de Windows.
2. **Dos roles a la vez.** Ventana 1: `admin`; ventana 2: `comprador` (las claves las imprime `demo.ps1`).
3. **Alertas y descuentos (admin).** Panel de riesgo: criticos (pan tajado, yogur, jamon, lechuga), altos (croissant, queso, jugo, banano), sobrestock (arroz, tomate, agua) y stock bajo (salchichas, pollo apanado). Explique las reglas: 50 % critico, 30 % alto, 10 % sobrestock (configurables).
4. **Catalogo con descuento (comprador).** Muestre las ofertas con precio original, final y motivo.
5. **Compra y factura.** El comprador agrega al carrito, paga (efectivo o tarjeta simulada) y abre la factura/PDF. En el admin el stock cambia solo (evento `stock_actualizado` por WebSocket).
6. **Cierre por inactividad.** Admin > Configuracion: `inactividad_segundos` = 30 y `aviso_segundos` = 10. Deje la ventana del comprador sin tocar: a los ~10 s del cierre aparece el aviso y a los 30 s la sesion se cierra y vuelve al login. Restaure 180/30 despues.
7. **Servidor en Linux.** Senale la barra de estado del cliente (servidor en linea / SO) y `GET /api/v1/health`. Opcional: `wsl -d Ubuntu -- bash -lc "uname -a; ss -ltnp 'sport = :8000'"`.
8. **Retiro automatico en vivo.** Con el admin en el panel de productos/alertas, espere a que "Sandwich de pollo (retiro en vivo)" venza: en <= ~60 s llega `productos_retirados` por WebSocket y desaparece del catalogo del comprador. Para forzarlo ya: `POST /riesgo/escaneo`.

### Preguntas tipicas del docente (respuestas cortas y honestas)

- **"Es realmente distribuido?"** Son dos nodos en SO distintos (Ubuntu en WSL2 y Windows 11) en una sola maquina fisica, comunicados por red real (TCP/IP). Se puede mostrar en dos portatiles (seccion 5), pero la demo corre en una.
- **"Que protocolo usan?"** HTTP/JSON (REST) para operaciones y WebSocket para eventos del servidor al cliente. Sin TLS (red de confianza); en produccion iria detras de HTTPS.
- **"Que es el token?"** Un JWT firmado que el servidor entrega en el login; el cliente lo envia en `Authorization: Bearer`. Ademas el servidor guarda la sesion (inactividad, revocacion al hacer logout), por eso puede cerrarla aunque el JWT no haya expirado. Las claves se guardan con argon2id.
- **"Por que WebSocket y polling?"** El WebSocket da cambios inmediatos (stock, descuentos, retiros) sin consultar constantemente; si se cae, el cliente reconecta con backoff y mientras tanto consulta cada 60 s, asi que la informacion no se pierde.
- **"Hay balanceo o replicas?"** No. Hay un unico servidor y una unica BD SQLite; no hay balanceador, replicacion ni tolerancia a fallos del servidor. Es una arquitectura cliente-servidor distribuida en dos nodos, no un cluster; escalar implicaria otra BD (p. ej. PostgreSQL) y un bus de eventos compartido.
