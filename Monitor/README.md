# Servicio de Monitoreo OpenVAS

Servicio de monitoreo completo que verifica el estado del contenedor Docker, servicios internos de GVM, actualizaciones de imagen y el servicio Docker daemon, con alertas proactivas por Telegram.

## Características

- ✅ Verificación del contenedor Docker
- ✅ Verificación del servicio Docker daemon
- ✅ Verificación de servicios GVM (gvmd, gsad)
- ✅ Verificación de conexión TLS a GVM
- ✅ Detección de actualizaciones de imagen
- ✅ Alertas por Telegram con formato estructurado
- ✅ Logs estructurados en JSON
- ✅ Sistema de cooldown para evitar spam de alertas
- ✅ Ejecución automática cada 5 minutos mediante systemd timer

## Ventajas sobre Healthcheck Docker

1. **Más completo:** Verifica múltiples aspectos (contenedor, servicios, imagen)
2. **Alertas proactivas:** Notifica antes de que el problema sea crítico
3. **Historial:** Logs estructurados para análisis
4. **Flexible:** Configurable sin reiniciar contenedor
5. **Independiente:** Funciona aunque Docker tenga problemas

## Instalación

### 1. Configurar Bot de Telegram

Antes de instalar el servicio, necesitas crear un bot de Telegram:

1. Abre Telegram y busca `@BotFather`
2. Envía el comando `/newbot`
3. Sigue las instrucciones para crear el bot:
   - Elige un nombre para tu bot
   - Elige un username (debe terminar en `bot`)
4. **Guarda el bot_token** que te proporciona BotFather (ejemplo: `123456789:ABCdefGHIjklMNOpqrsTUVwxyz`)

5. Para obtener el **chat_id**:
   
   **Si es un chat personal:**
   - Opción A: Envía un mensaje a tu bot y luego visita:
     ```
     https://api.telegram.org/bot<BOT_TOKEN>/getUpdates
     ```
     Busca `"chat":{"id":` en la respuesta JSON
   
   - Opción B: Usa el bot `@userinfobot` en Telegram para obtener tu chat_id directamente
   
   **Si es un CANAL (como en tu caso):**
   
   1. **Añade el bot al canal como administrador:**
      - Ve a la configuración del canal
      - Administradores → Añadir administrador
      - Busca tu bot y añádelo (puede tener permisos limitados, solo necesita poder enviar mensajes)
   
   2. **Envía un mensaje al canal** (puede ser cualquier mensaje, incluso desde el bot)
   
   3. **Obtén el chat_id del canal:**
      - Visita en tu navegador (reemplaza `<BOT_TOKEN>` con tu token):
        ```
        https://api.telegram.org/bot<BOT_TOKEN>/getUpdates
        ```
      - Busca en la respuesta JSON el objeto que contiene tu canal
      - El `chat_id` de un canal **siempre es negativo** (ejemplo: `-1001234567890`)
      - Busca algo como: `"chat":{"id":-1001234567890,"title":"Nombre del Canal","type":"channel"}`
   
   **Método alternativo para canales:**
   - Usa el bot `@getidsbot` en Telegram
   - Fórward un mensaje del canal a `@getidsbot`
   - Te mostrará el chat_id del canal (será un número negativo)
   
   **Nota importante:** El chat_id de un canal siempre empieza con `-100` seguido de más números. Por ejemplo: `-1001234567890`

### 2. Configurar Túnel SSH SOCKS (Opcional - Solo si Telegram está bloqueado)

Si Telegram está bloqueado por firewall corporativo, puedes usar un túnel SSH SOCKS a través de tu VPS:

**Requisitos previos:**
- Tu clave SSH pública debe estar en `~/.ssh/authorized_keys` del usuario en el VPS
- El servicio se ejecuta como `root`, así que usará la clave SSH de root (`/root/.ssh/id_rsa`)
- Asegúrate de que la clave pública de root esté en el `authorized_keys` del VPS

**Crear configuración del túnel** en `/opt/gvm/Monitor/config.json`:
```json
{
    "ssh_tunnel": {
        "enabled": true,
        "vps_host": "tu-vps.ejemplo.com",
        "vps_port": 22,
        "vps_user": "usuario",
        "ssh_key_path": null,
        "socks_port": 1080,
        "socks_host": "127.0.0.1"
    }
}
```

**Parámetros del túnel SSH:**
- `enabled`: Habilitar túnel SSH SOCKS (true/false)
- `vps_host`: IP o dominio de tu VPS
- `vps_port`: Puerto SSH del VPS (normalmente 22)
- `vps_user`: Usuario SSH en el VPS
- `ssh_key_path`: Ruta a la clave SSH privada (opcional, si es `null` usa la clave por defecto del usuario)
- `socks_port`: Puerto local para el proxy SOCKS (1080 por defecto)
- `socks_host`: Host local para el proxy SOCKS (127.0.0.1 por defecto)

