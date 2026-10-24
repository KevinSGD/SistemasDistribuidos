#!/usr/bin/env bash
# Detiene SOLO el servidor registrado en el PID file (SIGTERM). Con --force y tras el timeout, SIGKILL.
set -uo pipefail
. "$(dirname "${BASH_SOURCE[0]}")/_comun.sh"

if ! pid="$(inv_pid_vivo)"; then
    inv_log "El servidor no esta en marcha (PID file ausente u obsoleto, limpiado)."
    exit 0
fi
inv_log "Enviando SIGTERM a PID $pid"
kill -TERM "$pid" 2>/dev/null
for _ in $(seq 1 40); do
    kill -0 "$pid" 2>/dev/null || { rm -f "$INV_PID"; inv_log "Servidor detenido."; exit 0; }
    sleep 0.25
done
if [ "${1:-}" = "--force" ]; then
    kill -KILL "$pid" 2>/dev/null; rm -f "$INV_PID"; inv_log "Servidor terminado con SIGKILL."; exit 0
fi
inv_err "PID $pid no termino en 10s. Reintente con: bash $INV_REPO/deploy/wsl/stop_server.sh --force"
exit 1
