#!/bin/bash
# Sincroniza /opt/gvm con origin/main sin usar "git pull".
# Evita: "Necesita especificar cómo reconciliar las ramas divergentes"
#
# Uso local (si el repo ya tiene este script):
#   bash /opt/gvm/Update/sync-from-github.sh
#
# Uso de emergencia en flota (sin depender del script local antiguo):
#   curl -fsSL https://raw.githubusercontent.com/cybervaca/openvas-docker-automatic/main/Update/sync-from-github.sh | bash
#
# Variables opcionales:
#   REPO_PATH=/opt/gvm BRANCH=main REMOTE=origin

set -euo pipefail

REPO_PATH="${REPO_PATH:-/opt/gvm}"
BRANCH="${BRANCH:-main}"
REMOTE="${REMOTE:-origin}"

cd "$REPO_PATH"

echo "============================================================"
echo "sync-from-github: $REPO_PATH → ${REMOTE}/${BRANCH}"
echo "============================================================"

git remote get-url "$REMOTE" >/dev/null
echo "→ git fetch $REMOTE"
git fetch "$REMOTE"

BEFORE="$(git rev-parse --short HEAD)"
TARGET_SHA="$(git rev-parse --short "${REMOTE}/${BRANCH}")"

if [[ "$BEFORE" == "$TARGET_SHA" ]]; then
  echo "✓ Ya actualizado en $BEFORE"
  exit 0
fi

echo "  Local:  $BEFORE"
echo "  Remoto: $TARGET_SHA"

# Asegurar rama local
if git show-ref --verify --quiet "refs/heads/${BRANCH}"; then
  git checkout "$BRANCH"
else
  git checkout -B "$BRANCH" "${REMOTE}/${BRANCH}"
fi

echo "→ git reset --hard ${REMOTE}/${BRANCH}"
git reset --hard "${REMOTE}/${BRANCH}"

AFTER="$(git rev-parse --short HEAD)"
echo "✓ Actualizado $BEFORE → $AFTER"
git log -1 --oneline
echo "  (Config/config.json y ficheros en .gitignore no se tocan)"
