# Changelog

## [2.5.17] - 2026-07-23

### Mejorado
- **`gvm_connect.py`**: si no hay socket en el host, descubre el de gvmd vía Docker
  (bind mount de `/run/gvmd` o `/proc/<pid>/root/run/gvmd/gvmd.sock`).
  Mensaje de error con la línea exacta de volumen a añadir al compose.

## [2.5.16] - 2026-07-23

### Corregido
- **Actualización en flota**: `git pull` fallaba en Git reciente con ramas divergentes
  (`Necesita especificar cómo reconciliar las ramas divergentes`).
- **`Update/update-script.py`**: pasa a `git fetch` + `git reset --hard origin/main`
  (determinista; no usa `git pull`). `Config/config.json` se conserva (está en `.gitignore`).
- **`Update/sync-from-github.sh`**: mismo flujo; usable por `curl | bash` desde raw GitHub
  cuando el repo local aún no tiene el script nuevo.

### Documentación
- `Update/README.md`: one-liner de emergencia y cron.

## [2.5.15] - 2026-07-23

### Añadido
- **`gvm_connect.py`**: conexión GMP dual **TLS (9390) + Unix socket**, modo por defecto **`auto`**.
  - Prueba primero TLS (no rompe hosts que ya hablan por 9390).
  - Si el puerto está cerrado o TLS falla, prueba sockets (`/opt/gvm/run/gvmd/gvmd.sock`, `/run/gvmd/gvmd.sock`, …).
  - Config opcional en `config.json`: `gvm_connection` (`auto`|`tls`|`unix`), `gvm_host`, `gvm_port`, `gvm_socket`.
- Scripts de Targets/Reports/Monitor usan el helper compartido.
- **Monitor**: el check de gvmd acepta TCP **o** socket Unix (sin falso positivo solo por falta de 9390).
- **`docker-compose-example.yml`**: volumen `/opt/gvm/run/gvmd:/run/gvmd` para exponer el socket al host.

### Documentación
- `README.md`, `Config/config_example.json`: claves de conexión GVM.

## [2.5.14] - 2026-07-23

### Añadido
- **`Targets_Tasks/run_task_name.py`**: arranca una tarea GVM por **nombre exacto** (sin distinguir mayúsculas). Arranca aunque otras tareas estén en curso; si la pedida ya está `Running`/`Requested`/`Queued` no relanza (exit 0). Respeta el lock de mantenimiento. Uso: `python3 run_task_name.py "Mi Tarea"`.

### Documentación
- `README.md`: uso de `run_task_name.py`.

## [2.5.13] - 2026-06-01

### Añadido
- **`Reports/subida_share.py`**: en subidas (`-f`, `-p`, `-a`) se **crean automáticamente** las subcarpetas faltantes bajo `Documents` vía Microsoft Graph (p. ej. `General/Subidas/{pais}/Targets_Export/{site}` para `export-target.py`). Log `[INFO] Carpeta SharePoint creada: …` por cada nivel nuevo.

### Sin cambio de comportamiento
- **`--check-mensual`**: sigue solo resolviendo rutas existentes; no crea carpetas al comprobar informes del mes.

### Documentación
- `README.md`: nota sobre creación automática de carpetas en subidas SharePoint.

## [2.5.12] - 2026-05-22

### Cambiado
- **`Reports/subida_share.py`**: comprobación mensual (`--check-mensual`) y **subidas** resuelven la ruta bajo **`Documents`** nivel a nivel, comparando nombres de carpeta **sin distinguir mayúsculas**, alineado con SharePoint Online. La biblioteca **`Documents`** se localiza igual sin caso. Las subidas usan PUT por **`id`** de carpeta padre tras resolver la jerarquía.
### Mejorado
- Si falta **`requests`** o **`msal`**, `subida_share.py` imprime mensaje instructivo con **salida `2`** (fail-open desde `run-task --mensual`), no sólo traceback con código inconsistente.

### Ops
- **`Targets_Tasks/run-task.py`**: el chequeo mensual ejecuta **`subida_share`** con **`sys.executable`** (mismo Python/venv que el padre cuando se usa `./run_task.sh`).

### Documentación
- `README.md`: nota sobre rutas SharePoint insensitive y dependencias pip.

## [2.5.11] - 2026-05-18

### Añadido
- **Modo mensual (SharePoint)** — `Targets_Tasks/run-task.py`, `Reports/subida_share.py`, `Cron/run_task.sh`
  - Flag opcional **`--mensual`** en `run-task.py`: ejecuta `subida_share.py --check-mensual` y, si ya hay **informe CSV/XLSX del mes calendario** en `General/Subidas/{pais}/Openvas_Interno/{site}` (misma convención que la subida), **no** arranca tareas nuevas ni llama a `get-reports-test.py` (**código de salida 4**).
  - **`subida_share.py --check-mensual`**: listado por Microsoft Graph con paginación; salida **0** = hay informe del mes, **1** = no hay, **2** = error (en `run-task` se registra advertencia y se **continúa** el flujo, fail-open).
  - **`run_task.sh`** reenvía argumentos al Python (`"$@"`), p. ej. `./run_task.sh --mensual`.

