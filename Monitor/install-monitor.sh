#!/bin/bash
#
# Script de instalación del servicio de monitoreo OpenVAS
# Este script instala y configura el servicio systemd para monitoreo
#

set -e

# Colores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Rutas
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SYSTEMD_DIR="/etc/systemd/system"
MONITOR_DIR="/opt/gvm/Monitor"
LOG_DIR="/opt/gvm/logs/monitoring"
CONFIG_FILE="/opt/gvm/Config/config.json"

echo -e "${GREEN}=== Instalador del Servicio de Monitoreo OpenVAS ===${NC}\n"

# Verificar que se ejecuta como root
if [ "$EUID" -ne 0 ]; then 
    echo -e "${RED}ERROR: Este script debe ejecutarse como root${NC}"
    echo "Por favor ejecuta: sudo $0"
    exit 1
fi

# Verificar que existe el directorio de origen
if [ ! -d "$SCRIPT_DIR" ]; then
    echo -e "${RED}ERROR: No se encontró el directorio de instalación${NC}"
    exit 1
fi

# Verificar que existe monitor.py
if [ ! -f "$SCRIPT_DIR/monitor.py" ]; then
    echo -e "${RED}ERROR: No se encontró monitor.py en $SCRIPT_DIR${NC}"
    exit 1
fi

# Usuario para ejecutar el servicio
SERVICE_USER="redteam"
SERVICE_GROUP="redteam"

# Verificar que el usuario existe, crearlo si no existe
echo -e "${YELLOW}Verificando usuario del servicio...${NC}"
if ! id "$SERVICE_USER" &>/dev/null; then
    echo -e "${YELLOW}El usuario $SERVICE_USER no existe. Creándolo...${NC}"
    # Crear usuario con shell /bin/bash y directorio home
    useradd -m -s /bin/bash "$SERVICE_USER" 2>/dev/null || {
        echo -e "${RED}ERROR: No se pudo crear el usuario $SERVICE_USER${NC}"
        echo "Por favor crea el usuario manualmente o modifica el servicio para usar otro usuario"
        exit 1
    }
    echo -e "${GREEN}✓ Usuario $SERVICE_USER creado${NC}"
else
    echo -e "${GREEN}✓ Usuario $SERVICE_USER encontrado${NC}"
fi

# Verificar y agregar usuario al grupo docker
echo -e "${YELLOW}Verificando acceso a Docker...${NC}"
if getent group docker > /dev/null 2>&1; then
    if groups "$SERVICE_USER" | grep -q "\bdocker\b"; then
        echo -e "${GREEN}✓ Usuario $SERVICE_USER ya está en el grupo docker${NC}"
    else
        echo -e "${YELLOW}Agregando usuario $SERVICE_USER al grupo docker...${NC}"
        usermod -aG docker "$SERVICE_USER"
        echo -e "${GREEN}✓ Usuario $SERVICE_USER agregado al grupo docker${NC}"
        echo -e "${YELLOW}NOTA: El usuario necesitará reiniciar sesión para que los cambios surtan efecto${NC}"
        echo -e "${YELLOW}      Para servicios systemd, esto se aplica automáticamente${NC}"
    fi
else
    echo -e "${YELLOW}ADVERTENCIA: El grupo docker no existe${NC}"
    echo "El servicio puede no funcionar correctamente sin acceso a Docker"
fi

# Crear directorio de destino
echo -e "${YELLOW}Creando directorio de destino...${NC}"
mkdir -p "$MONITOR_DIR"
mkdir -p "$LOG_DIR"

# Verificar si ya estamos en el directorio de destino
if [ "$(realpath "$SCRIPT_DIR")" = "$(realpath "$MONITOR_DIR")" ]; then
    echo -e "${GREEN}✓ Los archivos ya están en el directorio de destino${NC}"
    echo -e "${YELLOW}Asegurando permisos de ejecución...${NC}"
    chmod +x "$MONITOR_DIR/monitor.py" 2>/dev/null || true
else
    # Copiar archivos
    echo -e "${YELLOW}Copiando archivos...${NC}"
    cp "$SCRIPT_DIR/monitor.py" "$MONITOR_DIR/monitor.py"
    chmod +x "$MONITOR_DIR/monitor.py"
fi

# Configurar permisos en directorios y archivos
echo -e "${YELLOW}Configurando permisos...${NC}"

