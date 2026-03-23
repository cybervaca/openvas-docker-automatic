#!/bin/bash
set -euo pipefail

CONTAINER_NAME="${OPENVAS_CONTAINER:-openvas}"

# Ejecuta la actualización de feeds dentro del contenedor (flujo Docker).
if ! docker ps --format '{{.Names}}' | grep -qx "${CONTAINER_NAME}"; then
  echo "ERROR: No existe (o no está corriendo) el contenedor '${CONTAINER_NAME}'."
  echo "Ejecuta: docker ps -a | grep ${CONTAINER_NAME}"
  exit 1
fi

echo "Actualizando feeds OpenVAS en contenedor '${CONTAINER_NAME}'..."
docker exec "${CONTAINER_NAME}" bash -lc "/scripts/sync.sh"
echo "Feeds actualizados correctamente."




