### Documentación
- `README.md`: uso de `--mensual` y cron.

## [2.5.10] - 2026-05-11

### Cambiado
- **`exclusion.csv` y SharePoint (defensa en profundidad)** - `Reports/subida_share.py` y `Reports/get-reports-test.py`
  - `subida_share.py`: si el archivo pedido es `exclusion.csv` (nombre, sin distinguir mayúsculas) y **no existe** o **está vacío**, termina con **código 0** y `[INFO]` en consola (no hay `[ERROR]` ni fallo para cron/monitores que miren el exit code).
  - `get-reports-test.py`: **nunca** envía Telegram cuando la fase o el nombre de archivo es `exclusion.csv`, aunque falle Graph/API o quedara `notify_on_failure=True`; solo `[WARNING]` en consola. Los **reportes principales CSV/XLSX** siguen con alerta Telegram si fallan.
  - Sigue existiendo comprobación antes de lanzar `subida_share.py` cuando el CSV no está o está vacío (menos llamadas innecesarias).

### Operaciones
- Los servidores solo reciben el arreglo si el commit está en el remoto (**`git push`** desde el desarrollo) y en el host se ejecuta **`git pull`** en `/opt/gvm` (o se reconstruye la imagen si los scripts van en Docker).

### Documentación
- `Monitor/README.md`, `Reports/README.md`: alineados con el comportamiento anterior.

## [2.5.9] - 2026-05-08

### Cambiado
- **`exclusion.csv` y SharePoint** - `Reports/get-reports-test.py`
  - No se intenta subir a SharePoint si `exclusion.csv` no existe o está vacío (caso habitual sin exclusiones)
  - Si la subida de `exclusion.csv` falla, solo se registra `[WARNING]` en consola; **no** se envía alerta Telegram (los reportes CSV/XLSX siguen alertando igual). *Ampliado en 2.5.10 con `subida_share.py` y bloqueo explícito de Telegram.*

### Documentación
- `Monitor/README.md`: aclarado el alcance de las alertas SharePoint/Telegram

## [2.5.8] - 2026-05-08

### Mejorado
- **Exportación paralela de reportes** - `Reports/get-reports-test.py` ahora exporta reports con 5 threads
  - Cada thread usa su propia conexión TLS/GMP para evitar compartir estado
  - Exporta solo el último reporte de cada task finalizada (`last_report`)
  - Evita recorrer todos los reports históricos con `get_reports(rows=1000)`
  - Si un reporte falla, se omite y el resto continúa
  - Se omiten CSV ausentes, vacíos o ilegibles durante la unificación

## [2.5.7] - 2026-05-08

### Añadido
- **Alertas Telegram para fallos de SharePoint** - `Reports/get-reports-test.py` ahora avisa si falla una subida
  - Detecta fallos de `subida_share.py` comprobando el `returncode`
  - Envía Telegram con país, site, región, scope, fase, archivo, destino, `stdout` y `stderr`
  - Cubre la subida de los **reportes principales CSV/XLSX**; **`exclusion.csv` quedó fuera de Telegram** en versiones posteriores (2.5.9+), al ser opcional en muchas instalaciones
  - Reutiliza `monitoring.telegram` de `/opt/gvm/Config/config.json`
  - Soporta el túnel SOCKS opcional de `/opt/gvm/Monitor/config.json`

### Documentación
- `Monitor/README.md` actualizado con la nueva alerta por fallo de subida a SharePoint

## [2.5.6] - 2026-05-08

### Corregido
- **Timeout descargando reportes grandes** - Aumentado el timeout TLS de GVM a 15 minutos en los scripts de reportes
  - Evita `TimeoutError: The read operation timed out` durante `gmp.get_report()`
  - Afecta a `Reports/get-reports-test.py`, `Reports/get-reports-os.py`, `Reports/get-reports-unico.py` y `Reports/get-reports.py`
  - Mantiene el flujo de descarga por GMP, pero da más margen a reportes CSV grandes con `details=True`

### Documentación
- `Monitor/README.md` actualizado con una nota de troubleshooting para timeouts descargando reportes

## [2.5.5] - 2026-05-07

### Añadido
- **Importación de exclusiones en targets** - `Targets_Tasks/set-tt.py` ahora aplica exclusiones al crear targets
  - Soporta columna opcional `Exclusiones` en `openvas.csv`
  - Usa `/opt/gvm/Reports/exclusion.csv` como fallback si no hay exclusiones en el CSV de entrada
  - Aplica exclusiones con `exclude_hosts` durante la creación del target
  - Registra las exclusiones aplicadas en `log.txt`