# Asegurar que el directorio padre /opt/gvm/ tiene permisos de ejecución para navegación
GVM_BASE_DIR="/opt/gvm"
if [ -d "$GVM_BASE_DIR" ]; then
    chmod 755 "$GVM_BASE_DIR" 2>/dev/null || true
fi

# Permisos en directorio Monitor (lectura/ejecución para el usuario)
chown -R "$SERVICE_USER:$SERVICE_GROUP" "$MONITOR_DIR"
chmod 755 "$MONITOR_DIR"
chmod 755 "$MONITOR_DIR/monitor.py"

# Permisos en directorio de logs (lectura/escritura para el usuario)
chown -R "$SERVICE_USER:$SERVICE_GROUP" "$LOG_DIR"
chmod 755 "$LOG_DIR"

# Permisos en directorio Config (lectura)
CONFIG_DIR="/opt/gvm/Config"
if [ -d "$CONFIG_DIR" ]; then
    # Asegurar que el usuario puede leer el directorio
    chmod 755 "$CONFIG_DIR"
fi

# Permisos en archivo de configuración principal (lectura)
if [ -f "$CONFIG_FILE" ]; then
    # Si el archivo es propiedad de root, permitir lectura al grupo o al mundo
    CONFIG_OWNER=$(stat -c '%U' "$CONFIG_FILE" 2>/dev/null || echo "root")
    if [ "$CONFIG_OWNER" = "root" ]; then
        # Permitir lectura al grupo si el grupo es _gvm o tiene permisos de grupo
        chmod 644 "$CONFIG_FILE"
        # Si el grupo del archivo no es _gvm, intentar cambiar el grupo o permisos
        CONFIG_GROUP=$(stat -c '%G' "$CONFIG_FILE" 2>/dev/null || echo "root")
        if [ "$CONFIG_GROUP" != "$SERVICE_GROUP" ]; then
            # Permitir lectura a todos (más permisivo pero funcional)
            chmod 644 "$CONFIG_FILE"
        fi
    else
        chmod 644 "$CONFIG_FILE"
    fi
fi

# Permisos en archivo de configuración del monitor (lectura, si existe)
MONITOR_CONFIG_FILE="/opt/gvm/Monitor/config.json"
if [ -f "$MONITOR_CONFIG_FILE" ]; then
    chown "$SERVICE_USER:$SERVICE_GROUP" "$MONITOR_CONFIG_FILE"
    chmod 640 "$MONITOR_CONFIG_FILE"
fi

# Verificar y configurar permisos en SSH keys si se usa túnel SSH
if [ -f "$MONITOR_CONFIG_FILE" ]; then
    SSH_KEY_PATH=$(python3 -c "import json; f=open('$MONITOR_CONFIG_FILE'); d=json.load(f); print(d.get('ssh_tunnel', {}).get('ssh_key_path', ''))" 2>/dev/null || echo "")
    if [ -n "$SSH_KEY_PATH" ] && [ -f "$SSH_KEY_PATH" ]; then
        echo -e "${YELLOW}Configurando permisos en SSH key...${NC}"
        chown "$SERVICE_USER:$SERVICE_GROUP" "$SSH_KEY_PATH"
        chmod 600 "$SSH_KEY_PATH"
        echo -e "${GREEN}✓ Permisos configurados en $SSH_KEY_PATH${NC}"
    fi
fi

echo -e "${GREEN}✓ Permisos configurados${NC}"

# Verificar si el servicio ya está instalado
SERVICE_INSTALLED=false
if systemctl list-unit-files | grep -q "openvas-monitor.service"; then
    SERVICE_INSTALLED=true
    echo -e "${YELLOW}El servicio ya está instalado. Reinstalando...${NC}"
    # Detener el timer y servicio si están activos
    if systemctl is-active --quiet openvas-monitor.timer; then
        echo -e "${YELLOW}Deteniendo timer...${NC}"
        systemctl stop openvas-monitor.timer 2>/dev/null || true
    fi
    if systemctl is-active --quiet openvas-monitor.service; then
        echo -e "${YELLOW}Deteniendo servicio...${NC}"
        systemctl stop openvas-monitor.service 2>/dev/null || true
    fi
fi

# Copiar archivos systemd
echo -e "${YELLOW}Instalando archivos systemd...${NC}"
cp "$SCRIPT_DIR/openvas-monitor.service" "$SYSTEMD_DIR/"
cp "$SCRIPT_DIR/openvas-monitor.timer" "$SYSTEMD_DIR/"