**Nota:** 
- El túnel se crea bajo demanda (solo cuando se necesita enviar una alerta) y se cierra automáticamente después
- Si `ssh_key_path` es `null` o no se especifica, se usará la clave SSH por defecto del usuario (normalmente `/root/.ssh/id_rsa`)
- Asegúrate de que la clave pública esté en el `authorized_keys` del VPS antes de usar el servicio

### 3. Configurar config.json

Edita `/opt/gvm/Config/config.json` y añade la sección `monitoring`:

```json
{
  "monitoring": {
    "enabled": true,
    "check_interval": 300,
    "alert_on_container_down": true,
    "alert_on_docker_down": true,
    "alert_on_gvm_down": true,
    "alert_on_image_update": true,
    "alert_cooldown": 3600,
    "telegram": {
      "bot_token": "123456789:ABCdefGHIjklMNOpqrsTUVwxyz",
      "chat_id": "123456789"
    }
  }
}
```

**Parámetros de configuración:**

- `enabled`: Habilitar/deshabilitar el monitoreo (true/false)
- `check_interval`: Intervalo de verificación en segundos (no usado actualmente, se controla con systemd timer)
- `alert_on_container_down`: Enviar alerta si el contenedor está detenido (true/false)
- `alert_on_docker_down`: Enviar alerta si Docker daemon está detenido (true/false)
- `alert_on_gvm_down`: Enviar alerta si GVM no responde (true/false)
- `alert_on_image_update`: Enviar alerta si hay actualización de imagen disponible (true/false)
- `alert_cooldown`: Tiempo en segundos entre alertas del mismo tipo (3600 = 1 hora)
- `telegram.bot_token`: Token del bot de Telegram obtenido de @BotFather
- `telegram.chat_id`: Tu chat_id de Telegram

### 3. Instalar el Servicio

Ejecuta el script de instalación:

```bash
sudo ./Monitor/install-monitor.sh
```

El script:
- Copia los archivos necesarios a `/opt/gvm/Monitor/`
- Instala los archivos systemd
- Crea los directorios de logs
- Verifica dependencias
- Habilita el timer (pero no lo inicia)

### 4. Iniciar el Servicio

```bash
# Iniciar el timer
sudo systemctl start openvas-monitor.timer

# Verificar que está activo
sudo systemctl status openvas-monitor.timer
```

## Uso

### Comandos Útiles

```bash
# Ver estado del timer
sudo systemctl status openvas-monitor.timer

# Ver logs del servicio
sudo journalctl -u openvas-monitor.service -f

# Ejecutar verificación manualmente
sudo systemctl start openvas-monitor.service

# Detener el timer
sudo systemctl stop openvas-monitor.timer

# Deshabilitar el timer (no se iniciará al reiniciar)
sudo systemctl disable openvas-monitor.timer

# Ver próximas ejecuciones programadas
systemctl list-timers openvas-monitor.timer
```

### Verificar Logs

Los logs se guardan en dos lugares:

1. **Log estructurado JSON:** `/opt/gvm/logs/monitoring/monitor.log`
   ```bash
   tail -f /opt/gvm/logs/monitoring/monitor.log
   ```

2. **Logs de systemd:**
   ```bash
   sudo journalctl -u openvas-monitor.service -f
   ```

### Formato de Logs

El log estructurado contiene entradas JSON con el siguiente formato:

```json
{
  "timestamp": "2024-01-15T10:30:00",
  "status": "ok|warning|error",
  "checks": {
    "container": "ok",
    "docker": "ok",
    "gvmd": "ok",
    "gsad": "ok",
    "gvm_connection": "ok",
    "image": "ok"
  },
  "alerts_sent": false
}
```

## Alertas por Telegram

### Tipos de Alertas

El servicio envía alertas formateadas con emojis para identificar el tipo:

- 🐳 **Contenedor:** El contenedor Docker no está corriendo
- 🔧 **Docker:** El servicio Docker daemon no está activo
- 🛡️ **GVM (gvmd):** El puerto 9390 no responde
- 🌐 **GSAD:** El puerto 9392 (web UI) no responde
- 🔌 **Conexión GVM:** No se puede conectar a GVM vía TLS
- 🔄 **Imagen:** Hay una actualización disponible para la imagen Docker

### Ejemplo de Mensaje

```
🐳 ALERTA: CONTAINER

Estado: Contenedor no está corriendo
Hora: 2024-01-15 10:30:00
Acción: Verificar con 'docker ps -a' y 'docker start openvas'
```

### Sistema de Cooldown