### Mejorado
- **Exportación de targets compatible con importación** - `Targets_Tasks/export-target.py` ahora exporta `Titulo;Rango;Desc;Exclusiones`
  - Extrae exclusiones existentes desde los targets de OpenVAS
  - Genera CSV reimportable directamente por `set-tt.py`
- **Ejemplo CSV actualizado** - `Targets_Tasks/openvas.csv.example` documenta la columna `Exclusiones`

### Documentación
- `Monitor/README.md` actualizado para aclarar el auto-update de feeds con `actualiza_gvm.sh`

## [2.5.4] - 2026-01-30

### Añadido
- **Verificación de Feeds en Servicio de Monitoreo** - Detección automática de feeds desactualizados
  - Nueva función `verificar_feeds()` que obtiene fecha de actualización de feeds usando GMP
  - Verifica NVTs, SCAP, CERT y GVMD_DATA
  - Calcula días desde última actualización
  - Alerta por Telegram si algún feed tiene más de 30 días sin actualizar (configurable)
  - Muestra información detallada de feeds desactualizados en las alertas
  - Integrado en el servicio de monitoreo existente

### Mejorado
- **Servicio de Monitoreo** - Verificación de feeds de vulnerabilidades
  - Añadida verificación de feeds después de verificar conexión GVM
  - Mensajes de alerta incluyen lista detallada de feeds desactualizados
  - Estado de todos los feeds visible en las alertas
  - Recomendación automática de ejecutar `actualiza_gvm.sh` cuando hay feeds desactualizados

### Cambios Técnicos
- `Monitor/monitor.py`:
  - Nueva función `verificar_feeds(config, feed_stale_days=30)` que usa GMP `get_info()`
  - Integrada en `ejecutar_verificaciones()` solo si GVM está conectado
  - Actualizado `formatear_mensaje_alerta_completo()` para incluir información de feeds
  - Añadida lógica de alertas para feeds en `enviar_alertas()`
  - Añadido emoji 📦 y nombre "Feeds de Vulnerabilidades" en mensajes
- `Config/config_example.json`:
  - Añadida opción `alert_on_feeds_stale: true` en sección `monitoring`
  - Añadida opción `feed_stale_days: 30` para configurar umbral de días
- `Monitor/README.md`:
  - Documentada nueva verificación de feeds
  - Añadido ejemplo de mensaje de alerta para feeds desactualizados
  - Actualizada lista de características y verificaciones

## [2.5.3] - 2026-02-19

### Corregido
- **Conexión GVM en get-reports-test.py** - Corregido tipo de conexión
  - Cambiado de `UnixSocketConnection` a `TLSConnection` para compatibilidad con Docker
  - Actualizado `connect_gvm()` para usar puerto TLS 9390 en lugar de socket Unix
  - Corregidas todas las rutas hardcodeadas de `/home/redteam/gvm/` a `/opt/gvm/`
  - El script ahora puede conectarse correctamente a GVM y generar reportes

### Cambios Técnicos
- `Reports/get-reports-test.py`:
  - Import cambiado de `UnixSocketConnection` a `TLSConnection`
  - Función `connect_gvm()` actualizada para usar `TLSConnection(hostname="127.0.0.1", port=9390)`
  - Actualizadas 12 rutas de `/home/redteam/gvm/` a `/opt/gvm/`:
    - `REPORTS_DIR`, `config.json`, `exports`, `subida_share.py`, `upload-reports.py`, `hosts.csv`
  - Consistencia con otros scripts del proyecto (`run-task.py`, `get-reports.py`, etc.)

## [2.5.2] - 2026-02-19

### Eliminado
- **Servicio autoheal** - Removido `willfarrell/autoheal` del docker-compose
  - El servicio de monitoreo OpenVAS (`Monitor/`) ahora reemplaza la funcionalidad de autoheal
  - Eliminada label `autoheal=true` del servicio openvas
  - El servicio de monitoreo proporciona funcionalidad más completa con alertas por Telegram

### Mejorado
- **Conexión a PostgreSQL** - Exposición del puerto PostgreSQL en docker-compose
  - Puerto 5432 expuesto en localhost (127.0.0.1:5432) en `docker-compose-example.yml`
  - Scripts de reportes actualizados para usar conexión directa primero
  - Orden de intento de conexión optimizado: conexión directa → docker exec → conexión local
  - Evita problemas al subir reportes cuando `docker exec` falla

### Cambios Técnicos
- `docker-compose-example.yml`:
  - Añadido puerto `127.0.0.1:5432:5432` para PostgreSQL
  - Eliminado servicio `autoheal` (reemplazado por servicio de monitoreo)
  - Eliminada label `autoheal=true` del servicio openvas
