# Update Scripts

Scripts para alinear `/opt/gvm` con `origin/main` en flotas de servidores.

## Por qué no usamos `git pull`

En Git reciente, `git pull` sin estrategia configurada falla si las ramas
divergieron:

```text
fatal: Necesita especificar cómo reconciliar las ramas divergentes.
```

En despliegue el repo de automatización **debe coincidir con GitHub**.
Por eso la actualización hace:

```bash
git fetch origin
git checkout main
git reset --hard origin/main
```

`Config/config.json` y el resto de ficheros en `.gitignore` **no se borran**.

## Archivos

### `sync-from-github.sh` (recomendado en flota)

```bash
bash /opt/gvm/Update/sync-from-github.sh
```

**Emergencia** (el `pull` local está roto y aún no tienes este script):

```bash
curl -fsSL https://raw.githubusercontent.com/cybervaca/openvas-docker-automatic/main/Update/sync-from-github.sh | bash
```

### `update-script.py`

Misma lógica en Python:

```bash
cd /opt/gvm/Update
python3 update-script.py
# opcional: python3 update-script.py -p /opt/gvm -b main
```

## Comando one-liner (sin descargar script)

En cualquier servidor bloqueado ahora mismo:

```bash
cd /opt/gvm && git fetch origin && git checkout main && git reset --hard origin/main
```

## Cron

```cron
# Actualizar automatización cada domingo 03:00
0 3 * * 0 /bin/bash /opt/gvm/Update/sync-from-github.sh >> /opt/gvm/logs/git-update.log 2>&1
```

## Notas

- Descarta commits/cambios locales en ficheros **rastreado**s (correcto para flota).
- No ejecuta `git clean -fd` (no borra CSV/logs locales no versionados).
- No modifica `git config` global del servidor.
