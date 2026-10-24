#!/usr/bin/env bash
# Funciones y rutas compartidas por los scripts de deploy/wsl (se usa con `source`).
# Todo vive en el filesystem de Linux: ~/.inventario/{venv,app,data,logs,run,credenciales.env}

INV_HOME="${INVENTARIO_HOME:-$HOME/.inventario}"
INV_VENV="$INV_HOME/venv"
INV_APP="$INV_HOME/app"
INV_DATA="$INV_HOME/data"
INV_LOGS="$INV_HOME/logs"
INV_RUN="$INV_HOME/run"
INV_PID="$INV_RUN/servidor.pid"
INV_CRED="$INV_HOME/credenciales.env"
INV_PY="$INV_VENV/bin/python"

# Raiz del repo (dos niveles sobre deploy/wsl)
INV_REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

INV_PORT="${INVENTARIO_PORT:-8000}"
INV_HEALTH_URL="http://127.0.0.1:${INV_PORT}/api/v1/health"

inv_log() { printf '[inventario] %s\n' "$*"; }
inv_err() { printf '[inventario] ERROR: %s\n' "$*" >&2; }

# Carga las variables del servidor (datos, logs, credenciales de demo) y las exporta.
inv_cargar_entorno() {
    export INVENTARIO_DATA_DIR="$INV_DATA"
    export INVENTARIO_DB="${INVENTARIO_DB:-$INV_DATA/inventario.db}"
    export INVENTARIO_LOG_DIR="$INV_LOGS"
    export INVENTARIO_HOST="${INVENTARIO_HOST:-0.0.0.0}"
    export INVENTARIO_PORT="$INV_PORT"
    if [ -f "$INV_CRED" ]; then
        set -a; . "$INV_CRED"; set +a
    fi
}

# Health con la stdlib de Python (no depende de curl). Imprime el cuerpo; exit 0 si HTTP 200.
inv_health() {
    "$INV_PY" -c '
import sys, urllib.request
try:
    with urllib.request.urlopen(sys.argv[1], timeout=2) as r:
        print(r.read().decode())
        sys.exit(0 if r.status == 200 else 1)
except Exception:
    sys.exit(1)
' "$INV_HEALTH_URL"
}

# PID registrado, solo si sigue vivo Y es nuestro proceso (evita PID reutilizado tras reinicio de WSL).
# Devuelve 0 e imprime el PID; si el archivo es obsoleto lo borra y devuelve 1.
inv_pid_vivo() {
    [ -f "$INV_PID" ] || return 1
    local pid; pid="$(tr -dc '0-9' < "$INV_PID")"
    if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null \
        && tr '\0' ' ' < "/proc/$pid/cmdline" 2>/dev/null | grep -q 'server\.main'; then
        echo "$pid"; return 0
    fi
    rm -f "$INV_PID"
    return 1
}

# 0 si algo escucha en 127.0.0.1:puerto
inv_puerto_ocupado() {
    (exec 3<>"/dev/tcp/127.0.0.1/$INV_PORT") 2>/dev/null
}
