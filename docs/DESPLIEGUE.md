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
inicie sesion en uno como `admin` y en el otro como `comprador`. Un solo cliente: `.\deploy\windows\start_client.ps1 [-Url http://IP:8000]`.
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
