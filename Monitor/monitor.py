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
        raise FileNotFoundError(f"El archivo '{CONFIG_PATH}' no se encontró.")
    except json.JSONDecodeError as e:
        raise ValueError(f"Error al decodificar el archivo JSON: {e}")
    except Exception as e:
        raise Exception(f"Error al leer configuración: {e}")

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
    # Si no se especifica o es null/None, SSH usará la clave por defecto del usuario (normalmente ~/.ssh/id_rsa)
    if ssh_key and ssh_key != 'null' and ssh_key != 'None' and ssh_key.lower() != 'none':
        if os.path.exists(str(ssh_key)):
            ssh_cmd.extend(['-i', str(ssh_key)])
            # Asegurar permisos correctos de la clave
            os.chmod(str(ssh_key), 0o600)
        else:
            escribir_log(f"Clave SSH especificada pero no encontrada en {ssh_key}, usando clave por defecto", 'WARNING')
    # Si ssh_key es None, null, o no está especificado, no añadir -i (usar clave por defecto)
    
    ssh_cmd.append(f'{vps_user}@{vps_host}')
    
    # Si el puerto no es 22, añadirlo
    if vps_port != 22:
        ssh_cmd.insert(-1, '-p')
        ssh_cmd.insert(-1, str(vps_port))
    
    try:
        escribir_log(f"Creando túnel SSH SOCKS a {vps_user}@{vps_host}:{vps_port}", 'INFO')
        
        # Crear el túnel en background
        process = subprocess.Popen(
            ssh_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.DEVNULL
        )
        
        # Esperar y verificar que el túnel esté realmente escuchando
        import time
        max_attempts = 10
        for attempt in range(max_attempts):
            time.sleep(0.5)
            # Verificar que el proceso sigue corriendo
            if process.poll() is not None:
                stdout, stderr = process.communicate()
                error_msg = stderr.decode('utf-8', errors='ignore')
                if error_msg:
                    escribir_log(f"Error al crear túnel SSH: {error_msg}", 'ERROR')
                else:
                    escribir_log(f"Proceso SSH terminó inesperadamente (código: {process.returncode})", 'ERROR')
                return False
            
            # Verificar que el puerto SOCKS esté escuchando
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(1)
                result = sock.connect_ex((socks_host, socks_port))
                sock.close()
                if result == 0:
                    ssh_tunnel_process = process
                    escribir_log(f"Túnel SSH SOCKS creado y escuchando en {socks_host}:{socks_port}", 'INFO')
                    return True
            except Exception:
                pass
        
        # Si llegamos aquí, el túnel no se estableció correctamente
        try:
            process.terminate()
            process.wait(timeout=2)
        except:
            try:
                process.kill()
            except:
                pass
        escribir_log(f"Timeout: El túnel SSH no está escuchando en {socks_host}:{socks_port} después de {max_attempts * 0.5} segundos", 'ERROR')
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

def dividir_mensaje(mensaje, max_length=4000):
    """Divide un mensaje largo en partes más pequeñas"""
    # Telegram tiene límite de 4096 caracteres, usamos 4000 para margen
    if len(mensaje) <= max_length:
        return [mensaje]
    
    partes = []
    lineas = mensaje.split('\n')
    parte_actual = ""
    
    for linea in lineas:
        # Si añadir esta línea excede el límite, guardar parte actual y empezar nueva
        if len(parte_actual) + len(linea) + 1 > max_length:
            if parte_actual:
                partes.append(parte_actual)
            parte_actual = linea + '\n'
        else:
            parte_actual += linea + '\n'
    
    # Añadir la última parte
    if parte_actual:
        partes.append(parte_actual)
    
    return partes

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
    
    # Dividir mensaje si es muy largo
    partes = dividir_mensaje(mensaje, max_length=4000)
    total_partes = len(partes)
    
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    
    # Enviar cada parte
    for i, parte in enumerate(partes):
        # Añadir indicador de parte si hay múltiples partes
        if total_partes > 1:
            parte_con_numero = f"📄 <i>Parte {i+1}/{total_partes}</i>\n\n{parte}"
        else:
            parte_con_numero = parte
        
        payload = {
            'chat_id': chat_id,
            'text': parte_con_numero,
            'parse_mode': 'HTML'
        }
        
        try:
            response = requests.post(url, json=payload, proxies=proxies, timeout=30)
            response.raise_for_status()
            
            if total_partes > 1:
                escribir_log(f"Mensaje parte {i+1}/{total_partes} enviada correctamente", 'INFO')
            
            # Pequeña pausa entre mensajes para evitar rate limiting
            if i < total_partes - 1:
                import time
                time.sleep(0.5)
                
        except requests.exceptions.HTTPError as e:
            error_detail = ""
            try:
                error_json = response.json()
                error_detail = f" - {error_json.get('description', '')}"
            except:
                pass
            escribir_log(f"Error HTTP al enviar mensaje parte {i+1}/{total_partes} a Telegram: {e}{error_detail}", 'ERROR')
            if usar_proxy:
                cerrar_tunel_ssh()
            return False
        except requests.exceptions.RequestException as e:
            escribir_log(f"Error al enviar mensaje parte {i+1}/{total_partes} a Telegram: {e}", 'ERROR')
            if usar_proxy:
                cerrar_tunel_ssh()
            return False
    
    # Cerrar túnel después de enviar todas las partes (bajo demanda)
    if usar_proxy:
        cerrar_tunel_ssh()
    
    if total_partes > 1:
        escribir_log(f"Mensaje completo enviado en {total_partes} partes", 'INFO')
    
    return True

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

