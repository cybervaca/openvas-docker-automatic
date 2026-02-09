# openvas-docker-automatic

Sistema automatizado para gestión de OpenVAS/GVM con Docker, incluyendo creación de targets y tasks, ejecución de escaneos, generación de reportes y monitoreo proactivo.

## Características Principales

- 🎯 **Gestión de Targets y Tasks**: Creación automática desde CSV
- 🔄 **Ejecución Automática**: Gestión de escaneos programados
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

## Monitoreo

El proyecto incluye un servicio de monitoreo completo que verifica:
- Estado del contenedor Docker
- Servicio Docker daemon
- Servicios GVM (gvmd, gsad)
- Conexión TLS a GVM
- Actualizaciones de imagen disponibles

**Alertas por Telegram**: Configura tu bot y recibe notificaciones proactivas.

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
