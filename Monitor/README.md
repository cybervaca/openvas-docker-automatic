# Servicio de Monitoreo OpenVAS

Servicio de monitoreo completo que verifica el estado del contenedor Docker, servicios internos de GVM, actualizaciones de imagen y el servicio Docker daemon, con alertas proactivas por Telegram.

## Características

- ✅ Verificación del contenedor Docker
- ✅ Verificación del servicio Docker daemon
- ✅ Verificación de servicios GVM (gvmd, gsad)
- ✅ Verificación de conexión TLS a GVM
- ✅ Verificación de actualización de feeds de vulnerabilidades
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

**IMPORTANTE:** El archivo `/opt/gvm/Monitor/config.json` es completamente opcional. Si no existe, el servicio funcionará normalmente sin túnel SOCKS, conectándose directamente a Telegram.

Si Telegram está bloqueado por firewall corporativo, puedes crear este archivo para usar un túnel SSH SOCKS a través de tu VPS:

**Requisitos previos:**
- Tu clave SSH pública debe estar en `~/.ssh/authorized_keys` del usuario en el VPS
- El servicio se ejecuta como `redteam`, así que usará la clave SSH de ese usuario (normalmente `/home/redteam/.ssh/id_rsa` o la especificada en `ssh_key_path`)
- Asegúrate de que la clave pública esté en el `authorized_keys` del VPS

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

**Notas importantes:** 
- **El archivo es opcional:** Si `/opt/gvm/Monitor/config.json` no existe, el servicio funcionará sin túnel SOCKS
- El túnel se crea bajo demanda (solo cuando se necesita enviar una alerta) y se cierra automáticamente después
- Si `ssh_key_path` es `null` o no se especifica, se usará la clave SSH por defecto del usuario `redteam` (normalmente `/home/redteam/.ssh/id_rsa`)
- Asegúrate de que la clave pública esté en el `authorized_keys` del VPS antes de usar el servicio
- Si no necesitas túnel SOCKS (Telegram no está bloqueado), simplemente no crees este archivo

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
- `alert_on_feeds_stale`: Enviar alerta si los feeds están desactualizados (true/false)
- `feed_stale_days`: Número de días sin actualizar para considerar un feed como desactualizado (default: 30)
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
- 📦 **Feeds:** Los feeds de vulnerabilidades están desactualizados (>30 días)
- 🔄 **Imagen:** Hay una actualización disponible para la imagen Docker

### Ejemplo de Mensaje

**Alerta de Contenedor:**
```
🐳 ALERTA: CONTAINER

Estado: Contenedor no está corriendo
Hora: 2024-01-15 10:30:00
Acción: Verificar con 'docker ps -a' y 'docker start openvas'
```

**Alerta de Feeds Desactualizados:**
```
🟡 ADVERTENCIA: OpenVAS Monitor

📦 FEEDS DESACTUALIZADOS:

• NVT: 35 días sin actualizar
  Última actualización: 2023-12-10 15:30:00

• SCAP: 32 días sin actualizar
  Última actualización: 2023-12-13 10:20:00

Estado de todos los feeds:
✅ GVMD_DATA: 5 días (Última: 2024-01-10 12:00:00)
✅ CERT: 8 días (Última: 2024-01-07 14:30:00)
⚠️ NVT: 35 días (Última: 2023-12-10 15:30:00)
⚠️ SCAP: 32 días (Última: 2023-12-13 10:20:00)

ACCIONES RECOMENDADAS:
📦 Feeds: Ejecutar '/opt/gvm/Cron/actualiza_gvm.sh'
```

### Sistema de Cooldown

Para evitar spam de alertas, el servicio implementa un sistema de cooldown:
- Cada tipo de alerta solo se envía una vez por el período configurado (`alert_cooldown`)
- El estado se guarda en `/opt/gvm/logs/monitoring/alert_cooldown.json`
- Por defecto: 3600 segundos (1 hora) entre alertas del mismo tipo

### Auto-actualización de Feeds

Además de las alertas, el monitor puede intentar actualizar los feeds automáticamente si detecta que algún feed lleva `>= 15` días sin actualizarse.

- El auto-update se ejecuta llamando a `/opt/gvm/Cron/actualiza_gvm.sh` (Docker-only).
- Para evitar ejecuciones repetidas cada pocos minutos, existe un cooldown separado de `24h`.
- El estado del cooldown se guarda en `/opt/gvm/logs/monitoring/auto_update_cooldown.json`.

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

6. **Feeds de Vulnerabilidades:**
   - Verifica la fecha de última actualización de los feeds (NVTs, SCAP, CERT, GVMD_DATA)
   - Usa el protocolo GMP para obtener información de feeds
   - Calcula días desde última actualización
   - Alerta si algún feed tiene más de 30 días sin actualizar (configurable con `feed_stale_days`)

7. **Actualización de Imagen:**
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

2. Verifica que el usuario del servicio tenga acceso a Docker:
   ```bash
   # El servicio se ejecuta como redteam
   sudo usermod -aG docker redteam
   # Reinicia el servicio para aplicar cambios
   sudo systemctl restart openvas-monitor.service
   ```

### El servicio no puede verificar Docker

1. Verifica que Docker CLI esté disponible:
   ```bash
   which docker
   docker ps
   ```

2. Verifica que el usuario del servicio tenga permisos:
   - El servicio se ejecuta como `redteam` (usuario no-root)
   - El usuario `redteam` debe estar en el grupo `docker`
   - El script de instalación configura esto automáticamente
   - Si hay problemas, verifica: `groups redteam` (debe incluir `docker`)

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

- El servicio se ejecuta como `redteam` (usuario no-root) para mejorar la seguridad
- El usuario `redteam` está en el grupo `docker` para tener acceso a comandos Docker
- Los permisos de archivos y directorios se configuran automáticamente durante la instalación
- Las credenciales de Telegram se leen desde `config.json` (asegúrate de proteger este archivo)
- Los logs no exponen credenciales (bot_token, chat_id)
- Rate limiting implementado mediante cooldown para evitar spam

## Contribuir

Si encuentras problemas o tienes sugerencias, por favor abre un issue en el repositorio.

## Licencia

Este proyecto es parte del sistema de automatización de OpenVAS Docker.