Para evitar spam de alertas, el servicio implementa un sistema de cooldown:
- Cada tipo de alerta solo se envía una vez por el período configurado (`alert_cooldown`)
- El estado se guarda en `/opt/gvm/logs/monitoring/alert_cooldown.json`
- Por defecto: 3600 segundos (1 hora) entre alertas del mismo tipo

## Verificaciones Realizadas

El servicio verifica los siguientes aspectos:

1. **Contenedor Docker:**
   - Verifica que el contenedor `openvas` esté corriendo
   - Usa `docker ps` para verificar el estado

2. **Docker Daemon:**
   - Verifica que el servicio `docker` esté activo
   - Usa `systemctl is-active docker`

3. **Puerto GVM (gvmd):**
   - Verifica que el puerto 9390 esté abierto y respondiendo
   - Conexión TCP al localhost

4. **Puerto GSAD (Web UI):**
   - Verifica que el puerto 9392 esté abierto y respondiendo
   - Conexión TCP al localhost

5. **Conexión GVM:**
   - Intenta conectar vía TLS al puerto 9390
   - Autentica con las credenciales del config.json
   - Obtiene la versión de GVM

6. **Actualización de Imagen:**
   - Verifica si hay actualizaciones disponibles para `immauss/openvas:latest`
   - Usa `docker pull --dry-run`

## Solución de Problemas

### El servicio no se ejecuta

1. Verifica que el timer esté activo:
   ```bash
   sudo systemctl status openvas-monitor.timer
   ```

2. Verifica los logs:
   ```bash
   sudo journalctl -u openvas-monitor.service -n 50
   ```

3. Ejecuta manualmente para ver errores:
   ```bash
   sudo /usr/bin/python3 /opt/gvm/Monitor/monitor.py
   ```

### No recibo alertas por Telegram

1. Verifica que las credenciales estén correctas en `config.json`
2. Prueba el bot manualmente:
   ```bash
   curl -X POST "https://api.telegram.org/bot<BOT_TOKEN>/sendMessage" \
     -d "chat_id=<CHAT_ID>&text=Test"
   ```
3. Verifica los logs del servicio para ver errores de conexión
4. Asegúrate de que `monitoring.enabled` esté en `true`

### Errores de permisos

1. Verifica que el script tenga permisos de ejecución:
   ```bash
   chmod +x /opt/gvm/Monitor/monitor.py
   ```

2. Verifica que el usuario tenga acceso a Docker:
   ```bash
   sudo usermod -aG docker $USER
   ```

### El servicio no puede verificar Docker

1. Verifica que Docker CLI esté disponible:
   ```bash
   which docker
   docker ps
   ```

2. Verifica que el usuario del servicio tenga permisos:
   - El servicio se ejecuta como `root` por defecto
   - Si cambias el usuario, asegúrate de que tenga acceso a Docker

## Desinstalación

Para desinstalar el servicio:

```bash
# Detener y deshabilitar el timer
sudo systemctl stop openvas-monitor.timer
sudo systemctl disable openvas-monitor.timer

# Eliminar archivos systemd
sudo rm /etc/systemd/system/openvas-monitor.service
sudo rm /etc/systemd/system/openvas-monitor.timer

# Recargar systemd
sudo systemctl daemon-reload

# (Opcional) Eliminar archivos del servicio
sudo rm -rf /opt/gvm/Monitor
sudo rm -rf /opt/gvm/logs/monitoring
```

## Estructura de Archivos

```
Monitor/
├── monitor.py              # Script principal de monitoreo
├── install-monitor.sh      # Instalador del servicio
├── openvas-monitor.service # Servicio systemd
├── openvas-monitor.timer   # Timer systemd
└── README.md               # Esta documentación

/opt/gvm/
├── Monitor/                # Archivos del servicio (instalados)
│   └── monitor.py
└── logs/
    └── monitoring/        # Logs del servicio
        ├── monitor.log     # Log estructurado JSON
        └── alert_cooldown.json  # Estado de cooldown
```

## Dependencias

- Python 3.x
- `requests` (para API de Telegram) - ya en requirements.txt
- `PySocks` (para soporte SOCKS5) - ya en requirements.txt
- `python-gvm` (para conexión GVM) - ya en requirements.txt
- Docker CLI (para verificar contenedor)
- systemctl (para verificar Docker daemon)
- SSH client (para túnel SOCKS, si está habilitado)

## Seguridad

- El servicio se ejecuta como `root` para tener acceso a Docker y systemctl
- Las credenciales de Telegram se leen desde `config.json` (asegúrate de proteger este archivo)
- Los logs no exponen credenciales (bot_token, chat_id)
- Rate limiting implementado mediante cooldown para evitar spam

## Contribuir

Si encuentras problemas o tienes sugerencias, por favor abre un issue en el repositorio.

## Licencia

Este proyecto es parte del sistema de automatización de OpenVAS Docker.

