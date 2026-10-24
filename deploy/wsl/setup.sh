#!/usr/bin/env bash
# Preparacion idempotente del servidor en WSL/Ubuntu. No usa sudo ni instala paquetes del sistema.
# Requisitos previos (si faltan se indican): python3, python3-venv, rsync.
set -euo pipefail
. "$(dirname "${BASH_SOURCE[0]}")/_comun.sh"

faltan=()
command -v python3 >/dev/null || faltan+=("python3")
command -v rsync >/dev/null || faltan+=("rsync")
python3 -c 'import venv, ensurepip' 2>/dev/null || faltan+=("python3-venv")
if [ "${#faltan[@]}" -gt 0 ]; then
    inv_err "Faltan paquetes del sistema: ${faltan[*]}"
    echo "Instalelos usted (requiere su contrasena de sudo):" >&2
    echo "  sudo apt update && sudo apt install -y python3 python3-venv python3-pip rsync" >&2
    exit 1
fi

mkdir -p "$INV_HOME" "$INV_DATA" "$INV_LOGS" "$INV_RUN"
chmod 700 "$INV_HOME" "$INV_DATA"

# 1) venv en el filesystem de Linux
if [ ! -x "$INV_PY" ]; then
    inv_log "Creando venv en $INV_VENV"
    python3 -m venv "$INV_VENV"
fi
inv_log "Instalando requirements-server.txt (solo dependencias del servidor)"
"$INV_PY" -m pip install --quiet --disable-pip-version-check -r "$INV_REPO/requirements-server.txt"

# 2) Codigo
bash "$(dirname "${BASH_SOURCE[0]}")/sync.sh"

# 3) Credenciales de demo (solo la primera vez; nunca dentro del repo)
if [ ! -f "$INV_CRED" ]; then
    gen() { "$INV_PY" -c 'import secrets; print(secrets.token_urlsafe(12))'; }
    ADMIN_PW="$(gen)"; COMP_PW="$(gen)"
    ( umask 077
      printf 'INVENTARIO_ADMIN_PASSWORD=%s\nINVENTARIO_COMPRADOR_PASSWORD=%s\n' "$ADMIN_PW" "$COMP_PW" > "$INV_CRED" )
    chmod 600 "$INV_CRED"
    echo "============================================================"
    echo " Credenciales de DEMO generadas (se muestran una sola vez):"
    echo "   admin     : $ADMIN_PW"
    echo "   comprador : $COMP_PW"
    echo " Guardadas en $INV_CRED (permisos 600)."
    echo " Solo surten efecto al crear la BD; si ya existe $INV_DATA/inventario.db,"
    echo " borre los datos de demo (ver docs/DESPLIEGUE.md) para aplicarlas."
    echo "============================================================"
else
    inv_log "Credenciales ya existentes en $INV_CRED (no se regeneran)."
fi

inv_log "Setup completo. Arranque con: bash $INV_REPO/deploy/wsl/start_server.sh"