def formatear_mensaje_alerta_completo(resultados, config, timestamp):
    """Formatea un mensaje completo con todas las alertas agrupadas"""
    pais = config.get('pais', 'N/A')
    site = config.get('site', 'N/A')
    region = config.get('region', 'N/A')
    
    # Determinar nivel de alerta general
    checks = resultados['checks']
    tiene_errores = any(status == 'error' for status in checks.values())
    tiene_warnings = any(status == 'warning' for status in checks.values())
    
    if tiene_errores:
        emoji_principal = '🔴'
        titulo = 'ALERTA CRÍTICA'
    elif tiene_warnings:
        emoji_principal = '🟡'
        titulo = 'ADVERTENCIA'
    else:
        emoji_principal = '✅'
        titulo = 'ESTADO OK'
    
    # Encabezado del mensaje
    mensaje = f"{emoji_principal} <b>{titulo}: OpenVAS Monitor</b>\n\n"
    mensaje += f"<b>País:</b> {pais}\n"
    mensaje += f"<b>Site:</b> {site}\n"
    mensaje += f"<b>Región:</b> {region}\n"
    mensaje += f"<b>Hora:</b> {timestamp}\n"
    mensaje += "\n" + "="*40 + "\n\n"
    
    # Emojis para cada tipo de check
    emojis = {
        'container': '🐳',
        'docker': '🔧',
        'gvmd': '🛡️',
        'gsad': '🌐',
        'gvm_connection': '🔌'
    }
    
    # Nombres descriptivos
    nombres = {
        'container': 'Contenedor Docker',
        'docker': 'Docker Daemon',
        'gvmd': 'GVM (Puerto 9390)',
        'gsad': 'GSAD Web UI (Puerto 9392)',
        'gvm_connection': 'Conexión GVM TLS'
    }
    
    # Mensajes de estado
    mensajes_estado = {
        'ok': '✅ OK',
        'error': '❌ ERROR',
        'warning': '⚠️ WARNING'
    }
    
    # Agrupar alertas por tipo
    alertas = []
    warnings = []
    ok_items = []
    
    for check_name, status in checks.items():
        emoji = emojis.get(check_name, '•')
        nombre = nombres.get(check_name, check_name)
        estado_emoji = mensajes_estado.get(status, status)
        
        item = f"{emoji} <b>{nombre}:</b> {estado_emoji}"
        
        if status == 'error':
            alertas.append(item)
        elif status == 'warning':
            warnings.append(item)
        else:
            ok_items.append(item)
    
    # Construir mensaje agrupado
    if alertas:
        mensaje += "<b>🔴 PROBLEMAS CRÍTICOS:</b>\n"
        for alerta in alertas:
            mensaje += f"{alerta}\n"
        mensaje += "\n"
    
    if warnings:
        mensaje += "<b>🟡 ADVERTENCIAS:</b>\n"
        for warning in warnings:
            mensaje += f"{warning}\n"
        mensaje += "\n"
    
    if ok_items:
        mensaje += "<b>✅ ESTADO OK:</b>\n"
        for ok_item in ok_items:
            mensaje += f"{ok_item}\n"
        mensaje += "\n"
    
    # Añadir acciones recomendadas si hay problemas
    if alertas:
        mensaje += "\n" + "="*40 + "\n"
        mensaje += "<b>ACCIONES RECOMENDADAS:</b>\n\n"
        
        acciones = {
            'container': "🐳 Contenedor: Verificar con 'docker ps -a' y 'docker start openvas'",
            'docker': "🔧 Docker: Verificar con 'systemctl status docker' y 'systemctl start docker'",
            'gvmd': "🛡️ GVM: Verificar logs con 'docker logs openvas'",
            'gsad': "🌐 GSAD: Verificar que el puerto 9392 esté accesible",
            'gvm_connection': "🔌 Conexión: Verificar credenciales y que GVM esté funcionando"
        }
        
        for check_name, status in checks.items():
            if status == 'error' and check_name in acciones:
                mensaje += f"{acciones[check_name]}\n"
    
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
    
    return resultados

