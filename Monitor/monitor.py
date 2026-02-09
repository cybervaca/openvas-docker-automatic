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
try:
    import socks  # PySocks para soporte SOCKS5
except ImportError:
    socks = None
from gvm.connections import TLSConnection
from gvm.protocols.gmp import Gmp
import xml.etree.ElementTree as ET

# Configuración
CONFIG_PATH = '/opt/gvm/Config/config.json'
MONITOR_CONFIG_PATH = '/opt/gvm/Monitor/config.json'
LOG_DIR = '/opt/gvm/logs/monitoring'
LOG_FILE = f'{LOG_DIR}/monitor.log'
ALERT_COOLDOWN_FILE = f'{LOG_DIR}/alert_cooldown.json'
CONTAINER_NAME = 'openvas'
GVM_PORT = 9390
GSAD_PORT = 9392

# Variable global para el proceso del túnel SSH
ssh_tunnel_process = None

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

def leer_configuracion_monitor():
    """Lee la configuración específica del monitor desde Monitor/config.json"""
    try:
        if os.path.exists(MONITOR_CONFIG_PATH):
            with open(MONITOR_CONFIG_PATH, 'r') as archivo:
                return json.load(archivo)
        return {}
    except Exception as e:
        escribir_log(f"Error al leer configuración del monitor: {e}", 'WARNING')
        return {}

def escribir_log(mensaje, nivel='INFO'):
    """Escribe un mensaje en el log estructurado"""
    timestamp = datetime.datetime.now().isoformat()
    log_entry = {
        'timestamp': timestamp,
        'level': nivel,
        'message': mensaje
    }
    
    # Asegurar que el directorio existe con permisos correctos
    try:
        os.makedirs(LOG_DIR, exist_ok=True, mode=0o755)
        # Intentar escribir el log
        with open(LOG_FILE, 'a') as f:
            f.write(json.dumps(log_entry) + '\n')
    except PermissionError:
        # Si no hay permisos, solo imprimir (útil para testing)
        pass
    except Exception as e:
        # Otros errores, solo imprimir
        pass
    
    print(f"[{timestamp}] [{nivel}] {mensaje}")

def crear_tunel_ssh_socks(config_monitor):
    """Crea un túnel SSH SOCKS bajo demanda"""
    global ssh_tunnel_process
    
    ssh_config = config_monitor.get('ssh_tunnel', {})
    
    if not ssh_config.get('enabled', False):
        return None
    
    # Verificar si el túnel ya existe y está activo
    if ssh_tunnel_process and ssh_tunnel_process.poll() is None:
        # Verificar que el puerto SOCKS esté realmente escuchando
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)
            result = sock.connect_ex((ssh_config.get('socks_host', '127.0.0.1'), 
                                     ssh_config.get('socks_port', 1080)))
            sock.close()
            if result == 0:
                escribir_log("Túnel SSH SOCKS ya está activo", 'INFO')
                return True
        except:
            pass
    
    # Crear nuevo túnel
    vps_host = ssh_config.get('vps_host')
    vps_port = ssh_config.get('vps_port', 22)
    vps_user = ssh_config.get('vps_user')
    ssh_key = ssh_config.get('ssh_key_path')
    socks_port = ssh_config.get('socks_port', 1080)
    socks_host = ssh_config.get('socks_host', '127.0.0.1')
    
    if not vps_host or not vps_user:
        escribir_log("Configuración SSH incompleta (falta vps_host o vps_user)", 'ERROR')
        return False
    
    # Construir comando SSH
    ssh_cmd = [
        'ssh',
        '-N',  # No ejecutar comando remoto
        '-D', f'{socks_host}:{socks_port}',  # SOCKS proxy
        '-o', 'StrictHostKeyChecking=no',  # No verificar host key (opcional, puede cambiarse)
        '-o', 'UserKnownHostsFile=/dev/null',
        '-o', 'LogLevel=ERROR',  # Reducir output
        '-o', 'BatchMode=yes',  # No pedir contraseña
        '-f',  # Background
    ]
    
    # Añadir clave SSH solo si está especificada y existe
    # Si no se especifica, SSH usará la clave por defecto del usuario (normalmente ~/.ssh/id_rsa)
    if ssh_key:
        if os.path.exists(ssh_key):
            ssh_cmd.extend(['-i', ssh_key])
            # Asegurar permisos correctos de la clave
            os.chmod(ssh_key, 0o600)
        else:
            escribir_log(f"Clave SSH especificada pero no encontrada en {ssh_key}, usando clave por defecto", 'WARNING')
    else:
        escribir_log("Usando clave SSH por defecto del usuario (desde ~/.ssh/)", 'INFO')
    
    ssh_cmd.append(f'{vps_user}@{vps_host}')
    
    # Si el puerto no es 22, añadirlo
    if vps_port != 22:
        ssh_cmd.insert(-1, '-p')
        ssh_cmd.insert(-1, str(vps_port))
    
    try:
        escribir_log(f"Creando túnel SSH SOCKS a {vps_user}@{vps_host}:{vps_port}", 'INFO')
        process = subprocess.Popen(
            ssh_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.DEVNULL
        )
        
        # Esperar un momento para verificar que se creó correctamente
        import time
        time.sleep(2)
        
        if process.poll() is None:
            ssh_tunnel_process = process
            escribir_log(f"Túnel SSH SOCKS creado en {socks_host}:{socks_port}", 'INFO')
            return True
        else:
            stdout, stderr = process.communicate()
            error_msg = stderr.decode('utf-8', errors='ignore')
            escribir_log(f"Error al crear túnel SSH: {error_msg}", 'ERROR')
            return False
            
    except Exception as e:
        escribir_log(f"Error al crear túnel SSH: {e}", 'ERROR')
        return False

