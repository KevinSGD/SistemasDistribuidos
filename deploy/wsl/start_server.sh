#!/usr/bin/env bash
# Arranca el servidor en segundo plano (nohup + setsid), con PID file y log, y espera al health.
# Variables opcionales: INVENTARIO_PORT (8000), INVENTARIO_HOST (0.0.0.0), ESPERA_S (30), SIN_SYNC=1.
set -uo pipefail
. "$(dirname "${BASH_SOURCE[0]}")/_comun.sh"

[ -x "$INV_PY" ] || { inv_err "No hay venv. Ejecute primero: bash $INV_REPO/deploy/wsl/setup.sh"; exit 1; }
mkdir -p "$INV_DATA" "$INV_LOGS" "$INV_RUN"

if pid="$(inv_pid_vivo)"; then
    inv_log "El servidor ya esta en marcha (PID $pid)."
    if inv_health >/dev/null; then inv_log "OK: $INV_HEALTH_URL responde."; exit 0; fi
    inv_err "El proceso existe pero /health no responde. Revise: bash $INV_REPO/deploy/wsl/status.sh"
    exit 1
fi

if inv_puerto_ocupado; then
    inv_err "El puerto $INV_PORT ya esta ocupado por otro proceso (no es este servidor)."
    echo "  Quien lo usa:  ss -ltnp 'sport = :$INV_PORT'" >&2
    echo "  O use otro puerto:  INVENTARIO_PORT=8001 bash $INV_REPO/deploy/wsl/start_server.sh" >&2
    exit 2
fi

if [ "${SIN_SYNC:-0}" != "1" ] && [ -d "$INV_REPO/server" ]; then
    bash "$(dirname "${BASH_SOURCE[0]}")/sync.sh" >/dev/null || { inv_err "Fallo la sincronizacion"; exit 1; }
fi
[ -d "$INV_APP/server" ] || { inv_err "Falta $INV_APP/server. Ejecute setup.sh o sync.sh"; exit 1; }

inv_cargar_entorno
cd "$INV_APP"
nohup setsid "$INV_PY" -m server.main >> "$INV_LOGS/stdout.log" 2>&1 < /dev/null &
pid=$!
echo "$pid" > "$INV_PID"
inv_log "Lanzado PID $pid, esperando /health (max ${ESPERA_S:-30}s)..."

for _ in $(seq 1 $(( ${ESPERA_S:-30} * 2 ))); do
    if ! kill -0 "$pid" 2>/dev/null; then
        rm -f "$INV_PID"
        inv_err "El servidor termino al arrancar. Ultimas lineas de $INV_LOGS/stdout.log:"
        tail -n 15 "$INV_LOGS/stdout.log" >&2
        exit 1
    fi
    if body="$(inv_health)"; then
        inv_log "OK  PID=$pid  puerto=$INV_PORT  health=$body"
        exit 0
    fi
    sleep 0.5
done
inv_err "Timeout esperando /health. Ultimas lineas:"
tail -n 15 "$INV_LOGS/stdout.log" >&2
exit 1
