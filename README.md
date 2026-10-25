# InventarioApp

Sistema para gestionar inventario de productos perecederos con descuentos dinámicos según la cercanía al vencimiento. Proyecto de la Universidad Manuela Beltrán (Ingeniería de Software - Sistemas Distribuidos). El documento académico es `contexto.md`.

Es una aplicación distribuida de dos nodos: un servidor FastAPI en Ubuntu (WSL2) y un cliente de escritorio PyQt6 en Windows. El administrador gestiona productos, usuarios y configuración y ve alertas de riesgo; el comprador ve las ofertas, arma un carrito, paga y recibe una factura.

## Arquitectura en 10 líneas

1. Nodo servidor (Ubuntu/WSL2): FastAPI + uvicorn, un solo proceso, SQLite en modo WAL.
2. Nodo cliente (Windows 11): PyQt6, `httpx` para HTTP y `QtWebSockets` para eventos.
3. Comunicación: HTTP/JSON (`/api/v1`) y un WebSocket (`/ws`) por el puerto 8000. Contrato en [docs/CONTRATO_API.md](docs/CONTRATO_API.md).
4. El servidor es el único dueño de la base de datos, de las reglas de negocio y de la autorización por rol; el cliente no abre la base de datos.
5. Autenticación con token JWT; contraseñas con argon2id.
6. La sesión se cierra por inactividad (180 s por defecto, aviso a 30 s; el administrador lo configura y aplica a sesiones abiertas).
7. Un escaneo en el servidor (cada 60 s) retira los vencidos y aplica los descuentos: crítico 50 %, alto 30 %, sobrestock 10 %; el stock bajo solo alerta.
8. Las compras son atómicas (sin sobreventa), generan factura con detalle en la base de datos y el IVA se calcula sobre el precio con descuento.
9. Los cambios se avisan en tiempo real por WebSocket; si el socket cae, el cliente reconecta y consulta cada 60 s.
10. Limitaciones asumidas: una sola máquina física, HTTP sin TLS, sin réplicas ni balanceo y un solo worker. Detalle y diagramas en [docs/ARQUITECTURA.md](docs/ARQUITECTURA.md).

## Requisitos

- Windows 11 con Python 3.13 o 3.14 (el cliente se probó con 3.13.15).
- WSL2 con Ubuntu y Python 3 con `venv` (el servidor se probó con Ubuntu 26.04 y Python 3.14.4); `rsync`.
- Dependencias por nodo: [requirements-server.txt](requirements-server.txt) y [requirements-client.txt](requirements-client.txt).

El archivo `requirements.txt` de la raíz ya no corresponde al sistema anterior (pandas, matplotlib, schedule): ahora solo contiene `-r requirements-server.txt` y `-r requirements-client.txt`. Sirve para crear un único entorno de desarrollo en Windows donde se pueda ejecutar toda la suite de pruebas (que necesita las dependencias de ambos nodos). Para ejecutar un nodo se instala únicamente su archivo.

## Instalación y ejecución

La guía completa, con red, solución de problemas y la demo con dos clientes, está en [docs/DESPLIEGUE.md](docs/DESPLIEGUE.md). Resumen:

### Servidor en Ubuntu (WSL2)

```powershell
# Una vez, en Ubuntu: paquetes del sistema
wsl -d Ubuntu -- bash -lc "sudo apt update && sudo apt install -y python3 python3-venv python3-pip rsync"

# Desde la raíz del repo en PowerShell: prepara ~/.inventario (venv, código, credenciales de demo)
wsl -d Ubuntu -- bash -lc "bash /mnt/c/RUTA/AL/REPO/deploy/wsl/setup.sh"

# Arrancar / detener
.\deploy\windows\start_server_wsl.ps1
.\deploy\windows\stop_server_wsl.ps1

# Comprobar
Invoke-RestMethod http://127.0.0.1:8000/api/v1/health   # {"estado":"ok","version":"1.0.0","so":"Linux"}
```

Cambie `/mnt/c/RUTA/AL/REPO` por la ruta del repositorio vista desde WSL (en este equipo, `/mnt/c/Users/kevin/Documents/App_Inventario`). El servidor se ejecuta con `python -m server.main` desde una copia del código en el sistema de archivos de Linux. Variables: `INVENTARIO_HOST` (0.0.0.0), `INVENTARIO_PORT` (8000), `INVENTARIO_DB`, `INVENTARIO_DATA_DIR`, `INVENTARIO_LOG_DIR`, `INVENTARIO_JWT_SECRET`.

Para un Ubuntu nativo (sin WSL) los pasos equivalentes son crear un `venv`, instalar `requirements-server.txt` y ejecutar `python -m server.main` desde la raíz del repo; esa variante no se probó (solo WSL2).

