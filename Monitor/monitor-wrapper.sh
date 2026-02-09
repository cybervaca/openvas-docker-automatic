#!/bin/bash
#
# Wrapper script para ejecutar monitor.py con el entorno virtual activado
# Este script activa el entorno virtual antes de ejecutar el monitor
#

set -e  # Salir si hay algún error

# Directorio del entorno virtual
VENV_DIR="/opt/gvm/gvm"

# Verificar que el entorno virtual existe
if [ ! -f "$VENV_DIR/bin/activate" ]; then
    echo "ERROR: No se encontró el entorno virtual en $VENV_DIR" >&2
    exit 1
fi

# Activar entorno virtual
source "$VENV_DIR/bin/activate"

# Verificar que python3 está disponible después de activar
if ! command -v python3 >/dev/null 2>&1; then
    echo "ERROR: python3 no está disponible después de activar el entorno virtual" >&2
    exit 1
fi

# Verificar que el módulo gvm está disponible
if ! python3 -c "from gvm.connections import TLSConnection" 2>/dev/null; then
    echo "ERROR: No se puede importar gvm.connections después de activar el entorno virtual" >&2
    echo "Verifica que python-gvm esté instalado en el entorno virtual" >&2
    exit 1
fi

# Ejecutar el monitor
exec python3 /opt/gvm/Monitor/monitor.py "$@"

