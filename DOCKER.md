# Despliegue con Docker Compose

Este proyecto incluye configuración Docker Compose para ejecutar OpenVAS en un contenedor.

## Archivo docker-compose.yml

El archivo `docker-compose.yml` está configurado para desplegar OpenVAS usando la imagen oficial de [immauss/openvas](https://hub.docker.com/r/immauss/openvas).

### Configuración

```yaml
version: '3.9'

services:
  openvas:
    image: immauss/openvas:latest
    container_name: openvas
    restart: unless-stopped
    ports:
      - "127.0.0.1:9392:9392"   # Web UI solo localhost
      - "127.0.0.1:9390:9390"   # Puerto de comunicación GMP/TLS
    volumes:
      - openvas-data:/data
      - /opt/gvm:/opt/gvm
    environment:
      - PASSWORD=admin
      - RELAYHOST=smtp.example.com
      - SMTPPORT=25

volumes:
  openvas-data:
```

### Características

#### Puertos Expuestos

- **9392**: Interfaz web de Greenbone Security Assistant (GSAD)
  - Expuesto solo en `localhost` por seguridad
  - Acceso: https://127.0.0.1:9392
  
- **9390**: Puerto de comunicación GMP (Greenbone Management Protocol) sobre TLS
  - Usado por los scripts Python para comunicarse con OpenVAS
  - Expuesto solo en `localhost` por seguridad

#### Volúmenes

1. **openvas-data**: Volumen Docker para persistencia de datos
   - Base de datos PostgreSQL
   - Configuración de OpenVAS
   - Feeds de vulnerabilidades (NVTs, CVEs, etc.)

2. **/opt/gvm**: Bind mount para scripts de automatización
   - Los scripts de este repositorio deben estar en `/opt/gvm` del host
   - Se comparten con el contenedor para ejecución

#### Variables de Entorno

- **PASSWORD**: Contraseña del usuario `admin` de OpenVAS (por defecto: `admin`)
- **RELAYHOST**: Servidor SMTP para envío de notificaciones por correo
- **SMTPPORT**: Puerto del servidor SMTP (por defecto: `25`)

## Uso

### Iniciar el contenedor

```bash
# Desde el directorio del proyecto
docker-compose up -d
```

### Ver logs

```bash
docker-compose logs -f
```

### Detener el contenedor

```bash
docker-compose down
```

### Detener y eliminar volúmenes (CUIDADO: borra todos los datos)

```bash
docker-compose down -v
```

## Primer Inicio

El primer inicio puede tardar **varios minutos** (15-30 min) ya que OpenVAS debe:

1. Inicializar la base de datos PostgreSQL
2. Descargar feeds de vulnerabilidades (NVTs)
3. Compilar las firmas de escaneo
4. Iniciar todos los servicios

### Verificar el estado de inicialización

```bash
# Ver logs en tiempo real
docker-compose logs -f openvas

# Verificar que todos los servicios estén corriendo
docker exec -it openvas ps aux | grep -E "gvmd|ospd|gsad|postgres|redis"
```

### Acceder a la interfaz web

Una vez iniciado, acceder a:

```
https://127.0.0.1:9392
```

**Credenciales por defecto:**
- Usuario: `admin`
- Contraseña: `admin` (o la especificada en `PASSWORD`)

⚠️ **Importante**: El navegador mostrará advertencia de certificado autofirmado. Es normal, aceptar e ignorar.

## Integración con los Scripts de Automatización

### Requisitos previos

1. Los scripts deben estar en `/opt/gvm/` del host
2. Entorno virtual Python configurado
3. Archivo `config.json` configurado

### Configuración en el host

```bash
# Clonar el repositorio en /opt/gvm
cd /opt
git clone <repo-url> gvm

# Crear entorno virtual
cd gvm
python3 -m venv gvm
source gvm/bin/activate

# Instalar dependencias
pip3 install -r requirements.txt

# Configurar
cd Config
cp config_example.json config.json
# Editar config.json con tus valores
```

### Ejecutar scripts desde el host

Los scripts se ejecutan **desde el host**, no dentro del contenedor:

```bash
cd /opt/gvm
source gvm/bin/activate

# Crear targets y tasks
cd Targets_Tasks
python3 set-tt.py

# Ejecutar tareas
python3 run-task.py
```

Los scripts se conectan al contenedor usando:
- **TLS**: `127.0.0.1:9390` (Targets_Tasks, Reports)

### Conexión TLS vs Unix Socket

Este proyecto usa **TLS connection** (puerto 9390) en lugar de Unix Socket para mayor compatibilidad con Docker:

- ✅ **TLS (127.0.0.1:9390)**: Funciona desde el host hacia el contenedor
- ❌ **Unix Socket**: Requiere que el socket esté montado como volumen

Los scripts en `Targets_Tasks/` usan TLS y funcionan perfectamente desde el host.

## Cron Jobs

Para automatizar la ejecución, configurar cron en el **host**:

```bash
crontab -e
```

Agregar:

```cron
# Ejecutar tareas cada 15 minutos
*/15 * * * * /opt/gvm/Cron/run_task.sh
```

## Seguridad

### Consideraciones

1. **Puertos en localhost**: Los puertos están expuestos solo en `127.0.0.1`, no son accesibles desde la red
2. **Cambiar contraseña**: Modificar la contraseña por defecto después del primer inicio
3. **Reverse Proxy**: Para acceso remoto, usar un reverse proxy con HTTPS (nginx, traefik)
4. **Firewall**: Asegurar que los puertos no estén expuestos públicamente

### Cambiar contraseña de admin

Dentro del contenedor:

```bash
docker exec -it openvas gvmd --user=admin --new-password='NuevaContraseñaSegura123!'
```

### Configurar reverse proxy (opcional)

Para acceso remoto seguro, configurar nginx como reverse proxy:

```nginx
server {
    listen 443 ssl http2;
    server_name openvas.ejemplo.com;

    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;

    location / {
        proxy_pass https://127.0.0.1:9392;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_ssl_verify off;
    }
}
```

## Mantenimiento del Contenedor

### Actualizar imagen de OpenVAS

```bash
docker-compose pull
docker-compose up -d
```

### Backup de datos

```bash
# Crear backup del volumen
docker run --rm \
  -v openvas-docker-automatic_openvas-data:/data \
  -v $(pwd):/backup \
  alpine tar czf /backup/openvas-backup-$(date +%Y%m%d).tar.gz /data
```

### Restaurar desde backup

```bash
# Restaurar volumen desde backup
docker run --rm \
  -v openvas-docker-automatic_openvas-data:/data \
  -v $(pwd):/backup \
  alpine tar xzf /backup/openvas-backup-20260128.tar.gz -C /
```

## Troubleshooting

### El contenedor no inicia

```bash
# Ver logs detallados
docker-compose logs openvas

# Verificar recursos del sistema
docker stats
```

### No se puede acceder a la interfaz web

```bash
# Verificar que el puerto esté expuesto
docker-compose ps

# Verificar que el servicio gsad esté corriendo
docker exec -it openvas ps aux | grep gsad

# Verificar logs
docker exec -it openvas tail -f /var/log/gvm/gsad.log
```

### Los scripts no se conectan

```bash
# Verificar que el puerto 9390 esté escuchando
docker exec -it openvas netstat -tuln | grep 9390

# Probar conexión desde el host
telnet 127.0.0.1 9390
# O con openssl
openssl s_client -connect 127.0.0.1:9390
```

### Feeds no se actualizan

```bash
# Ejecutar actualización manual dentro del contenedor
docker exec -it openvas greenbone-feed-sync --type GVMD_DATA
docker exec -it openvas greenbone-feed-sync --type SCAP
docker exec -it openvas greenbone-feed-sync --type CERT
```

### Contenedor usa mucha memoria

OpenVAS requiere recursos significativos:
- **RAM**: Mínimo 4GB, recomendado 8GB
- **CPU**: Mínimo 2 cores, recomendado 4+
- **Disco**: Mínimo 20GB para feeds y reportes

Si tienes problemas de recursos:

```bash
# Limitar memoria del contenedor (docker-compose.yml)
services:
  openvas:
    # ... otras configuraciones
    deploy:
      resources:
        limits:
          memory: 8G
        reservations:
          memory: 4G
```

## Diferencias con Instalación Nativa

| Aspecto | Docker | Nativa |
|---------|--------|--------|
| Instalación | `docker-compose up` | Scripts complejos |
| Tiempo inicial | 15-30 min | 1-2 horas |
| Dependencias | Incluidas en imagen | Manual |
| Actualizaciones | `docker-compose pull` | Scripts de actualización |
| Aislamiento | Contenedor | Sistema host |
| Persistencia | Volúmenes Docker | Filesystem host |
| Conexión scripts | TLS (9390) | TLS o Unix Socket |

## Recursos

- [Imagen Docker oficial](https://hub.docker.com/r/immauss/openvas)
- [Documentación OpenVAS](https://docs.greenbone.net/)
- [Greenbone Community](https://community.greenbone.net/)
- [GVM Python Library](https://python-gvm.readthedocs.io/)

## Soporte

Para problemas específicos del contenedor Docker, consultar:
- Issues de la imagen: https://github.com/immauss/openvas/issues
- Documentación del proyecto: README.md

