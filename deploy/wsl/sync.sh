#!/usr/bin/env bash
# Sincroniza el codigo del servidor (server/ y shared/) a ~/.inventario/app (filesystem de Linux).
# Por que copia y no ejecutar desde /mnt/c: el acceso a /mnt/c (9p/drvfs) es mucho mas lento en el
# arranque (miles de imports) y la copia demuestra que el servidor corre solo con Linux.
set -euo pipefail
. "$(dirname "${BASH_SOURCE[0]}")/_comun.sh"

mkdir -p "$INV_APP"
for d in server shared; do
    [ -d "$INV_REPO/$d" ] || { inv_err "No existe $INV_REPO/$d"; exit 1; }
    mkdir -p "$INV_APP/$d"
    rsync -a --delete --exclude '__pycache__' --exclude '*.pyc' \
        "$INV_REPO/$d/" "$INV_APP/$d/"
done
inv_log "Codigo sincronizado: $INV_REPO -> $INV_APP"
