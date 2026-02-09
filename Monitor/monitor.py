#!/usr/bin/env python3
"""
Servicio de Monitoreo OpenVAS
Verifica el estado del contenedor Docker, servicios GVM, y envía alertas por Telegram
"""

import warnings
# Suprimir warnings de deprecación
warnings.filterwarnings('ignore', category=DeprecationWarning)
warnings.filterwarnings('ignore', category=UserWarning)

import json
import os
import subprocess
import datetime
import socket
import requests
import sys
from gvm.connections import TLSConnection
from gvm.protocols.gmp import Gmp
import xml.etree.ElementTree as ET

# Configuración
CONFIG_PATH = '/opt/gvm/Config/config.json'
LOG_DIR = '/opt/gvm/logs/monitoring'
LOG_FILE = f'{LOG_DIR}/monitor.log'
ALERT_COOLDOWN_FILE = f'{LOG_DIR}/alert_cooldown.json'
CONTAINER_NAME = 'openvas'
GVM_PORT = 9390
GSAD_PORT = 9392

def leer_configuracion():
    """Lee la configuración desde config.json"""
    try:
        with open(CONFIG_PATH, 'r') as archivo:
            configuracion = json.load(archivo)
            return configuracion
    except FileNotFoundError:
        print(f"ERROR: El archivo '{CONFIG_PATH}' no se encontró.")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"ERROR: Error al decodificar el archivo JSON: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"ERROR: Ocurrió un error al leer configuración: {e}")
        sys.exit(1)

def escribir_log(mensaje, nivel='INFO'):
    """Escribe un mensaje en el log estructurado"""
    timestamp = datetime.datetime.now().isoformat()
    log_entry = {
        'timestamp': timestamp,
        'level': nivel,
        'message': mensaje
    }
    
    # Asegurar que el directorio existe
    os.makedirs(LOG_DIR, exist_ok=True)
    
    with open(LOG_FILE, 'a') as f:
        f.write(json.dumps(log_entry) + '\n')
    
    print(f"[{timestamp}] [{nivel}] {mensaje}")

def enviar_telegram(mensaje, bot_token, chat_id):
    """Envía un mensaje por Telegram"""
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        'chat_id': chat_id,
        'text': mensaje,
        'parse_mode': 'HTML'
    }
    
    try:
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()
        return True
    except requests.exceptions.RequestException as e:
        escribir_log(f"Error al enviar mensaje a Telegram: {e}", 'ERROR')
        return False

def cargar_cooldown():
    """Carga el estado de cooldown de alertas"""
    if os.path.exists(ALERT_COOLDOWN_FILE):
        try:
            with open(ALERT_COOLDOWN_FILE, 'r') as f:
                return json.load(f)
        except:
            return {}
    return {}

def guardar_cooldown(cooldown_data):
    """Guarda el estado de cooldown de alertas"""
    os.makedirs(LOG_DIR, exist_ok=True)
    with open(ALERT_COOLDOWN_FILE, 'w') as f:
        json.dump(cooldown_data, f)

def puede_enviar_alerta(tipo_alerta, config):
    """Verifica si se puede enviar una alerta según el cooldown"""
    cooldown_seconds = config.get('monitoring', {}).get('alert_cooldown', 3600)
    cooldown_data = cargar_cooldown()
    
    if tipo_alerta not in cooldown_data:
        return True
    
    ultimo_envio = datetime.datetime.fromisoformat(cooldown_data[tipo_alerta])
    tiempo_transcurrido = (datetime.datetime.now() - ultimo_envio).total_seconds()
    
    return tiempo_transcurrido >= cooldown_seconds

def registrar_alerta_enviada(tipo_alerta):
    """Registra que se envió una alerta"""
    cooldown_data = cargar_cooldown()
    cooldown_data[tipo_alerta] = datetime.datetime.now().isoformat()
    guardar_cooldown(cooldown_data)

