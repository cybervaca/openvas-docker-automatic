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

# Crear directorio de destino
echo -e "${YELLOW}Creando directorio de destino...${NC}"
mkdir -p "$MONITOR_DIR"
mkdir -p "$LOG_DIR"

# Copiar archivos
echo -e "${YELLOW}Copiando archivos...${NC}"
cp "$SCRIPT_DIR/monitor.py" "$MONITOR_DIR/monitor.py"
chmod +x "$MONITOR_DIR/monitor.py"

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

# Recargar systemd
echo -e "${YELLOW}Recargando systemd...${NC}"
systemctl daemon-reload

# Habilitar timer (pero no iniciarlo todavía)
echo -e "${YELLOW}Habilitando timer...${NC}"
systemctl enable openvas-monitor.timer

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