- `Reports/get-reports-os.py` - Función `get_hosts()` actualizada con conexión directa primero
- `Reports/get-reports-unico.py` - Función `get_hosts()` actualizada con conexión directa primero
- `Reports/get-reports-test.py` - Función `get_hosts()` actualizada para seguir el mismo patrón
  - Uso de `PGPASSWORD` para evitar prompts de contraseña
  - Manejo mejorado de errores con múltiples fallbacks

## [2.5.1] - 2026-02-09

### Mejorado
- **Servicio de Monitoreo OpenVAS** - Seguridad mejorada
  - Cambio de usuario de ejecución de `root` a `redteam` (usuario no-root)
  - Script de instalación actualizado para crear usuario `redteam` si no existe
  - Configuración automática de permisos y grupo docker
  - Soporte para reinstalación automática del servicio
  - Documentación actualizada con el nuevo usuario

### Cambios Técnicos
- `Monitor/openvas-monitor.service` - Usuario cambiado a `redteam`
- `Monitor/install-monitor.sh` - Mejoras en instalación y reinstalación:
  - Creación automática del usuario si no existe
  - Detección y reinstalación automática si el servicio ya está instalado
  - Configuración mejorada de permisos para usuario no-root
- `Monitor/README.md` - Documentación actualizada con usuario `redteam`

## [2.5.0] - 2026-02-09

### Añadido
- **Servicio de Monitoreo OpenVAS** (`Monitor/`)
  - Script principal `monitor.py` con verificaciones completas:
    - Estado del contenedor Docker
    - Servicio Docker daemon
    - Puertos GVM (9390, 9392)
    - Conexión TLS a GVM
    - Detección de actualizaciones de imagen
  - Alertas por Telegram con formato estructurado y emojis
  - Logs estructurados en JSON (`/opt/gvm/logs/monitoring/`)
  - Sistema de cooldown para evitar spam de alertas
  - Ejecución automática cada 5 minutos mediante systemd timer
  - Script helper `get_channel_id.py` para obtener chat_id de canales y grupos
  - Documentación completa en `Monitor/README.md`
  - Script de instalación `install-monitor.sh`

### Mejorado
- `Config/config_example.json` - Añadida sección `monitoring` con configuración completa
  - Opciones para habilitar/deshabilitar tipos de alertas
  - Configuración de Telegram (bot_token, chat_id)
  - Sistema de cooldown configurable
- `Reports/get-reports.py`, `get-reports-os.py`, `get-reports-unico.py`
  - Migración de Unix Socket a TLS Connection (puerto 9390)
  - Actualización de rutas a `/opt/gvm/`
  - Supresión de warnings de deprecación
  - Corrección de path duplicado en mensajes
  - Soporte para PostgreSQL dentro de contenedor Docker

### Corregido
- Path duplicado en mensajes de reportes: `/opt/gvm/Reports/exports/exports/` → `/opt/gvm/Reports/exports/`
- Warnings de deprecación suprimidos en scripts de reportes
- Conexión a PostgreSQL desde scripts ejecutados fuera del contenedor Docker

### Documentación
- `README.md` - Actualizado con información del servicio de monitoreo
- `Monitor/README.md` - Documentación completa del servicio
- `Reports/README.md` - Documentación actualizada con nuevas rutas y TLS

## [2.4.0] - 2026-01-30

### Añadido
- `Targets_Tasks/set-tt.py` - Detección y resolución automática de títulos duplicados
  - Nueva función `resolve_duplicate_titles()` que parsea el CSV antes de crear targets
  - Agrega sufijos numéricos automáticamente (_2, _3, etc.) a títulos duplicados
  - Actualiza también la descripción para reflejar el nuevo título
  - Muestra mensajes informativos de los cambios realizados
  - Previene errores al intentar crear targets con el mismo nombre

### Mejorado
- `Targets_Tasks/set-tt.py` - Mejor manejo de títulos duplicados en openvas.csv
  - Ejemplo: `PR_Servidores` duplicado se convierte en `PR_Servidores_2`, `PR_Servidores_3`, etc.
  - El parseo se ejecuta automáticamente al cargar el CSV
  - No requiere intervención manual del usuario

## [2.3.0] - 2026-01-29

### Simplificado
- `Update/update-script.py` - Simplificado a un git pull básico
  - Eliminada lógica compleja de backup/restore de targets
  - Eliminada descarga de export-target.py
  - Eliminado git pull forzado
  - Eliminada verificación de versiones
  - Ahora solo hace `git fetch` y `git pull origin main`
  - Más simple, predecible y seguro

### Actualizado
- `Update/README.md` - Documentación actualizada para reflejar la simplificación
- `README.md` - Descripción de scripts Cron actualizada

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

