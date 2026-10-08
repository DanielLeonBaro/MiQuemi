#!/bin/sh
set -eu
CDPATH= cd -- "$(dirname -- "$0")"
if ! command -v python3 >/dev/null 2>&1 || ! python3 -c 'import sys; sys.exit(sys.version_info < (3, 10))' >/dev/null 2>&1; then
    printf '%s\n' 'Necesitas Python 3.10 o posterior. Instala python3 y python3-venv con el gestor de paquetes de tu distribucion.' >&2
    exit 1
fi
export HOST=127.0.0.1
export PORT=8000
printf '%s\n' 'Iniciando MiQuemi. Conserva esta terminal abierta mientras usas la pagina.'
exec python3 -u server.py --open-browser
