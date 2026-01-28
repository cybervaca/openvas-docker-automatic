#!/bin/bash

# Wrapper script para ejecutar el script de mantenimiento de OpenVAS
# Uso: ./maintenance.sh [--dry-run] [--verbose] [--no-email]

VIRTUAL_ENV="/opt/gvm/gvm"
SCRIPT_PATH="/opt/gvm/Maintenance/maintenance.py"

# Activar entorno virtual
source "$VIRTUAL_ENV/bin/activate"

# Ejecutar script de mantenimiento con todos los argumentos pasados
python3 "$SCRIPT_PATH" "$@"

# Desactivar entorno virtual
deactivate

