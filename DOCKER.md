# Despliegue con Docker Compose

Este proyecto incluye configuración Docker Compose para ejecutar OpenVAS en un contenedor.

## Archivo docker-compose.yml

El archivo `docker-compose.yml` está configurado para desplegar OpenVAS usando la imagen oficial de [immauss/openvas](https://hub.docker.com/r/immauss/openvas).

### Configuración

```yaml
version: "3.9"

services:
  openvas:
    image: immauss/openvas:latest
    container_name: openvas
    restart: unless-stopped
    
    # Límites de recursos (anti-OOM)
    mem_limit: 10g
    mem_reservation: 8g
    cpus: "2.0"
    
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
      - TZ=UTC
    
    # Autoheal solo reinicia contenedores con esta label
    labels:
      - autoheal=true
    
    # Healthcheck: verifica procesos críticos + web
    healthcheck:
      test: ["CMD-SHELL", "pgrep -x gvmd >/dev/null && pgrep -f ospd-openvas >/dev/null && pgrep -x redis-server >/dev/null && pgrep -x postgres >/dev/null && ( (command -v curl >/dev/null && curl -fsS http://127.0.0.1:9392 >/dev/null) || (command -v wget >/dev/null && wget -qO- http://127.0.0.1:9392 >/dev/null) )"]
      interval: 60s
      timeout: 10s
      retries: 3
      start_period: 180s
    
    # Prioridad baja para el OOM killer
    oom_score_adj: -500

  autoheal:
    image: willfarrell/autoheal
    container_name: autoheal
    restart: unless-stopped
    environment:
      - AUTOHEAL_INTERVAL=30
      - AUTOHEAL_START_PERIOD=120
      - AUTOHEAL_ONLY_LABEL=true
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock:ro

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
- **TZ**: Zona horaria del contenedor (por defecto: `UTC`)

#### Sistema de Auto-Recuperación

El docker-compose incluye:
- **Healthcheck**: Verifica procesos críticos y disponibilidad web cada 60 segundos
- **Autoheal**: Reinicia automáticamente contenedores unhealthy
- **Límites de recursos**: Previene OOM y consumo excesivo de CPU
- **Protección OOM**: Reduce la probabilidad de que el kernel mate el proceso

Ver sección [Sistema de Auto-Recuperación](#sistema-de-auto-recuperación) para más detalles.

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

## Sistema de Auto-Recuperación

El docker-compose incluye un sistema robusto de monitoreo y recuperación automática para prevenir y resolver caídas de servicios.

### Healthcheck

El contenedor OpenVAS incluye un healthcheck que verifica periódicamente:

1. **Procesos críticos** (cada 60 segundos):
   - `gvmd` (Greenbone Vulnerability Manager)
   - `ospd-openvas` (OpenVAS Scanner Protocol daemon)
   - `redis-server` (Cache y colas)
   - `postgres` (Base de datos)

2. **Disponibilidad web**:
   - Verifica que la interfaz web responda en el puerto 9392
   - Usa `curl` si está disponible, o `wget` como alternativa

**Configuración del healthcheck:**
- **Intervalo**: 60 segundos
- **Timeout**: 10 segundos por verificación
- **Reintentos**: 3 fallos consecutivos marcan el contenedor como `unhealthy`
- **Periodo de inicio**: 180 segundos (da tiempo para la inicialización completa)

### Autoheal

El servicio `autoheal` monitorea automáticamente los contenedores con la etiqueta `autoheal=true` y los reinicia cuando detecta que están `unhealthy`.

**Características:**
- **Intervalo de verificación**: 30 segundos
- **Periodo de inicio**: 120 segundos (espera antes de monitorear contenedores nuevos)
- **Solo etiquetados**: Solo actúa sobre contenedores con `autoheal=true` (seguridad)
- **Acceso read-only**: Solo lectura al socket de Docker

**Cómo funciona:**
1. Autoheal verifica cada 30 segundos el estado de salud de los contenedores
2. Si detecta un contenedor `unhealthy` (después de 3 fallos del healthcheck)
3. Reinicia automáticamente el contenedor
4. Registra la acción en sus logs

### Límites de Recursos

Para prevenir problemas de OOM (Out of Memory) y consumo excesivo de recursos:

- **Memoria máxima**: 10GB (`mem_limit: 10g`)
- **Memoria reservada**: 8GB (`mem_reservation: 8g`)
- **CPU**: Limitado a 2 cores (`cpus: "2.0"`)
- **Protección OOM**: `oom_score_adj: -500` (reduce la probabilidad de que el kernel mate el proceso)

### Verificar el Estado de Salud

```bash
# Ver el estado de salud del contenedor
docker inspect openvas --format='{{.State.Health.Status}}'

# Ver detalles completos del healthcheck
docker inspect openvas --format='{{json .State.Health}}' | jq

# Ver logs del healthcheck
docker inspect openvas --format='{{range .State.Health.Log}}{{.Output}}{{end}}'
```

### Ver Logs de Autoheal

```bash
# Ver logs del contenedor autoheal
docker logs autoheal

# Seguir logs en tiempo real
docker logs -f autoheal
```

### Ejemplo de Salida del Healthcheck

```bash
$ docker inspect openvas --format='{{json .State.Health}}' | jq
{
  "Status": "healthy",
  "FailingStreak": 0,
  "Log": [
    {
      "Start": "2026-02-02T10:00:00.000000000Z",
      "End": "2026-02-02T10:00:10.123456789Z",
      "ExitCode": 0,
      "Output": ""
    }
  ]
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

Los límites están configurados en `docker-compose.yml`:
- Memoria máxima: 10GB
- Memoria reservada: 8GB
- CPU: 2 cores

Si necesitas ajustar los límites, edita `docker-compose.yml` y reinicia:

```bash
docker-compose down
docker-compose up -d
```

### Verificar el estado del healthcheck

Si el contenedor se reinicia constantemente, verifica el estado del healthcheck:

```bash
# Ver el estado actual
docker inspect openvas --format='{{.State.Health.Status}}'

# Ver el historial de verificaciones
docker inspect openvas --format='{{range .State.Health.Log}}{{println .Output}}{{end}}'

# Ver qué proceso está fallando
docker exec -it openvas ps aux | grep -E "gvmd|ospd|redis|postgres"
```

**Estados posibles:**
- `healthy`: Todos los servicios funcionan correctamente
- `unhealthy`: El healthcheck falló 3 veces consecutivas
- `starting`: El contenedor está en el período de inicio (primeros 180 segundos)

### Autoheal reinicia constantemente el contenedor

Si autoheal reinicia el contenedor repetidamente, puede indicar un problema más profundo:

1. **Verificar logs del contenedor**:
   ```bash
   docker logs --tail 100 openvas
   ```

2. **Verificar logs de autoheal**:
   ```bash
   docker logs autoheal
   ```

3. **Verificar recursos del sistema**:
   ```bash
   # Ver uso de recursos en tiempo real
   docker stats openvas
   
   # Verificar memoria disponible en el host
   free -h
   ```

4. **Verificar qué servicio está fallando**:
   ```bash
   # Verificar procesos dentro del contenedor
   docker exec -it openvas ps aux
   
   # Verificar logs de servicios específicos
   docker exec -it openvas tail -f /var/log/gvm/gvmd.log
   docker exec -it openvas tail -f /var/log/gvm/ospd-openvas.log
   ```

5. **Deshabilitar temporalmente autoheal** (para debugging):
   ```bash
   # Detener autoheal
   docker stop autoheal
   
   # Reiniciar openvas manualmente
   docker restart openvas
   
   # Monitorear manualmente
   docker logs -f openvas
   ```

### Ajustar límites de recursos según necesidades

Si tu servidor tiene más o menos recursos, puedes ajustar los límites en `docker-compose.yml`:

```yaml
services:
  openvas:
    # Para servidores con más recursos
    mem_limit: 16g
    mem_reservation: 12g
    cpus: "4.0"
    
    # Para servidores con menos recursos
    # mem_limit: 8g
    # mem_reservation: 6g
    # cpus: "1.5"
```

**Recomendaciones:**
- **Mínimo**: 8GB RAM, 2 CPUs
- **Recomendado**: 16GB RAM, 4 CPUs
- **Producción**: 32GB+ RAM, 8+ CPUs

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

