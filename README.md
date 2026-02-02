# Automatic OpenVAS Installation and Configuration

Este proyecto automatiza la instalación y configuración de OpenVAS, así como la gestión de tareas y objetivos.

## Diferencias con el proyecto original

Este proyecto está adaptado para:
- Utilizar **siempre** los scripts `set-tt.py` y `run-task.py` para comunicarse con OpenVAS
- Usar la ruta `/opt/gvm/` en lugar de `/home/redteam/gvm`
- Optimizado para entornos Docker y contenedores

## Opciones de Instalación

### Opción 1: Despliegue con Docker (Recomendado)

La forma más rápida y sencilla es usar Docker Compose:

```bash
# Clonar el repositorio
cd /opt
git clone <repo-url> gvm
cd gvm

# Iniciar OpenVAS con Docker
docker-compose up -d

# Configurar scripts de automatización en el host
python3 -m venv gvm
source gvm/bin/activate
pip3 install -r requirements.txt

# Configurar
cd Config
cp config_example.json config.json
# Editar config.json con tus valores
```

**Ver documentación completa**: [DOCKER.md](DOCKER.md)

**Características de resiliencia incluidas:**
- ✅ Healthcheck automático que verifica procesos críticos y disponibilidad web
- ✅ Auto-recuperación mediante contenedor autoheal que reinicia servicios caídos
- ✅ Límites de recursos (memoria y CPU) para prevenir OOM y consumo excesivo
- ✅ Protección OOM para reducir la probabilidad de que el kernel mate el proceso

### Opción 2: Instalación Nativa

## Instalación Nativa

```bash
# Clonar o copiar el proyecto a la ubicación deseada:
cd /opt
git clone <repo-url> gvm

# O si ya tienes los archivos:
# cp -r openvas-docker-automatic /opt/gvm

# Ingresar al directorio y configurar el entorno virtual:
cd gvm
python3 -m venv gvm
source gvm/bin/activate

# Si no existe python3.10-venv, instalar según la versión:
sudo apt install python3.10-venv

# Instalar dependencias:
pip3 install -r requirements.txt
```

### Instalación de OpenVAS (si es necesario)

Si necesitas instalar OpenVAS desde cero:

```bash
# Ingresar al directorio "install" y ejecutar los scripts de instalacion:
cd install
python3 get-versionesonline.py #para obtener las ultimas versiones
chmod +x pre-install.sh #para actualizar cmake y obtener la ruta de pkgconfig
./pre-install.sh
chmod +x install.sh
./install.sh
```

Si después de la instalación, el servicio gsad.service da error, modificar el fichero
`/etc/systemd/system/multi-user.target.wants/gsad.service`
Y borrar de ExecStart:
```
-f --drop-privileges=gvm
```
Y ejecutamos:
```
sudo systemctl daemon-reload
sudo service gsad restart
```

#### Para cambiar la contraseña de gvmd:
```
gvmd --user=admin --new-password=
```

## Configuración

### Config

En la carpeta Config, copiar el fichero `config_example.json` a `config.json`:

```bash
cd /opt/gvm/Config
cp config_example.json config.json
```

Modificar los valores con los correspondientes de la ubicación.

### Cron

En la carpeta Cron, los scripts ya tienen permisos de ejecución. Para configurar cron:

```bash
# Editar crontab
crontab -e

# Agregar líneas como estas (ajustar según tus necesidades):
# Ejecutar tareas cada 15 minutos
*/15 * * * * /opt/gvm/Cron/run_task.sh
```

### Configuración de Targets y Tasks

En `Targets_Tasks` existe una plantilla CSV (`openvas.csv`) para la importación de los targets y su correspondiente task.

El formato del CSV debe ser (delimitado por punto y coma `;`):
```
Titulo;Rango;Desc
Red_Interna;192.168.1.0/24;Escaneo de red interna
```

Una vez rellenado el CSV, ejecutar:

```bash
cd /opt/gvm/Targets_Tasks
python3 set-tt.py
```

Este script:
- Lee el archivo `openvas.csv`
- Crea los targets en OpenVAS
- Crea automáticamente las tasks asociadas
- Obtiene dinámicamente el ID de la configuración "Full and Fast"
- Usa conexión TLS (puerto 9390)

## Scripts Principales

### Targets_Tasks/

#### `set-tt.py`
Script principal para crear targets y tasks desde un CSV. Características:
- Lee CSV con formato: `Titulo;Rango;Desc`
- Conecta vía TLS a GVM (puerto 9390)
- Obtiene dinámicamente el ID de configuración "Full and Fast"
- Agrupa targets si tienen más de 9 rangos
- Genera log detallado en `log.txt`

#### `run-task.py`
Script para gestionar la ejecución de tasks. Códigos de retorno:
- `0`: Todas las tasks finalizadas, exporta reportes
- `1`: Hay tasks corriendo aún
- `2`: Arrancó una nueva task
- `3`: Mantenimiento en curso, no se pueden ejecutar tareas

Características:
- Verifica lock de mantenimiento antes de ejecutar
- Conecta vía TLS a GVM (puerto 9390)
- Maneja estados: Running, Requested, Queued, New
- Llama automáticamente a `get-reports-test.py` cuando terminan todas las tasks

#### `delete-files.py`
Limpia reportes de la base de datos y archivos temporales.

### Reports/

#### `get-reports-test.py`
Exporta reportes de OpenVAS en formato CSV y genera archivos consolidados.

Funcionalidades:
- Conecta vía Unix Socket (`/run/gvmd/gvmd.sock`)
- Exporta reportes con filtro: `apply_overrides=1 min_qod=70 severity>0`
- Genera CSV consolidado con timestamp
- Extrae IPs excluidas de targets
- Añade información de sistemas operativos
- Separa CVEs y Misconfigs
- Sube reportes a SharePoint
- Envía reportes a Balbix/Valbix