### Cliente en Windows

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-client.txt
.\deploy\windows\start_client.ps1                 # usa http://127.0.0.1:8000
.\deploy\windows\start_client.ps1 -Url http://IP:8000   # otro servidor
```

La URL también se puede escribir en el campo "Servidor" del login o fijarse con `INVENTARIO_URL`. Se usa `127.0.0.1` y no `localhost` porque en Windows 11 con WSL2 `localhost` añade ~2 s por conexión nueva.

Aviso: el cliente importa `platformdirs`, que `requirements-client.txt` no lista. Si en un entorno limpio falta, instálelo con `pip install platformdirs==4.13.5` (el entorno completo de la raíz ya lo incluye por `requirements-server.txt`).

### Demo con dos clientes

```powershell
.\deploy\windows\demo.ps1 -ConDatos
```

Arranca el servidor, carga unos 25 productos de ejemplo que cubren todos los niveles de riesgo, muestra las credenciales y abre dos clientes (uno como `admin`, otro como `comprador`). Guion de la demostración: [docs/DESPLIEGUE.md](docs/DESPLIEGUE.md), secciones 9 y 10.

## Credenciales de demo

No están en el repositorio ni en el código. Hay dos usuarios iniciales, `admin` (rol administrador) y `comprador` (rol comprador):

- `deploy/wsl/setup.sh` genera una contraseña aleatoria para cada uno la primera vez, las muestra una vez y las guarda en `~/.inventario/credenciales.env` (permisos 600) dentro de WSL. `demo.ps1` las vuelve a mostrar leyendo ese archivo.
- Solo se aplican al crear la base de datos. Si la base ya existía, borre los datos de demo (DESPLIEGUE.md, sección 7).
- Si el servidor arranca sin variables `INVENTARIO_ADMIN_PASSWORD` / `INVENTARIO_COMPRADOR_PASSWORD`, genera contraseñas y las escribe en `credenciales_iniciales.txt` en su directorio de datos.
- Cámbielas desde la vista Usuarios (el administrador) y no las publique.

## Pruebas

```powershell
# Suite normal (dominio, aplicación, infraestructura, seguridad, API y cliente; los e2e quedan deseleccionados)
$env:QT_QPA_PLATFORM='offscreen'; .\.venv\Scripts\python.exe -m pytest tests -q -p no:cacheprovider

# End-to-end: cliente Windows contra un servidor aislado en WSL2 (unos 3 minutos)
.\.venv\Scripts\python.exe -m pytest tests/e2e -m e2e -p no:cacheprovider -v -s
```

La suite normal necesita las dependencias de ambos nodos (por eso existe el `requirements.txt` de la raíz). Los e2e levantan su propia instancia del servidor en WSL2 (puerto desde 8010) y no tocan el servidor de demo. Resultados medidos el 2026-10-24: 419 pruebas normales aprobadas en 3 ejecuciones consecutivas y 32 e2e aprobadas (32 de 32 en la última ejecución completa), ver [docs/INFORME_PRUEBAS.md](docs/INFORME_PRUEBAS.md). Las capturas se regeneran con `python -m tests.e2e.capturas`.

## Estructura del repositorio

```
server/      servidor FastAPI: api, application, domain, infrastructure/db, security
client/      cliente PyQt6: presentation, application, infrastructure
shared/      modelos Pydantic del contrato y redondeo monetario (usados por ambos nodos)
deploy/      scripts de WSL (wsl/), de Windows (windows/) y datos de demo (seed_demo.py)
tests/       domain, application, infra, security, api, client, e2e
docs/        arquitectura, contrato de la API, despliegue, informe de pruebas, auditoría, capturas
contexto.md  documento del proyecto (requerimientos, alcance, diseño)
```

## Documentación

| Documento | Contenido |
|---|---|
| [docs/ARQUITECTURA.md](docs/ARQUITECTURA.md) | Nodos, diagramas de componentes y de secuencia (login, compra, inactividad), modelo de datos, decisiones y limitaciones |
| [docs/CONTRATO_API.md](docs/CONTRATO_API.md) | Rutas REST, errores y eventos WebSocket |
| [docs/DESPLIEGUE.md](docs/DESPLIEGUE.md) | Instalación, red, demo, guion y solución de problemas |
| [docs/INFORME_PRUEBAS.md](docs/INFORME_PRUEBAS.md) | Resultados de las pruebas, incluidas las E2E entre Windows y Ubuntu |
| [docs/AUDITORIA_F01_F10.md](docs/AUDITORIA_F01_F10.md) | Estado de las 10 falencias de la auditoría, con evidencia |
| [docs/TEXTO_PARA_DOCX.md](docs/TEXTO_PARA_DOCX.md) | Texto actualizado para copiar en `Documentacion SD.docx` |

## Capturas

Capturas reales del cliente Windows conectado al servidor Linux, en [docs/capturas](docs/capturas): login, dashboard, inventario, configuración de seguridad de sesión, usuarios, catálogo y carrito del comprador, pago, factura, aviso de inactividad y cierre por inactividad (archivos `01_` a `11_`).

## Créditos

Universidad Manuela Beltrán, Facultad de Ingeniería, Colombia, 2026. Asignatura: Ingeniería de Software - Sistemas Distribuidos.

| Integrante | Rol en el proyecto |
|---|---|
| Santiago Forero Díaz | Documentación del proyecto (análisis, planteamiento y organización de los apartados) |
| Johan Sebastián Martínez Rodríguez | Backend (lógica del sistema, datos y mecanismo interno) |
| Bryan Andrés Puentes Vargas | Frontend (diseño e implementación de la interfaz gráfica) |

Docente: Juan José Osorio Tabares.
