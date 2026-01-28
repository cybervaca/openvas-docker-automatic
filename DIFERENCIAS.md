# Diferencias Clave con el Proyecto Original

Este documento resume las diferencias principales entre este proyecto (`openvas-docker-automatic`) y el proyecto original (`automatic-openvas`).

## Cambios Principales

### 1. Scripts Principales Simplificados

**Antes (automatic-openvas):**
- Usaba `set-TT.py` y múltiples versiones de scripts
- Mezcla de conexiones (Unix Socket y TLS)

**Ahora (openvas-docker-automatic):**
- **SIEMPRE** usa `set-tt.py` y `run-task.py` (nombres simplificados)
- Conexión TLS consistente (puerto 9390) en scripts principales
- Unix Socket solo para reportes

### 2. Cambio de Ruta Base

**Antes:**
```
/home/redteam/gvm/
```

**Ahora:**
```
/opt/gvm/
```

Todos los archivos modificados:
- ✅ `Config/config_example.json` - Sin cambios en el path interno
- ✅ `Targets_Tasks/run-task.py` - `/opt/gvm/Config/config.json`
- ✅ `Targets_Tasks/delete-files.py` - `/opt/gvm/` en todas las rutas
- ✅ `Reports/get-reports-test.py` - `/opt/gvm/Reports` y `/opt/gvm/Config/config.json`
- ✅ `Reports/subida_share.py` - `/opt/gvm/Config/config.json`
- ✅ `Reports/upload-reports.py` - `/opt/gvm/Config/config.json` y `/opt/gvm/Targets_Tasks/delete-files.py`
- ✅ `Maintenance/maintenance.py` - `/opt/gvm/` en todas las rutas y locks
- ✅ `Cron/*.sh` - `/opt/gvm/` en todas las rutas

### 3. Scripts que SIEMPRE se Usan

| Script | Propósito | Conexión |
|--------|-----------|----------|
| `set-tt.py` | Crear targets y tasks | TLS (9390) |
| `run-task.py` | Ejecutar y gestionar tasks | TLS (9390) |
| `get-reports-test.py` | Exportar reportes | Unix Socket |
| `delete-files.py` | Limpiar BD y archivos | Unix Socket |
| `maintenance.py` | Mantenimiento completo | Unix Socket |

### 4. Archivo de Lock de Mantenimiento

**Antes:**
```
/home/redteam/gvm/.maintenance.lock
```

**Ahora:**
```
/opt/gvm/.maintenance.lock
```

### 5. Configuración

**Ubicación:**
- Antes: `/home/redteam/gvm/Config/config.json`
- Ahora: `/opt/gvm/Config/config.json`

**Lectura en scripts:**
- Todos los scripts adaptados para leer desde `/opt/gvm/Config/config.json`

### 6. Logs

**Ubicaciones actualizadas:**
- `/opt/gvm/logs/maintenance/` - Reportes de mantenimiento
- `/opt/gvm/taskslog.txt` - Log de ejecución de tasks
- `/opt/gvm/tasksend.txt` - Información de tasks finalizadas
- `/opt/gvm/logbalbix.txt` - Log de subidas a Balbix

### 7. Entorno Virtual

**Ubicación:**
- Antes: `/home/redteam/gvm/gvm/`
- Ahora: `/opt/gvm/gvm/`

**Scripts de Cron actualizados:**
```bash
VIRTUAL_ENV="/opt/gvm/gvm"
```

## Tabla de Comparación Rápida

| Característica | automatic-openvas | openvas-docker-automatic |
|----------------|-------------------|--------------------------|
| **Ruta base** | `/home/redteam/gvm` | `/opt/gvm/` |
| **Scripts principales** | `set-TT.py` (mezcla) | `set-tt.py`, `run-task.py` |
| **Conexión targets/tasks** | Variable | TLS (9390) |
| **Conexión reportes** | Unix Socket | Unix Socket |
| **Lock mantenimiento** | `/home/redteam/gvm/.maintenance.lock` | `/opt/gvm/.maintenance.lock` |
| **Config path** | `/home/redteam/gvm/Config/` | `/opt/gvm/Config/` |
| **Entorno virtual** | `/home/redteam/gvm/gvm/` | `/opt/gvm/gvm/` |

## Archivos Creados/Modificados

### Archivos Nuevos
- ✅ `DIFERENCIAS.md` - Este archivo
- ✅ `CHANGELOG.md` - Registro de cambios
- ✅ `.gitignore` - Ignorar archivos sensibles
- ✅ `Targets_Tasks/openvas.csv.example` - Plantilla CSV

### Archivos Adaptados (todos los paths cambiados)
- ✅ `Targets_Tasks/set-tt.py` (sin cambios de path, ya usa TLS)
- ✅ `Targets_Tasks/run-task.py`
- ✅ `Targets_Tasks/delete-files.py`
- ✅ `Reports/get-reports-test.py`
- ✅ `Reports/subida_share.py`
- ✅ `Reports/upload-reports.py`
- ✅ `Maintenance/maintenance.py`
- ✅ `Cron/run_task.sh`
- ✅ `Cron/maintenance.sh`
- ✅ `Cron/actualiza_gvm.sh`
- ✅ `Cron/cron-update.sh`
- ✅ `Cron/update-script.sh`
- ✅ `Cron/procesos.sh`

### Archivos Sin Cambios
- ✅ `Config/config_example.json` (estructura igual)
- ✅ `requirements.txt` (dependencias iguales)

## Instrucciones de Migración

Si tienes el proyecto original y quieres migrar:

1. **Backup de configuración:**
```bash
cp /home/redteam/gvm/Config/config.json /tmp/config.json.backup
```

2. **Copiar proyecto a nueva ubicación:**
```bash
sudo mkdir -p /opt/gvm
sudo cp -r /home/cybervaca/apps/devs/openvas-docker-automatic/* /opt/gvm/
```

3. **Restaurar configuración:**
```bash
cp /tmp/config.json.backup /opt/gvm/Config/config.json
```

4. **Crear entorno virtual:**
```bash
cd /opt/gvm
python3 -m venv gvm
source gvm/bin/activate
pip3 install -r requirements.txt
```

5. **Actualizar crontab:**
```bash
crontab -e
# Cambiar todos los paths de /home/redteam/gvm a /opt/gvm
```

6. **Copiar CSV de targets:**
```bash
cp /home/redteam/gvm/Targets_Tasks/openvas.csv /opt/gvm/Targets_Tasks/openvas.csv
```

7. **Verificar permisos:**
```bash
chmod +x /opt/gvm/Cron/*.sh
```

## Verificación Post-Instalación

```bash
# Verificar estructura
tree /opt/gvm -L 2

# Verificar entorno virtual
source /opt/gvm/gvm/bin/activate
python3 -c "import gvm; print('GVM importado correctamente')"

# Verificar configuración
python3 -c "import json; print(json.load(open('/opt/gvm/Config/config.json'))['user'])"

# Verificar scripts
/opt/gvm/Cron/run_task.sh --help 2>&1 | head -n 5
```

## Soporte

Para problemas o dudas sobre las diferencias:
1. Revisar este documento
2. Consultar el README.md para detalles de configuración
3. Verificar que todas las rutas usen `/opt/gvm/`
4. Confirmar que solo se usen `set-tt.py` y `run-task.py`