# Verificar configuración
echo -e "${YELLOW}Verificando configuración...${NC}"
if [ ! -f "$CONFIG_FILE" ]; then
    echo -e "${YELLOW}ADVERTENCIA: No se encontró $CONFIG_FILE${NC}"
    echo "Asegúrate de configurar el archivo antes de habilitar el servicio"
else
    # Verificar que tiene la sección monitoring
    if ! grep -q '"monitoring"' "$CONFIG_FILE"; then
        echo -e "${YELLOW}ADVERTENCIA: No se encontró la sección 'monitoring' en $CONFIG_FILE${NC}"
        echo "Revisa Config/config_example.json para ver el formato correcto"
    else
        # Verificar credenciales de Telegram
        if grep -q 'TU_BOT_TOKEN' "$CONFIG_FILE" || grep -q 'TU_CHAT_ID' "$CONFIG_FILE"; then
            echo -e "${YELLOW}ADVERTENCIA: Parece que las credenciales de Telegram no están configuradas${NC}"
            echo "Configura bot_token y chat_id en $CONFIG_FILE antes de habilitar el servicio"
        else
            echo -e "${GREEN}✓ Configuración encontrada${NC}"
        fi
    fi
fi

# Verificar configuración del túnel SSH (opcional)
MONITOR_CONFIG_FILE="/opt/gvm/Monitor/config.json"
if [ -f "$MONITOR_CONFIG_FILE" ]; then
    echo -e "${GREEN}✓ Configuración de túnel SSH encontrada (opcional)${NC}"
else
    echo -e "${YELLOW}ℹ️  Configuración de túnel SSH no encontrada (opcional)${NC}"
    echo "   Si Telegram está bloqueado, crea $MONITOR_CONFIG_FILE"
    echo "   Si Telegram no está bloqueado, no es necesario este archivo"
fi

# Recargar systemd
echo -e "${YELLOW}Recargando systemd...${NC}"
systemctl daemon-reload

# Habilitar timer
echo -e "${YELLOW}Habilitando timer...${NC}"
systemctl enable openvas-monitor.timer

# Si el servicio estaba instalado, reiniciarlo
if [ "$SERVICE_INSTALLED" = true ]; then
    echo -e "${YELLOW}Reiniciando timer con nueva configuración...${NC}"
    systemctl start openvas-monitor.timer
    echo -e "${GREEN}✓ Servicio reinstalado y reiniciado${NC}"
else
    echo -e "${GREEN}✓ Timer habilitado (no iniciado automáticamente)${NC}"
fi

# Verificar que Docker está disponible
if ! command -v docker &> /dev/null; then
    echo -e "${YELLOW}ADVERTENCIA: Docker no está disponible en PATH${NC}"
    echo "El servicio puede no funcionar correctamente"
fi

# Verificar que Python3 está disponible
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}ERROR: Python3 no está disponible${NC}"
    exit 1
fi

# Verificar dependencias Python
echo -e "${YELLOW}Verificando dependencias Python...${NC}"
if python3 -c "import requests" 2>/dev/null; then
    echo -e "${GREEN}✓ requests disponible${NC}"
else
    echo -e "${YELLOW}ADVERTENCIA: requests no está instalado${NC}"
    echo "Instala con: pip3 install requests"
fi

if python3 -c "from gvm.connections import TLSConnection" 2>/dev/null; then
    echo -e "${GREEN}✓ python-gvm disponible${NC}"
else
    echo -e "${YELLOW}ADVERTENCIA: python-gvm no está instalado${NC}"
    echo "Instala con: pip3 install python-gvm"
fi

echo ""
echo -e "${GREEN}=== Instalación completada ===${NC}\n"
echo "Próximos pasos:"
echo "1. Configura las credenciales de Telegram en $CONFIG_FILE"
echo "2. Inicia el timer con: sudo systemctl start openvas-monitor.timer"
echo "3. Verifica el estado con: sudo systemctl status openvas-monitor.timer"
echo "4. Ver los logs con: sudo journalctl -u openvas-monitor.service -f"
echo ""
echo "Comandos útiles:"
echo "  - Iniciar timer:     sudo systemctl start openvas-monitor.timer"
echo "  - Detener timer:      sudo systemctl stop openvas-monitor.timer"
echo "  - Estado del timer:   sudo systemctl status openvas-monitor.timer"
echo "  - Ver logs:           sudo journalctl -u openvas-monitor.service -f"
echo "  - Ejecutar manual:    sudo systemctl start openvas-monitor.service"
echo ""

