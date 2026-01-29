# Changelog

## [2.2.0] - 2026-01-29

### Eliminado
- `Maintenance/maintenance.py` - Script de mantenimiento completo removido
- `Cron/maintenance.sh` - Wrapper de mantenimiento eliminado
- Sistema de lock de mantenimiento (`.maintenance.lock`) eliminado de `run-task.py`
- Referencias a mantenimiento eliminadas de toda la documentación

### Actualizado
- `Targets_Tasks/run-task.py` - Eliminada verificación de lock de mantenimiento
- Documentación actualizada (README.md, DOCKER.md, INICIO_RAPIDO.md, DIFERENCIAS.md, DEPENDENCIAS.md)

## [2.1.0] - 2026-01-29

### Añadido
- Archivo `docker-compose.yml` para despliegue con Docker
- Documentación completa de Docker en `DOCKER.md`:
  - Guía de instalación y configuración
  - Integración con scripts de automatización
  - Troubleshooting específico para Docker
  - Información de seguridad y reverse proxy
  - Backup y restauración de datos
- Sección en README.md sobre instalación con Docker

### Mejorado
- Script `subida_share.py` refactorizado:
  - Cambio de argumento `-a` de 'aplicacion' a 'automatizacion'
  - Argumento `-p/--pais` ahora es requerido
  - Nueva estructura de ruta: `General/Subidas/{pais}/{automatizacion}/{SITE}`
  - Muestra URL completa de SharePoint en mensaje de éxito
  - Overwrite forzado por defecto
  - Validación de archivos con `Path()`

### Corregido
- Ruta de subida a SharePoint corregida para eliminar carpeta redundante
- Creación automática de directorios `Reports/exports/` y `Reports/exports/vulns_host/`
- Cambio de `UnixSocketConnection` a `TLSConnection` en todos los scripts para compatibilidad con Docker
- Archivos `.gitkeep` añadidos para asegurar estructura de directorios en Git

### Documentación
- README.md actualizado con opciones de instalación (Docker y Nativa)
- DOCKER.md con guía completa de despliegue en contenedores
- Mejoras en documentación de troubleshooting

## [2.0.0] - 2026-01-28

### Última actualización
- Renombrados scripts principales para simplicidad:
  - `run-task-2.py` → `run-task.py`
  - `set-tt-2.py` → `set-tt.py`
- Actualizada toda la documentación con nuevos nombres

## [2.0.0-initial] - 2026-01-28

### Cambios Mayores
- **Scripts simplificados**: `set-tt.py` y `run-task.py` para comunicación con OpenVAS
- **Cambio de ruta base**: De `/home/redteam/gvm` a `/opt/gvm/`
- **Conexión TLS**: Los scripts principales usan conexión TLS (puerto 9390) en lugar de Unix Socket

### Adaptaciones
- Todos los paths actualizados de `/home/redteam/gvm` a `/opt/gvm/`
- Scripts de Cron actualizados para nueva ruta base
- Reports scripts adaptados para `/opt/gvm/`
- Configuración adaptada para nueva estructura

### Características Mantenidas
- Sistema de lock de mantenimiento
- Verificación de feeds antes de actualizar (>30 días)
- Timeout de 8 horas para actualización de feeds
- Limpieza automática de reportes (90 días)
- Optimización de base de datos con detención de servicios
- Separación de CVEs y Misconfigs
- Subida automática a SharePoint y Balbix/Valbix

### Notas de Migración
Si vienes del proyecto original (`automatic-openvas`):
1. Cambiar todas las referencias de `/home/redteam/gvm` a `/opt/gvm/`
2. Actualizar crontab con nuevos paths
3. Usar siempre `set-tt.py` y `run-task.py`
4. Copiar `config.json` a `/opt/gvm/Config/`
5. Crear directorio `/opt/gvm/` y copiar todos los archivos

### Basado en
- [automatic-openvas v1.2025.09.02_13](https://github.com/cybervaca/automatic-openvas)

