# Inicio Rápido - openvas-docker-automatic

## TL;DR - Para Empezar en 5 Minutos

### 1. Copiar el Proyecto
```bash
sudo cp -r /home/cybervaca/apps/devs/openvas-docker-automatic /opt/gvm
cd /opt/gvm
```

### 2. Configurar Entorno Virtual
```bash
python3 -m venv gvm
source gvm/bin/activate
pip3 install -r requirements.txt
```

### 3. Configurar
```bash
# Copiar y editar configuración
cp Config/config_example.json Config/config.json
nano Config/config.json  # Editar con tus valores

# Copiar plantilla CSV
cp Targets_Tasks/openvas.csv.example Targets_Tasks/openvas.csv
nano Targets_Tasks/openvas.csv  # Añadir tus targets
```

### 4. Crear Targets y Tasks
```bash
cd /opt/gvm/Targets_Tasks
source /opt/gvm/gvm/bin/activate
python3 set-tt.py
# Ingresar contraseña de OpenVAS cuando se solicite
```

### 5. Ejecutar Primera Task
```bash
cd /opt/gvm/Targets_Tasks
source /opt/gvm/gvm/bin/activate
python3 run-task.py
```

### 6. Configurar Cron (Opcional)
```bash
crontab -e
# Añadir:
*/15 * * * * /opt/gvm/Cron/run_task.sh
0 2 1 * * /opt/gvm/Cron/maintenance.sh
```

## Comandos Más Usados

### Crear Targets y Tasks desde CSV
```bash
cd /opt/gvm/Targets_Tasks
source /opt/gvm/gvm/bin/activate
python3 set-tt.py
```

### Ejecutar/Verificar Tasks
```bash
cd /opt/gvm/Targets_Tasks
source /opt/gvm/gvm/bin/activate
python3 run-task.py
```

Códigos de salida:
- `0` = Todas las tasks terminadas, reportes exportados
- `1` = Hay tasks corriendo
- `2` = Nueva task iniciada
- `3` = Mantenimiento en curso

### Exportar Reportes Manualmente
```bash
cd /opt/gvm/Reports
source /opt/gvm/gvm/bin/activate
python3 get-reports-test.py
```

### Limpiar Reportes de la BD
```bash
cd /opt/gvm/Targets_Tasks
source /opt/gvm/gvm/bin/activate
python3 delete-files.py
```

### Ejecutar Mantenimiento
```bash
cd /opt/gvm/Maintenance
source /opt/gvm/gvm/bin/activate

# Modo normal
python3 maintenance.py

# Modo simulación (ver qué haría sin hacer cambios)
python3 maintenance.py --dry-run

# Modo verbose (más detalles)
python3 maintenance.py --verbose
```

## Formato del CSV de Targets

El archivo `Targets_Tasks/openvas.csv` debe tener este formato:

```csv
Titulo;Rango;Desc
Red_Interna_192;192.168.1.0/24;Escaneo de red interna segmento 192
Red_Interna_10;10.0.0.0/24;Escaneo de red interna segmento 10
Servidores_DMZ;172.16.0.0/24;Escaneo de servidores en DMZ
```

**Importante:**
- Delimitador: punto y coma (`;`)
- Sin espacios alrededor del delimitador
- Codificación: UTF-8
- Sin filas vacías

## Estructura Mínima de config.json

```json
{
    "user": "admin",
    "password": "tu_password_openvas",
    "pais": "TU_PAIS",
    "region": "TU_REGION",
    "scope": "INTERNAL",
    "site": "TU_SITE",
    "mailserver": "smtp.tu-empresa.com",
    "smtp_user": "usuario@tu-empresa.com",
    "smtp_pass": "password_smtp",
    "from": "openvas@tu-empresa.com",
    "to": "redteam@tu-empresa.com"
}
```

## Verificación Rápida del Sistema

```bash
# ¿Están corriendo los servicios?
sudo systemctl status gvmd ospd-openvas

# ¿Puedo conectarme a GVM?
sudo -u gvm gvmd --get-scanners

# ¿Está el socket disponible?
ls -la /run/gvmd/gvmd.sock

# ¿Hay mantenimiento activo?
cat /opt/gvm/.maintenance.lock 2>/dev/null && echo "Mantenimiento activo" || echo "Sin mantenimiento"

# Ver logs recientes
tail -f /opt/gvm/taskslog.txt
```