def verificar_contenedor():
    """Verifica si el contenedor Docker está corriendo"""
    try:
        result = subprocess.run(
            ['docker', 'ps', '--filter', f'name={CONTAINER_NAME}', '--format', '{{.Names}}'],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if CONTAINER_NAME in result.stdout:
            return {'status': 'ok', 'message': 'Contenedor corriendo'}
        else:
            return {'status': 'error', 'message': 'Contenedor no está corriendo'}
    except subprocess.TimeoutExpired:
        return {'status': 'error', 'message': 'Timeout al verificar contenedor'}
    except FileNotFoundError:
        return {'status': 'error', 'message': 'Docker CLI no encontrado'}
    except Exception as e:
        return {'status': 'error', 'message': f'Error: {str(e)}'}

def verificar_docker_daemon():
    """Verifica si el servicio Docker daemon está activo"""
    try:
        result = subprocess.run(
            ['systemctl', 'is-active', 'docker'],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode == 0 and 'active' in result.stdout:
            return {'status': 'ok', 'message': 'Docker daemon activo'}
        else:
            return {'status': 'error', 'message': 'Docker daemon no está activo'}
    except subprocess.TimeoutExpired:
        return {'status': 'error', 'message': 'Timeout al verificar Docker daemon'}
    except Exception as e:
        return {'status': 'error', 'message': f'Error: {str(e)}'}

def verificar_puerto(host, port):
    """Verifica si un puerto está abierto y respondiendo"""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5)
        result = sock.connect_ex((host, port))
        sock.close()
        
        if result == 0:
            return {'status': 'ok', 'message': f'Puerto {port} abierto'}
        else:
            return {'status': 'error', 'message': f'Puerto {port} no responde'}
    except Exception as e:
        return {'status': 'error', 'message': f'Error al verificar puerto: {str(e)}'}

def verificar_gvm_connection(config):
    """Verifica la conexión TLS a GVM"""
    try:
        username = config.get('user', 'admin')
        password = config.get('password', '')
        
        if not password:
            return {'status': 'warning', 'message': 'Password no configurado'}
        
        connection = TLSConnection(hostname="127.0.0.1", port=GVM_PORT)
        
        with Gmp(connection=connection) as gmp:
            response = gmp.get_version()
            root = ET.fromstring(response)
            status = root.get("status")
            
            if status == "200":
                version = root.find("version").text
                return {'status': 'ok', 'message': f'GVM conectado (v{version})'}
            else:
                return {'status': 'error', 'message': f'GVM respondió con status: {status}'}
    except Exception as e:
        return {'status': 'error', 'message': f'Error de conexión GVM: {str(e)}'}

def verificar_actualizacion_imagen():
    """Verifica si hay actualizaciones disponibles para la imagen Docker"""
    try:
        result = subprocess.run(
            ['docker', 'pull', 'immauss/openvas:latest', '--dry-run'],
            capture_output=True,
            text=True,
            timeout=60
        )
        
        # Si hay output, significa que hay actualización disponible
        if 'Image is up to date' in result.stdout or 'up to date' in result.stdout.lower():
            return {'status': 'ok', 'message': 'Imagen actualizada'}
        else:
            return {'status': 'warning', 'message': 'Actualización de imagen disponible'}
    except subprocess.TimeoutExpired:
        return {'status': 'warning', 'message': 'Timeout al verificar actualización'}
    except Exception as e:
        return {'status': 'warning', 'message': f'Error al verificar actualización: {str(e)}'}

def formatear_mensaje_alerta(tipo, detalles, timestamp):
    """Formatea un mensaje de alerta para Telegram"""
    emojis = {
        'container': '🐳',
        'docker': '🔧',
        'gvmd': '🛡️',
        'gsad': '🌐',
        'gvm_connection': '🔌',
        'image': '🔄'
    }
    
    emoji = emojis.get(tipo, '⚠️')
    
    mensaje = f"{emoji} <b>ALERTA: {tipo.upper().replace('_', ' ')}</b>\n\n"
    mensaje += f"<b>Estado:</b> {detalles['message']}\n"
    mensaje += f"<b>Hora:</b> {timestamp}\n"
    
    # Añadir acciones recomendadas según el tipo
    acciones = {
        'container': "Acción: Verificar con 'docker ps -a' y 'docker start openvas'",
        'docker': "Acción: Verificar con 'systemctl status docker' y 'systemctl start docker'",
        'gvmd': "Acción: Verificar logs del contenedor con 'docker logs openvas'",
        'gsad': "Acción: Verificar que el puerto 9392 esté accesible",
        'gvm_connection': "Acción: Verificar credenciales y que GVM esté funcionando",
        'image': "Acción: Considerar actualizar con 'docker pull immauss/openvas:latest'"
    }
    
    if tipo in acciones:
        mensaje += f"\n<b>{acciones[tipo]}</b>"
    
    return mensaje

def ejecutar_verificaciones(config):
    """Ejecuta todas las verificaciones y retorna los resultados"""
    resultados = {
        'timestamp': datetime.datetime.now().isoformat(),
        'checks': {},
        'status': 'ok',
        'alerts_sent': []
    }
    
    # Verificar contenedor
    contenedor = verificar_contenedor()
    resultados['checks']['container'] = contenedor['status']
    escribir_log(f"Contenedor: {contenedor['message']}")
    if contenedor['status'] != 'ok':
        resultados['status'] = 'error'
    
    # Verificar Docker daemon
    docker = verificar_docker_daemon()
    resultados['checks']['docker'] = docker['status']
    escribir_log(f"Docker daemon: {docker['message']}")
    if docker['status'] != 'ok':
        resultados['status'] = 'error'
    
    # Verificar puerto GVM (gvmd)
    gvmd_port = verificar_puerto('127.0.0.1', GVM_PORT)
    resultados['checks']['gvmd'] = gvmd_port['status']
    escribir_log(f"Puerto GVM (9390): {gvmd_port['message']}")
    if gvmd_port['status'] != 'ok':
        resultados['status'] = 'error'
    
    # Verificar puerto GSAD (web UI)
    gsad_port = verificar_puerto('127.0.0.1', GSAD_PORT)
    resultados['checks']['gsad'] = gsad_port['status']
    escribir_log(f"Puerto GSAD (9392): {gsad_port['message']}")
    if gsad_port['status'] != 'ok':
        resultados['status'] = 'warning' if resultados['status'] == 'ok' else resultados['status']
    
    # Verificar conexión GVM
    gvm_conn = verificar_gvm_connection(config)
    resultados['checks']['gvm_connection'] = gvm_conn['status']
    escribir_log(f"Conexión GVM: {gvm_conn['message']}")
    if gvm_conn['status'] != 'ok':
        resultados['status'] = 'error' if gvm_conn['status'] == 'error' else resultados['status']
    
    # Verificar actualización de imagen
    imagen = verificar_actualizacion_imagen()
    resultados['checks']['image'] = imagen['status']
    escribir_log(f"Imagen Docker: {imagen['message']}")
    if imagen['status'] == 'warning':
        resultados['status'] = 'warning' if resultados['status'] == 'ok' else resultados['status']
    
    return resultados

def enviar_alertas(resultados, config):
    """Envía alertas por Telegram según los resultados"""
    monitoring_config = config.get('monitoring', {})
    
    if not monitoring_config.get('enabled', False):
        return
    
    telegram_config = monitoring_config.get('telegram', {})
    bot_token = telegram_config.get('bot_token')
    chat_id = telegram_config.get('chat_id')
    
    if not bot_token or not chat_id:
        escribir_log("Telegram no configurado (falta bot_token o chat_id)", 'WARNING')
        return
    
    timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    # Verificar y enviar alertas según configuración
    checks = resultados['checks']
    
    # Alerta de contenedor
    if monitoring_config.get('alert_on_container_down', True) and checks.get('container') != 'ok':
        if puede_enviar_alerta('container', config):
            mensaje = formatear_mensaje_alerta('container', 
                {'message': 'Contenedor no está corriendo'}, timestamp)
            if enviar_telegram(mensaje, bot_token, chat_id):
                registrar_alerta_enviada('container')
                resultados['alerts_sent'].append('container')
                escribir_log("Alerta de contenedor enviada por Telegram")
    
    # Alerta de Docker daemon
    if monitoring_config.get('alert_on_docker_down', True) and checks.get('docker') != 'ok':
        if puede_enviar_alerta('docker', config):
            mensaje = formatear_mensaje_alerta('docker',
                {'message': 'Docker daemon no está activo'}, timestamp)
            if enviar_telegram(mensaje, bot_token, chat_id):
                registrar_alerta_enviada('docker')
                resultados['alerts_sent'].append('docker')
                escribir_log("Alerta de Docker daemon enviada por Telegram")
    
    # Alerta de GVM
    if monitoring_config.get('alert_on_gvm_down', True):
        if checks.get('gvmd') != 'ok' or checks.get('gvm_connection') != 'ok':
            if puede_enviar_alerta('gvm', config):
                mensaje = formatear_mensaje_alerta('gvm_connection',
                    {'message': 'GVM no responde correctamente'}, timestamp)
                if enviar_telegram(mensaje, bot_token, chat_id):
                    registrar_alerta_enviada('gvm')
                    resultados['alerts_sent'].append('gvm')
                    escribir_log("Alerta de GVM enviada por Telegram")
    
    # Alerta de actualización de imagen
    if monitoring_config.get('alert_on_image_update', True) and checks.get('image') == 'warning':
        if puede_enviar_alerta('image', config):
            mensaje = formatear_mensaje_alerta('image',
                {'message': 'Actualización de imagen disponible'}, timestamp)
            if enviar_telegram(mensaje, bot_token, chat_id):
                registrar_alerta_enviada('image')
                resultados['alerts_sent'].append('image')
                escribir_log("Alerta de actualización de imagen enviada por Telegram")

def main():
    """Función principal"""
    escribir_log("Iniciando verificación de monitoreo")
    
    # Leer configuración
    config = leer_configuracion()
    
    # Verificar si el monitoreo está habilitado
    monitoring_config = config.get('monitoring', {})
    if not monitoring_config.get('enabled', False):
        escribir_log("Monitoreo deshabilitado en configuración", 'INFO')
        return
    
    # Ejecutar verificaciones
    resultados = ejecutar_verificaciones(config)
    
    # Enviar alertas si es necesario
    enviar_alertas(resultados, config)
    
    # Guardar resultado en log estructurado
    os.makedirs(LOG_DIR, exist_ok=True)
    log_entry = {
        'timestamp': resultados['timestamp'],
        'status': resultados['status'],
        'checks': resultados['checks'],
        'alerts_sent': len(resultados['alerts_sent']) > 0
    }
    
    with open(LOG_FILE, 'a') as f:
        f.write(json.dumps(log_entry) + '\n')
    
    escribir_log(f"Verificación completada. Estado: {resultados['status']}")
    
    # Exit code según el estado
    if resultados['status'] == 'error':
        sys.exit(1)
    elif resultados['status'] == 'warning':
        sys.exit(0)
    else:
        sys.exit(0)

if __name__ == '__main__':
    main()

