#!/usr/bin/env bash
# Instancia AISLADA del servidor para las pruebas E2E (no toca ~/.inventario/data ni el puerto 8000).
#
# Uso:  wsl_server.sh start  <id> <puerto> <repo_en_wsl>   (credenciales por entorno)
#       wsl_server.sh stop   <id>                           (SIGTERM solo al PID registrado)
#       wsl_server.sh status <id>
#       wsl_server.sh clean  <id>                           (borra /tmp/inv_e2e_<id>)
#
# Reutiliza el venv de ~/.inventario/venv (solo lectura) y una COPIA propia del codigo del repo
# en /tmp/inv_e2e_<id>/app (rsync de server/ y shared/); datos, logs y PID viven en /tmp/inv_e2e_<id>.
# Variables que lee `start`: INVENTARIO_ADMIN_PASSWORD, INVENTARIO_COMPRADOR_PASSWORD.
set -uo pipefail

accion="${1:-}"; id="${2:-}"
[[ "$id" =~ ^[A-Za-z0-9_]+$ ]] || { echo "id invalido" >&2; exit 64; }
E="/tmp/inv_e2e_${id}"
PIDF="$E/server.pid"
PY="${INVENTARIO_E2E_VENV:-$HOME/.inventario/venv}/bin/python"

pid_vivo() {  # imprime el PID si esta vivo y es NUESTRO server.main (cwd = $E/app)
    [ -f "$PIDF" ] || return 1
    local p; p="$(tr -dc '0-9' < "$PIDF")"
    [ -n "$p" ] && kill -0 "$p" 2>/dev/null || return 1
    tr '\0' ' ' < "/proc/$p/cmdline" 2>/dev/null | grep -q 'server\.main' || return 1
    [ "$(readlink "/proc/$p/cwd" 2>/dev/null)" = "$E/app" ] || return 1
    echo "$p"
}

case "$accion" in
start)
    puerto="${3:-}"; repo="${4:-}"
    [[ "$puerto" =~ ^[0-9]+$ ]] || { echo "puerto invalido" >&2; exit 64; }
    [ -x "$PY" ] || { echo "no existe el venv: $PY" >&2; exit 1; }
    if p="$(pid_vivo)"; then echo "ya en marcha PID=$p"; exit 0; fi
    if (exec 3<>"/dev/tcp/127.0.0.1/$puerto") 2>/dev/null; then echo "puerto $puerto ocupado" >&2; exit 2; fi
    mkdir -p "$E/data" "$E/logs" "$E/app/server" "$E/app/shared"
    if [ -n "$repo" ]; then
        for d in server shared; do
            rsync -a --delete --exclude '__pycache__' --exclude '*.pyc' "$repo/$d/" "$E/app/$d/" || exit 1
        done
    fi
    cd "$E/app" || exit 1
    env INVENTARIO_DATA_DIR="$E/data" INVENTARIO_DB="$E/data/inventario.db" \
        INVENTARIO_LOG_DIR="$E/logs" INVENTARIO_HOST=0.0.0.0 INVENTARIO_PORT="$puerto" \
        PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
        nohup setsid "$PY" -m server.main >> "$E/logs/stdout.log" 2>&1 < /dev/null &
    echo $! > "$PIDF"
    p="$(cat "$PIDF")"
    for _ in $(seq 1 120); do
        kill -0 "$p" 2>/dev/null || { echo "el servidor termino al arrancar" >&2; tail -n 20 "$E/logs/stdout.log" >&2; exit 1; }
        if "$PY" -c "import sys,urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:$puerto/api/v1/health',timeout=2).status==200 else 1)" 2>/dev/null; then
            echo "OK PID=$p puerto=$puerto"; exit 0
        fi
        sleep 0.25
    done
    echo "timeout esperando health" >&2; tail -n 20 "$E/logs/stdout.log" >&2; exit 1
    ;;
stop)
    if p="$(pid_vivo)"; then
        kill -TERM "$p"
        for _ in $(seq 1 60); do kill -0 "$p" 2>/dev/null || break; sleep 0.25; done
        if kill -0 "$p" 2>/dev/null; then kill -KILL "$p"; echo "KILL PID=$p"; else echo "detenido PID=$p"; fi
    else
        echo "no hay proceso propio en marcha"
    fi
    rm -f "$PIDF"
    ;;
status)
    if p="$(pid_vivo)"; then echo "PID=$p"; else echo "detenido"; exit 3; fi
    ;;
clean)
    if pid_vivo >/dev/null; then echo "sigue en marcha; haga stop primero" >&2; exit 1; fi
    case "$E" in /tmp/inv_e2e_*) rm -rf -- "$E"; echo "borrado $E";; *) exit 1;; esac
    ;;
*)  echo "uso: $0 start|stop|status|clean <id> ..." >&2; exit 64;;
esac
