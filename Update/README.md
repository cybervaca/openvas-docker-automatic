# Update Scripts

Script para actualizar el repositorio de automatización de OpenVAS desde GitHub.

## Archivo

### update-script.py

Script para actualizar automáticamente el repositorio manteniendo la configuración de targets.

**Funcionalidad:**
1. Descarga `export-target.py` desde GitHub
2. Exporta los targets actuales a `openvas.csv.export` (backup)
3. Hace git pull forzado del repositorio
4. Restaura `openvas.csv` desde el backup

Esto permite actualizar los scripts de automatización sin perder la configuración de targets y tasks existentes.

**Uso:**
```bash
cd /opt/gvm/Update
python3 update-script.py

# Forzar actualización aunque la versión sea la misma
python3 update-script.py --force
```

**Argumentos:**
- `--force`: Forzar actualización incluso si la versión local es la misma que la remota

## Cómo Funciona

### Proceso de Actualización

1. **Verificación de Versión**
   - Lee la versión local desde `Config/config_example.json`
   - Obtiene la versión remota desde GitHub
   - Compara ambas versiones

2. **Verificación de Cambios Remotos**
   - Ejecuta `git fetch origin`
   - Compara HEAD local con `origin/main`
   - Detecta si hay commits nuevos en el repositorio remoto

3. **Backup de Configuración**
   - Descarga `export-target.py` desde GitHub
   - Ejecuta el script para exportar todos los targets actuales
   - Guarda el resultado en `openvas.csv.export`

4. **Actualización del Repositorio**
   - Ejecuta `git reset --hard HEAD` (descarta cambios locales)
   - Ejecuta `git fetch origin`
   - Ejecuta `git reset --hard origin/main` (actualización forzada)

5. **Restauración de Configuración**
   - Copia `openvas.csv.export` a `openvas.csv`
   - Los targets y tasks se mantienen intactos

### Seguridad de Datos

El script garantiza que:
- ✅ Los targets actuales se respaldan antes de actualizar
- ✅ El archivo `openvas.csv` se restaura después del pull
- ✅ No se pierden configuraciones de escaneos
- ✅ Los cambios locales se sobrescriben (actualización limpia)

## Requisitos

### Dependencias Python
```bash
pip3 install requests
```

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

## Cuándo se Ejecuta la Actualización

El script actualiza el repositorio en los siguientes casos:

1. **Versión Diferente**
   - Si `version` en `config_example.json` local es diferente a la remota

2. **Commits Nuevos Detectados**
   - Si hay commits en `origin/main` que no están en la rama local
   - Incluso si la versión es la misma

3. **Modo Forzado**
   - Si se usa la opción `--force`
   - Actualiza sin importar versión o commits

4. **Error al Verificar**
   - Si hay error al leer versiones o verificar git
   - Para garantizar que siempre esté actualizado

## Logs y Archivos Generados

### Durante la Ejecución
- **openvas.csv.export**: Backup temporal de targets
  - Ubicación: `/opt/gvm/Targets_Tasks/openvas.csv.export`
  - Se genera antes del git pull
  - Se usa para restaurar después de la actualización

### Salida del Script
```bash
# Ejemplo de salida normal
Verificando versiones...
Se detectaron 3 commit(s) remoto(s) disponible(s)
Paso 1: Descargando export-target.py...
Archivo descargado: /opt/gvm/Targets_Tasks/export-target.py
Paso 2: Ejecutando export-target.py...
Export completado: /opt/gvm/Targets_Tasks/openvas.csv.export
Paso 3: Haciendo git pull forzado...
Git pull forzado completado
Paso 4: Restaurando openvas.csv desde backup...
Backup restaurado: /opt/gvm/Targets_Tasks/openvas.csv
Actualización completada exitosamente
```

## Automatización con Cron

### Actualización Diaria del Repositorio
```bash
crontab -e
```