def enviar_alertas(resultados, config):
    """Envía alertas por Telegram según los resultados (mensaje único agrupado)"""
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
    
    # Verificar si hay algo que reportar
    checks = resultados['checks']
    
    # Determinar si hay problemas según configuración
    tiene_problemas = False
    
    # Verificar contenedor
    if monitoring_config.get('alert_on_container_down', True) and checks.get('container') != 'ok':
        tiene_problemas = True
    
    # Verificar Docker daemon
    if monitoring_config.get('alert_on_docker_down', True) and checks.get('docker') != 'ok':
        tiene_problemas = True
    
    # Verificar GVM
    if monitoring_config.get('alert_on_gvm_down', True):
        if checks.get('gvmd') != 'ok' or checks.get('gvm_connection') != 'ok':
            tiene_problemas = True
    
    # Enviar mensaje completo solo si hay problemas o si se quiere reportar estado OK
    # Por ahora solo enviamos si hay problemas (para evitar spam cuando todo está OK)
    if tiene_problemas:
        # Verificar cooldown (usamos 'monitoring' como tipo único para el mensaje completo)
        puede_enviar = puede_enviar_alerta('monitoring', config)
        forzar_envio = monitoring_config.get('force_send', False)  # Opción para forzar envío
        
        escribir_log(f"Verificación de cooldown: puede_enviar={puede_enviar}, tiene_problemas={tiene_problemas}, forzar={forzar_envio}", 'DEBUG')
        
        if puede_enviar or forzar_envio:
            if forzar_envio and not puede_enviar:
                escribir_log("Forzando envío de alerta (ignorando cooldown)", 'WARNING')
            
            mensaje = formatear_mensaje_alerta_completo(resultados, config, timestamp)
            escribir_log(f"Preparando envío de alerta (tamaño mensaje: {len(mensaje)} caracteres)", 'INFO')
            if enviar_telegram(mensaje, bot_token, chat_id, config_monitor):
                registrar_alerta_enviada('monitoring')
                resultados['alerts_sent'].append('monitoring')
                escribir_log("Alerta completa enviada por Telegram", 'INFO')
            else:
                escribir_log("Error al enviar alerta por Telegram", 'ERROR')
        else:
            cooldown_data = cargar_cooldown()
            if 'monitoring' in cooldown_data:
                ultimo_envio = datetime.datetime.fromisoformat(cooldown_data['monitoring'])
                tiempo_transcurrido = (datetime.datetime.now() - ultimo_envio).total_seconds()
                cooldown_seconds = monitoring_config.get('alert_cooldown', 3600)
                tiempo_restante = cooldown_seconds - tiempo_transcurrido
                escribir_log(f"Cooldown activo. Tiempo restante: {int(tiempo_restante)} segundos ({int(tiempo_restante/60)} minutos)", 'INFO')
            else:
                escribir_log("No se puede enviar alerta (cooldown activo pero sin datos)", 'WARNING')
    else:
        escribir_log("No hay problemas que reportar, no se envía alerta", 'INFO')

def main():
    """Función principal"""
    try:
        escribir_log("Iniciando verificación de monitoreo")
        
        # Leer configuración
        try:
            config = leer_configuracion()
        except PermissionError as e:
            escribir_log(f"ERROR: No se puede leer configuración por permisos: {e}", 'ERROR')
            print(f"ERROR: Permisos insuficientes para leer {CONFIG_PATH}")
            print(f"Verifica que el usuario tenga permisos de lectura en el archivo")
            sys.exit(1)
        except Exception as e:
            escribir_log(f"ERROR: Error al leer configuración: {e}", 'ERROR')
            sys.exit(1)
        
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
        try:
            os.makedirs(LOG_DIR, exist_ok=True, mode=0o755)
            log_entry = {
                'timestamp': resultados['timestamp'],
                'status': resultados['status'],
                'checks': resultados['checks'],
                'alerts_sent': len(resultados['alerts_sent']) > 0
            }
            
            with open(LOG_FILE, 'a') as f:
                f.write(json.dumps(log_entry) + '\n')
        except PermissionError as e:
            escribir_log(f"ADVERTENCIA: No se puede escribir log por permisos: {e}", 'WARNING')
            print(f"ADVERTENCIA: Permisos insuficientes para escribir en {LOG_FILE}")
        except Exception as e:
            escribir_log(f"ADVERTENCIA: Error al escribir log: {e}", 'WARNING')
        
        escribir_log(f"Verificación completada. Estado: {resultados['status']}")
        
        # Siempre salir con código 0 (éxito) porque detectar problemas es la función normal del servicio
        # El servicio solo debe fallar si hay errores en el propio script (configuración, permisos, etc.)
        # No debe fallar por detectar que el contenedor está caído o hay problemas - eso es su trabajo
        sys.exit(0)
    finally:
        # Asegurar que el túnel SSH se cierre al finalizar
        cerrar_tunel_ssh()

if __name__ == '__main__':
    main()