## Troubleshooting Express

### Error: "No se encontró el archivo config.json"
```bash
cp /opt/gvm/Config/config_example.json /opt/gvm/Config/config.json
nano /opt/gvm/Config/config.json
```

### Error: "Connection refused" al conectar a GVM
```bash
sudo systemctl restart gvmd
sudo systemctl restart ospd-openvas
sleep 5
sudo systemctl status gvmd ospd-openvas
```

### Error: "No se pudo obtener el ID de configuración"
```bash
# Verificar que exista la configuración "Full and Fast"
sudo -u gvm gvmd --get-configs | grep -i "full"
```

### Error: Lock de mantenimiento obsoleto
```bash
# Verificar si hay proceso corriendo
ps aux | grep maintenance.py

# Si no hay proceso, eliminar lock
rm /opt/gvm/.maintenance.lock
```

### Tasks no se ejecutan automáticamente
```bash
# Verificar cron
crontab -l | grep run_task.sh

# Verificar permisos
ls -la /opt/gvm/Cron/run_task.sh
chmod +x /opt/gvm/Cron/run_task.sh

# Ejecutar manualmente para ver errores
/opt/gvm/Cron/run_task.sh
```

## Flujo de Trabajo Típico

1. **Lunes**: Crear targets y tasks
   ```bash
   # Editar CSV con nuevos targets
   nano /opt/gvm/Targets_Tasks/openvas.csv
   
   # Crear targets y tasks
   cd /opt/gvm/Targets_Tasks
   source /opt/gvm/gvm/bin/activate
   python3 set-tt.py
   ```

2. **Lunes-Viernes**: Cron ejecuta automáticamente cada 15 min
   - Ejecuta tasks en estado "New"
   - Exporta reportes cuando terminan
   - Sube a SharePoint y Balbix

3. **Primer día del mes**: Mantenimiento automático
   - Actualiza feeds (si >30 días)
   - Limpia reportes antiguos (>90 días)
   - Optimiza base de datos
   - Genera reporte de mantenimiento

## Archivos Importantes

| Archivo | Qué es |
|---------|--------|
| `Config/config.json` | **Configuración principal** (credenciales, emails, etc.) |
| `Targets_Tasks/openvas.csv` | **Lista de targets a escanear** |
| `Targets_Tasks/set-tt.py` | **Script para crear targets/tasks** |
| `Targets_Tasks/run-task.py` | **Script para ejecutar tasks** |
| `Reports/get-reports-test.py` | Script para exportar reportes |
| `Maintenance/maintenance.py` | Script de mantenimiento completo |
| `taskslog.txt` | Log de ejecución de tasks |
| `.maintenance.lock` | Indica mantenimiento en curso |

## Diferencias con Proyecto Original

**Lo más importante:**
1. ✅ Ruta base: `/opt/gvm/` (antes `/home/redteam/gvm`)
2. ✅ Siempre usar `set-tt.py` y `run-task.py` (nunca los scripts sin "-2")
3. ✅ Conexión TLS para targets/tasks (puerto 9390)

Para más detalles, ver `DIFERENCIAS.md`.

## Ayuda

- **README completo**: `README.md`
- **Diferencias con original**: `DIFERENCIAS.md`
- **Registro de cambios**: `CHANGELOG.md`
- **Proyecto original**: https://github.com/cybervaca/automatic-openvas

## Checklist de Instalación

- [ ] Proyecto copiado a `/opt/gvm/`
- [ ] Entorno virtual creado (`/opt/gvm/gvm/`)
- [ ] Dependencias instaladas (`pip3 install -r requirements.txt`)
- [ ] `config.json` creado y configurado
- [ ] `openvas.csv` creado con targets
- [ ] Scripts de Cron con permisos de ejecución (`chmod +x Cron/*.sh`)
- [ ] Servicios OpenVAS corriendo (`gvmd`, `ospd-openvas`)
- [ ] Targets y tasks creados (`set-tt.py`)
- [ ] Crontab configurado (opcional)
- [ ] Primera ejecución manual exitosa (`run-task.py`)

¡Listo para escanear! 🚀