Agregar:
```cron
# Verificar actualizaciones del repositorio diariamente a las 2:00 AM
0 2 * * * cd /opt/gvm && source gvm/bin/activate && python3 /opt/gvm/Update/update-script.py >> /opt/gvm/logs/update-repo.log 2>&1
```

### Actualización Semanal
```cron
# Verificar actualizaciones cada lunes a las 3:00 AM
0 3 * * 1 cd /opt/gvm && source gvm/bin/activate && python3 /opt/gvm/Update/update-script.py >> /opt/gvm/logs/update-repo.log 2>&1
```

### Forzar Actualización Mensual
```cron
# Forzar actualización el primer día de cada mes
0 4 1 * * cd /opt/gvm && source gvm/bin/activate && python3 /opt/gvm/Update/update-script.py --force >> /opt/gvm/logs/update-repo.log 2>&1
```

## Ejemplos de Uso

### Actualización Manual
```bash
# Navegar al directorio
cd /opt/gvm/Update

# Activar entorno virtual si es necesario
source ../gvm/bin/activate

# Ejecutar actualización
python3 update-script.py
```

### Verificar Estado Antes de Actualizar
```bash
cd /opt/gvm

# Ver versión local
cat Config/config_example.json | grep version

# Ver última versión en GitHub
curl -s https://raw.githubusercontent.com/cybervaca/openvas-docker-automatic/main/Config/config_example.json | grep version

# Ver commits pendientes
git fetch origin
git log HEAD..origin/main --oneline
```

### Actualización Forzada
```bash
cd /opt/gvm/Update
python3 update-script.py --force
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

### Error: Git pull forzado falla
```bash
# Verificar estado del repositorio
cd /opt/gvm
git status

# Limpiar cambios locales manualmente
git reset --hard HEAD
git clean -fd

# Intentar actualización manual
git fetch origin
git reset --hard origin/main
```

### Error: No se encuentra export-target.py
```bash
# Descargar manualmente
cd /opt/gvm/Targets_Tasks
wget https://raw.githubusercontent.com/cybervaca/openvas-docker-automatic/main/Targets_Tasks/export-target.py
chmod +x export-target.py
```

### Error: Falla al ejecutar export-target.py
```bash
# Verificar que exista config.json
ls -la /opt/gvm/Config/config.json

# Verificar conexión a OpenVAS
cd /opt/gvm/Targets_Tasks
python3 export-target.py -c /opt/gvm/Config/config.json -o /opt/gvm/Targets_Tasks/openvas.csv.export
```

### Backup se Perdió
```bash
# Si openvas.csv.export no existe después de error
cd /opt/gvm/Targets_Tasks

# Restaurar desde git (última versión commiteada)
git checkout HEAD -- openvas.csv

# O recrear manualmente desde la interfaz de OpenVAS
# y luego crear el CSV con el formato: Titulo;Rango;Desc
```

### Actualización No Detecta Cambios
```bash
# Forzar actualización
cd /opt/gvm/Update
python3 update-script.py --force

# O actualizar manualmente
cd /opt/gvm
git pull origin main
```

## Notas Importantes

1. **Backup Automático**: El script siempre hace backup de `openvas.csv` antes de actualizar
2. **Actualización Limpia**: Los cambios locales se descartan (`git reset --hard`)
3. **Verificación Dual**: Verifica tanto versión como commits nuevos
4. **Configuración Segura**: `openvas.csv` se restaura automáticamente después del pull
5. **No Actualiza OpenVAS**: Solo actualiza los scripts de automatización, no OpenVAS en sí

## ¿Qué NO Hace Este Script?

❌ No actualiza componentes de OpenVAS (gvmd, ospd-openvas, scanner, etc.)
❌ No actualiza feeds de vulnerabilidades
❌ No reinicia servicios de OpenVAS
❌ No modifica la instalación de OpenVAS
❌ No actualiza la base de datos de OpenVAS

✅ Solo actualiza los scripts Python y shell de automatización
✅ Solo actualiza documentación y configuración del repositorio
✅ Solo hace git pull del repositorio `openvas-docker-automatic`

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