def cerrar_tunel_ssh():
    """Cierra el túnel SSH si está activo"""
    global ssh_tunnel_process
    
    if ssh_tunnel_process and ssh_tunnel_process.poll() is None:
        try:
            ssh_tunnel_process.terminate()
            ssh_tunnel_process.wait(timeout=5)
            escribir_log("Túnel SSH SOCKS cerrado", 'INFO')
        except:
            try:
                ssh_tunnel_process.kill()
            except:
                pass
        finally:
            ssh_tunnel_process = None

def enviar_telegram(mensaje, bot_token, chat_id, config_monitor=None):
    """Envía un mensaje por Telegram, usando túnel SOCKS si está configurado"""
    # Asegurar que chat_id sea string (puede venir como número del JSON)
    chat_id = str(chat_id)
    
    # Leer configuración del monitor si no se proporciona
    if config_monitor is None:
        config_monitor = leer_configuracion_monitor()
    
    # Crear túnel SSH SOCKS si está configurado
    ssh_config = config_monitor.get('ssh_tunnel', {})
    usar_proxy = ssh_config.get('enabled', False)
    
    proxies = None
    if usar_proxy:
        if socks is None:
            escribir_log("PySocks no está instalado. Instala con: pip install PySocks", 'ERROR')
            return False
        if crear_tunel_ssh_socks(config_monitor):
            socks_host = ssh_config.get('socks_host', '127.0.0.1')
            socks_port = ssh_config.get('socks_port', 1080)
            proxies = {
                'http': f'socks5://{socks_host}:{socks_port}',
                'https': f'socks5://{socks_host}:{socks_port}'
            }
            escribir_log(f"Usando proxy SOCKS {socks_host}:{socks_port} para Telegram", 'INFO')
    
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        'chat_id': chat_id,
        'text': mensaje,
        'parse_mode': 'HTML'
    }
    
    try:
        response = requests.post(url, json=payload, proxies=proxies, timeout=30)
        response.raise_for_status()
        
        # Cerrar túnel después de enviar (bajo demanda)
        if usar_proxy:
            cerrar_tunel_ssh()
        
        return True
    except requests.exceptions.HTTPError as e:
        error_detail = ""
        try:
            error_json = response.json()
            error_detail = f" - {error_json.get('description', '')}"
        except:
            pass
        escribir_log(f"Error HTTP al enviar mensaje a Telegram: {e}{error_detail}", 'ERROR')
        if usar_proxy:
            cerrar_tunel_ssh()
        return False
    except requests.exceptions.RequestException as e:
        escribir_log(f"Error al enviar mensaje a Telegram: {e}", 'ERROR')
        if usar_proxy:
            cerrar_tunel_ssh()
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
    
    # Asegurar que chat_id sea string
    chat_id = str(chat_id)
    
    # Leer configuración del monitor para el túnel SSH
    config_monitor = leer_configuracion_monitor()
    
    timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    # Verificar y enviar alertas según configuración
    checks = resultados['checks']
    
    # Alerta de contenedor
    if monitoring_config.get('alert_on_container_down', True) and checks.get('container') != 'ok':
        if puede_enviar_alerta('container', config):
            mensaje = formatear_mensaje_alerta('container', 
                {'message': 'Contenedor no está corriendo'}, timestamp)
            if enviar_telegram(mensaje, bot_token, chat_id, config_monitor):
                registrar_alerta_enviada('container')
                resultados['alerts_sent'].append('container')
                escribir_log("Alerta de contenedor enviada por Telegram")
    
    # Alerta de Docker daemon
    if monitoring_config.get('alert_on_docker_down', True) and checks.get('docker') != 'ok':
        if puede_enviar_alerta('docker', config):
            mensaje = formatear_mensaje_alerta('docker',
                {'message': 'Docker daemon no está activo'}, timestamp)
            if enviar_telegram(mensaje, bot_token, chat_id, config_monitor):
                registrar_alerta_enviada('docker')
                resultados['alerts_sent'].append('docker')
                escribir_log("Alerta de Docker daemon enviada por Telegram")
    
    # Alerta de GVM
    if monitoring_config.get('alert_on_gvm_down', True):
        if checks.get('gvmd') != 'ok' or checks.get('gvm_connection') != 'ok':
            if puede_enviar_alerta('gvm', config):
                mensaje = formatear_mensaje_alerta('gvm_connection',
                    {'message': 'GVM no responde correctamente'}, timestamp)
                if enviar_telegram(mensaje, bot_token, chat_id, config_monitor):
                    registrar_alerta_enviada('gvm')
                    resultados['alerts_sent'].append('gvm')
                    escribir_log("Alerta de GVM enviada por Telegram")
    
    # Alerta de actualización de imagen
    if monitoring_config.get('alert_on_image_update', True) and checks.get('image') == 'warning':
        if puede_enviar_alerta('image', config):
            mensaje = formatear_mensaje_alerta('image',
                {'message': 'Actualización de imagen disponible'}, timestamp)
            if enviar_telegram(mensaje, bot_token, chat_id, config_monitor):
                registrar_alerta_enviada('image')
                resultados['alerts_sent'].append('image')
                escribir_log("Alerta de actualización de imagen enviada por Telegram")

def main():
    """Función principal"""
    try:
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
    finally:
        # Asegurar que el túnel SSH se cierre al finalizar
        cerrar_tunel_ssh()

if __name__ == '__main__':
    main()