#### `subida_share.py`
Sube archivos a SharePoint usando Microsoft Graph API.

Uso:
```bash
python3 subida_share.py -f archivo.csv -p PAIS -a Openvas_Interno [-o]
```

#### `upload-reports.py`
Sube reportes a AWS S3 (Balbix/Valbix).

### Cron/

Scripts para automatización:

- `run_task.sh` - Wrapper para ejecutar `run-task.py`
- `actualiza_gvm.sh` - Actualiza feeds de GVM manualmente
- `update-script.sh` - Actualiza el repositorio desde GitHub (git pull)
- `procesos.sh` - Monitor de procesos (útil para debugging)

## Flujo de Trabajo

### Ciclo Completo de Escaneo

1. **Ejecución de run-task.py** (via cron cada 15 min)
   - Verifica lock de mantenimiento
   - Si hay mantenimiento activo: sale con código 3
   - Verifica tasks Running/Queued/Requested: sale con código 1
   - Busca tasks en estado "New" y las ejecuta: sale con código 2
   - Si todas las tasks terminaron: exporta reportes y sale con código 0

2. **Exportación de Reportes** (cuando todas las tasks terminan)
   - `get-reports-test.py` exporta reportes CSV
   - `subida_share.py` sube a SharePoint
   - Separa CVEs y Misconfigs
   - `upload-reports.py` sube a Balbix/Valbix
   - `delete-files.py` limpia reportes de la BD

3. **Mantenimiento** (mensual, primer día del mes a las 2:00 AM)
   - Crea lock de mantenimiento
   - Verifica servicios
   - Actualiza feeds (solo si >30 días)
   - Limpia reportes y archivos antiguos
   - Optimiza base de datos
   - Genera reporte de mantenimiento
   - Elimina lock

4. **Reinicio del Ciclo**
   - Siguiente ejecución de `run-task.py`
   - Si hay tasks "New", las ejecuta
   - Repite el ciclo

## Características Importantes

### Uso Exclusivo de set-tt.py y run-task.py

Este proyecto utiliza **únicamente** las versiones "-2" de los scripts principales:

- **set-tt.py**: Conexión TLS (puerto 9390), obtención dinámica de configuración
- **run-task.py**: Conexión TLS, verificación de lock de mantenimiento

Los scripts originales `set-TT.py` y `run-task.py` **NO se utilizan**.

### Ruta Base: /opt/gvm/

Todas las rutas están configuradas para usar `/opt/gvm/` como directorio base, no `/home/redteam/gvm`.

### Conexiones a OpenVAS

- **Targets/Tasks**: Conexión TLS a `127.0.0.1:9390`
- **Reports**: Unix Socket `/run/gvmd/gvmd.sock`
- **Maintenance**: Unix Socket `/run/gvmd/gvmd.sock`

### Sistema de Lock de Mantenimiento

El archivo lock `/opt/gvm/.maintenance.lock` previene que se ejecuten nuevas tasks durante el mantenimiento:

```json
{
  "timestamp": "2026-01-28T10:00:00",
  "pid": 12345,
  "status": "running"
}
```

## Troubleshooting

### Error: No se puede conectar a GVM

Verificar que los servicios estén corriendo:
```bash
sudo systemctl status gvmd
sudo systemctl status ospd-openvas
```

### Error: Lock de mantenimiento obsoleto

Si el proceso de mantenimiento falló, eliminar manualmente:
```bash
rm /opt/gvm/.maintenance.lock
```

### Error: Feeds en "Update in progress..." por mucho tiempo

El script de mantenimiento tiene timeout de 8 horas. Si persiste:
```bash
# Verificar procesos activos
ps aux | grep feed-sync
ps aux | grep nvt-sync

# Si no hay procesos activos, reiniciar servicios
sudo systemctl restart gvmd
sudo systemctl restart ospd-openvas
```

### Error: CSV no se procesa correctamente

Verificar formato del CSV:
- Delimitador: punto y coma (`;`)
- Columnas requeridas: `Titulo`, `Rango`, `Desc`
- Sin filas vacías
- Codificación UTF-8

## Logs

Los logs se generan en las siguientes ubicaciones:

- `/opt/gvm/taskslog.txt` - Log de ejecución de tasks
- `/opt/gvm/tasksend.txt` - Información de tasks finalizadas
- `/opt/gvm/logbalbix.txt` - Log de subidas a Balbix
- `/opt/gvm/Targets_Tasks/log.txt` - Log de creación de targets/tasks

## Estructura de Directorios

```
/opt/gvm/
├── Config/
│   ├── config.json (crear desde config_example.json)
│   └── config_example.json
├── Cron/
│   ├── actualiza_gvm.sh
│   ├── cron-update.sh
│   ├── procesos.sh
│   ├── run_task.sh
│   └── update-script.sh
├── Reports/
│   ├── exports/
│   │   └── vulns_host/
│   ├── get-reports-test.py
│   ├── subida_share.py
│   └── upload-reports.py
├── Targets_Tasks/
│   ├── delete-files.py
│   ├── openvas.csv (crear este archivo)
│   ├── run-task.py
│   └── set-tt.py
├── logs/
│   └── maintenance/
├── gvm/ (entorno virtual)
└── requirements.txt
```

## Créditos

Basado en [automatic-openvas](https://github.com/cybervaca/automatic-openvas) con adaptaciones para:
- Uso exclusivo de scripts -2 (TLS connection)
- Cambio de ruta base a `/opt/gvm/`
- Optimizaciones para entornos contenedorizados

## Licencia

Ver archivo LICENSE en el proyecto original.
