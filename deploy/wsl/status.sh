#!/usr/bin/env bash
# Estado del servidor: PID, puerto, health y ultimas lineas del log.
set -uo pipefail
. "$(dirname "${BASH_SOURCE[0]}")/_comun.sh"

estado=1
if pid="$(inv_pid_vivo)"; then
    echo "PID:     $pid (vivo)"
else
    echo "PID:     ninguno (servidor detenido o PID file obsoleto)"
    pid=""
fi
echo "Puerto:  $INV_PORT"
if [ -x "$INV_PY" ] && body="$(inv_health)"; then
    echo "Health:  OK  $body"; estado=0
else
    echo "Health:  SIN RESPUESTA ($INV_HEALTH_URL)"
    if [ -z "$pid" ] && inv_puerto_ocupado; then echo "Aviso:   el puerto $INV_PORT lo usa OTRO proceso"; fi
fi
echo "IP WSL:  $(hostname -I 2>/dev/null | awk '{print $1}')"
echo "Datos:   $INV_DATA"
echo "--- ultimas lineas de $INV_LOGS/servidor.log ---"
tail -n 8 "$INV_LOGS/servidor.log" 2>/dev/null || echo "(sin log aun)"
exit $estado
