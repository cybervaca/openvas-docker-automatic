# Update Scripts

Script simple para actualizar el repositorio de automatización de OpenVAS desde GitHub.

## Archivo

### update-script.py

Script simplificado que hace `git pull` del repositorio.

**Funcionalidad:**
1. Verifica si hay cambios remotos (`git fetch`)
2. Hace `git pull origin main` si hay actualizaciones
3. Muestra el resultado de la actualización

**No hace backups ni fuerza cambios**, solo un pull limpio.

**Uso:**
```bash
cd /opt/gvm/Update
python3 update-script.py
```

## Cómo Funciona

### Proceso Simplificado

1. **git fetch origin**
   - Obtiene información de cambios remotos

2. **Verificación de Commits**
   - Compara HEAD local con `origin/main`
   - Cuenta cuántos commits hay en remoto

3. **git pull origin main**
   - Si hay cambios, hace pull
   - Si no hay cambios, informa que ya está actualizado

### Características

- ✅ Pull simple y limpio
- ✅ No fuerza cambios (respeta configuración local)
- ✅ No hace backups automáticos
- ✅ Muestra cantidad de commits remotos
- ⚠️ Si hay conflictos locales, el pull puede fallar (comportamiento normal de git)

## Requisitos

### Herramientas del Sistema
- git
- python3

### Configuración
El script requiere que el directorio `/opt/gvm/` sea un repositorio git configurado:

```bash
cd /opt/gvm
git remote -v
# Debe mostrar: origin https://github.com/cybervaca/openvas-docker-automatic.git
```

## Salida del Script

```bash
# Ejemplo de salida cuando hay actualizaciones
============================================================
Script de actualización de OpenVAS (git pull)
============================================================
Verificando actualizaciones en /opt/gvm/...
Se encontraron 3 commit(s) remoto(s)
Actualizando repositorio...
Updating f9da240..e5cb082
Fast-forward
 README.md | 5 +++--
 1 file changed, 3 insertions(+), 2 deletions(-)
✓ Actualización completada exitosamente

✓ Proceso completado
```

```bash
# Ejemplo de salida cuando ya está actualizado
============================================================
Script de actualización de OpenVAS (git pull)
============================================================
Verificando actualizaciones en /opt/gvm/...
✓ Ya estás actualizado, no hay cambios remotos

✓ Proceso completado
```

## Automatización con Cron

Puedes automatizar la actualización del repositorio con cron:

```bash
crontab -e
```

```cron
# Actualización diaria a las 2:00 AM
0 2 * * * /opt/gvm/Cron/update-script.sh >> /opt/gvm/logs/update-repo.log 2>&1

# O actualización semanal (lunes a las 3:00 AM)
0 3 * * 1 /opt/gvm/Cron/update-script.sh >> /opt/gvm/logs/update-repo.log 2>&1
```

## Ejemplos de Uso

### Actualización Manual
```bash
# Usando el wrapper
/opt/gvm/Cron/update-script.sh

# O directamente
cd /opt/gvm/Update
python3 update-script.py
```

### Verificar Commits Pendientes Manualmente
```bash
cd /opt/gvm
git fetch origin
git log HEAD..origin/main --oneline
```

### Ver Qué Cambió Después de Actualizar
```bash
cd /opt/gvm
git log -5 --oneline
git show --stat
```

## Troubleshooting

### Error: No se puede conectar a GitHub
```bash
# Verificar conectividad
curl -I https://github.com

# Verificar configuración de git
cd /opt/gvm
git remote -v

# Si falla, reconfigurar remote
git remote set-url origin https://github.com/cybervaca/openvas-docker-automatic.git
```

### Error: Git pull falla (conflictos locales)
```bash
# Ver qué archivos tienen conflictos
cd /opt/gvm
git status

# Opción 1: Guardar cambios locales (stash)
git stash
python3 /opt/gvm/Update/update-script.py

# Opción 2: Descartar cambios locales
git reset --hard HEAD
git pull origin main
```

### Actualización Manual si el Script Falla
```bash
cd /opt/gvm
git fetch origin
git pull origin main
```

## Notas Importantes

1. **Pull Simple**: El script hace `git pull` estándar, no fuerza cambios
2. **Respeta Configuración Local**: Si hay conflictos, el pull falla (comportamiento normal de git)
3. **No Hace Backups**: Es responsabilidad del usuario hacer backup si modifica archivos
4. **Solo Actualiza Scripts**: No actualiza OpenVAS en sí, solo los scripts de automatización

## ¿Qué NO Hace Este Script?

❌ No actualiza componentes de OpenVAS (gvmd, ospd-openvas, scanner, etc.)
❌ No actualiza feeds de vulnerabilidades
❌ No reinicia servicios de OpenVAS
❌ No modifica la instalación de OpenVAS
❌ No actualiza la base de datos de OpenVAS
❌ No hace backups de configuración
❌ No fuerza cambios (no hace `git reset --hard`)

✅ Solo hace `git pull origin main`
✅ Verifica si hay cambios remotos antes
✅ Muestra información clara del resultado

## Para Actualizar OpenVAS en Docker

Si necesitas actualizar OpenVAS (no los scripts), usa Docker:

```bash
# Detener contenedor
docker-compose down

# Actualizar imagen
docker-compose pull

# Iniciar con nueva versión
docker-compose up -d

# Ver logs
docker-compose logs -f
```

## Referencias

- [Repositorio GitHub](https://github.com/cybervaca/openvas-docker-automatic)
- [Documentación Principal](../README.md)
- [Guía Docker](../DOCKER.md)
- [Changelog](../CHANGELOG.md)
