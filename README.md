# openvas-docker-automatic

Sistema automatizado para gestión de OpenVAS/GVM con Docker, incluyendo creación de targets y tasks, ejecución de escaneos, generación de reportes y monitoreo proactivo.

## Características Principales

- 🎯 **Gestión de Targets y Tasks**: Creación automática desde CSV
- 🔄 **Ejecución Automática**: Gestión de escaneos programados (incluye modo **`--mensual`**: un solo ciclo de informe por mes comprobando SharePoint)
- 📊 **Generación de Reportes**: Múltiples formatos y exportación
- 📤 **Integración Cloud**: Subida automática a SharePoint y Balbix/Valbix
- 🔍 **Monitoreo Proactivo**: Servicio de monitoreo con alertas por Telegram
- 🐳 **Docker Ready**: Despliegue simplificado con docker-compose

## Estructura del Proyecto

```
openvas-docker-automatic/
├── Config/              # Configuración (config.json)
├── Monitor/             # Servicio de monitoreo con alertas Telegram
├── Reports/             # Scripts de generación y exportación de reportes
├── Targets_Tasks/       # Scripts de gestión de targets y tasks
├── Cron/                # Scripts de automatización y cron
├── Update/              # Scripts de actualización
└── docker-compose.yml   # Configuración Docker
```

## Instalación Rápida

### Con Docker (Recomendado)

```bash
git clone https://github.com/cybervaca/openvas-docker-automatic.git
cd openvas-docker-automatic
docker-compose up -d
```

Ver [DOCKER.md](DOCKER.md) para más detalles.

### Instalación Nativa

1. Clonar el repositorio
2. Instalar dependencias: `pip install -r requirements.txt`
3. Configurar `/opt/gvm/Config/config.json`
4. Configurar scripts de cron según necesidades

## Ejecución programada y modo mensual

El script [`Cron/run_task.sh`](Cron/run_task.sh) activa el venv y ejecuta [`Targets_Tasks/run-task.py`](Targets_Tasks/run-task.py). Los argumentos se **reenvían tal cual** (`"$@"`).

- **Modo normal:** `./run_task.sh` — mismo comportamiento que antes.
- **Modo mensual (`--mensual`):** `./run_task.sh --mensual` — antes de tocar GVM se llama a `Reports/subida_share.py --check-mensual`. Si en SharePoint ya existe un informe **.csv** o **.xlsx** del **mes actual** (prefijo `YYYY_MM_` en el nombre o fecha de modificación en Graph, según implementación), **no** se inician tareas nuevas ni se ejecuta la generación de reportes (`get-reports-test.py`); el proceso termina con código **4**. Si la comprobación falla (red, credenciales, etc., código **2**), se deja constancia en el log y **se sigue** el flujo habitual (fail-open).

Las carpetas hasta el informe (`General/Subidas/.../Openvas_Interno/…`) se resuelven contra Microsoft Graph **sin distinguir mayúsculas** (`Mexico` y `MEXICO` encuentran la misma carpeta). Las subidas con `subida_share.py -f … -p … -a …` usan la misma lógica y, si falta algún segmento de la ruta (p. ej. la subcarpeta `{site}` bajo `Targets_Export` al exportar targets), **lo crean** antes de subir el archivo. La comprobación **`--check-mensual`** no crea carpetas: solo lista lo que ya existe.

**Dependencias SharePoint (`requests`, `msal`):** tienen que estar instaladas en el **mismo** entorno desde el que se ejecuta `./run_task.sh` (`source /opt/gvm/gvm`). Si falta alguna, `./run_task.sh --mensual` verá código **2** y continuará la orquestación (fail-open).

Requisitos: la misma configuración Graph/SharePoint que para las subidas (`/opt/gvm/Config/config.json`: `pais`, `site`, `tenant_id`, `client_id`, `client_secret`).

## Monitoreo

El proyecto incluye un servicio de monitoreo completo que verifica:
- Estado del contenedor Docker
- Servicio Docker daemon
- Servicios GVM (gvmd, gsad)
- Conexión TLS a GVM
- **Actualización de feeds de vulnerabilidades** (NVTs, SCAP, CERT, GVMD_DATA)
- Actualizaciones de imagen disponibles

**Alertas por Telegram**: Configura tu bot y recibe notificaciones proactivas cuando hay problemas o feeds desactualizados (>30 días).

Ver [Monitor/README.md](Monitor/README.md) para configuración completa.

## Documentación

- [DOCKER.md](DOCKER.md) - Guía de instalación y uso con Docker
- [INICIO_RAPIDO.md](INICIO_RAPIDO.md) - Guía rápida de inicio
- [DIFERENCIAS.md](DIFERENCIAS.md) - Diferencias con el proyecto original
- [DEPENDENCIAS.md](DEPENDENCIAS.md) - Dependencias del proyecto
- [Monitor/README.md](Monitor/README.md) - Documentación del servicio de monitoreo
- [Reports/README.md](Reports/README.md) - Documentación de scripts de reportes

## Licencia

Este proyecto es parte del sistema de automatización de OpenVAS Docker.
