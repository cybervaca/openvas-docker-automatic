#!/bin/bash
#
# Wrapper script para ejecutar monitor.py con el entorno virtual activado
# Este script activa el entorno virtual antes de ejecutar el monitor
#

# Directorio del entorno virtual
VENV_DIR="/opt/gvm/gvm"

# Activar entorno virtual
if [ -f "$VENV_DIR/bin/activate" ]; then
    source "$VENV_DIR/bin/activate"
else
    echo "ERROR: No se encontró el entorno virtual en $VENV_DIR" >&2
    exit 1
fi

# Ejecutar el monitor
exec python3 /opt/gvm/Monitor/monitor.py "$@"

