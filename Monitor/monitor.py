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
import shutil
import subprocess
import datetime
import socket
import requests
import sys
try:
    import socks  # PySocks para soporte SOCKS5
except ImportError:
    socks = None
from gvm.protocols.gmp import Gmp
import xml.etree.ElementTree as ET

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
from gvm_connect import (
    verificar_transporte_gvm,
    tcp_port_open,
    DEFAULT_SOCKET_CANDIDATES,
    connect_gvm,
)

# Configuración
CONFIG_PATH = '/opt/gvm/Config/config.json'
MONITOR_CONFIG_PATH = '/opt/gvm/Monitor/config.json'
LOG_DIR = '/opt/gvm/logs/monitoring'
LOG_FILE = f'{LOG_DIR}/monitor.log'
ALERT_COOLDOWN_FILE = f'{LOG_DIR}/alert_cooldown.json'
AUTO_UPDATE_FEEDS_AFTER_DAYS = 15
AUTO_UPDATE_COOLDOWN_SECONDS = 24 * 60 * 60  # 24h
AUTO_UPDATE_COOLDOWN_FILE = f'{LOG_DIR}/auto_update_cooldown.json'
AUTO_UPDATE_COOLDOWN_KEY = 'feeds'
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

def cargar_auto_update_cooldown():
    """Carga el estado de cooldown para auto-update de feeds"""
    if os.path.exists(AUTO_UPDATE_COOLDOWN_FILE):
        try:
            with open(AUTO_UPDATE_COOLDOWN_FILE, 'r') as f:
                return json.load(f)
        except:
            return {}
    return {}

def guardar_auto_update_cooldown(cooldown_data):
    """Guarda el estado de cooldown para auto-update de feeds"""
    os.makedirs(LOG_DIR, exist_ok=True)
    with open(AUTO_UPDATE_COOLDOWN_FILE, 'w') as f:
        json.dump(cooldown_data, f)

def puede_ejecutar_auto_update_feeds():
    """Determina si se puede ejecutar auto-update de feeds (según cooldown)"""
    cooldown_data = cargar_auto_update_cooldown()
    if AUTO_UPDATE_COOLDOWN_KEY not in cooldown_data:
        return True, None

    ultimo_envio = datetime.datetime.fromisoformat(cooldown_data[AUTO_UPDATE_COOLDOWN_KEY])
    tiempo_transcurrido = (datetime.datetime.now() - ultimo_envio).total_seconds()
    restante = AUTO_UPDATE_COOLDOWN_SECONDS - tiempo_transcurrido
    return tiempo_transcurrido >= AUTO_UPDATE_COOLDOWN_SECONDS, max(0, restante)

def registrar_auto_update_feeds():
    """Registra que se ejecutó un auto-update de feeds"""
    cooldown_data = cargar_auto_update_cooldown()
    cooldown_data[AUTO_UPDATE_COOLDOWN_KEY] = datetime.datetime.now().isoformat()
    guardar_auto_update_cooldown(cooldown_data)

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

def verificar_disco(config):
    """Verifica espacio libre en disco (umbral por defecto: 5 GB)"""
    monitoring_config = config.get('monitoring', {})
    min_free_gb = float(monitoring_config.get('disk_min_free_gb', 5))
    paths = monitoring_config.get('disk_paths', ['/'])
    if not isinstance(paths, list) or not paths:
        paths = ['/']

    min_free_bytes = min_free_gb * (1024 ** 3)
    seen_devs = set()
    partitions = []

    for path in paths:
        try:
            if not os.path.exists(path):
                partitions.append({
                    'path': path,
                    'status': 'error',
                    'free_gb': None,
                    'total_gb': None,
                    'message': f'Ruta no existe: {path}'
                })
                continue

            st = os.stat(path)
            if st.st_dev in seen_devs:
                continue
            seen_devs.add(st.st_dev)

            usage = shutil.disk_usage(path)
            free_gb = usage.free / (1024 ** 3)
            total_gb = usage.total / (1024 ** 3)
            entry = {
                'path': path,
                'free_gb': round(free_gb, 2),
                'total_gb': round(total_gb, 2),
            }
            if usage.free <= min_free_bytes:
                entry['status'] = 'error'
                entry['message'] = (
                    f'{path}: {free_gb:.2f} GB libres de {total_gb:.2f} GB '
                    f'(umbral {min_free_gb:g} GB)'
                )
            else:
                entry['status'] = 'ok'
                entry['message'] = f'{path}: {free_gb:.2f} GB libres de {total_gb:.2f} GB'
            partitions.append(entry)
        except Exception as e:
            partitions.append({
                'path': path,
                'status': 'error',
                'free_gb': None,
                'total_gb': None,
                'message': f'Error al verificar {path}: {str(e)}'
            })

    details = {
        'min_free_gb': min_free_gb,
        'partitions': partitions,
        'low': [p for p in partitions if p.get('status') == 'error']
    }

    if any(p.get('status') == 'error' for p in partitions):
        msgs = [p['message'] for p in partitions if p.get('status') == 'error']
        return {'status': 'error', 'message': '; '.join(msgs), 'details': details}

    msgs = [p['message'] for p in partitions]
    return {
        'status': 'ok',
        'message': '; '.join(msgs) if msgs else 'Disco OK',
        'details': details
    }

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

def verificar_gvm_listener(config):
    """
    Comprueba si gvmd es alcanzable por TCP 9390 o por socket Unix.
    No marca error solo porque falte el 9390 si el socket Unix existe.
    """
    host = str(config.get("gvm_host") or "127.0.0.1")
    try:
        port = int(config.get("gvm_port") or GVM_PORT)
    except (TypeError, ValueError):
        port = GVM_PORT

    if tcp_port_open(host, port, timeout=2.0):
        return {"status": "ok", "message": f"Puerto {port} abierto (TLS)"}

    paths = []
    custom = config.get("gvm_socket")
    if custom:
        paths.append(str(custom).strip())
    paths.extend(DEFAULT_SOCKET_CANDIDATES)
    for path in paths:
        if path and os.path.exists(path):
            return {
                "status": "ok",
                "message": f"Puerto {port} cerrado; socket Unix presente: {path}",
            }

    return {
        "status": "error",
        "message": f"Sin listener TLS {host}:{port} ni socket Unix de gvmd",
    }


def verificar_gvm_connection(config):
    """Verifica la conexión GMP a GVM (TLS y/o Unix según config/auto)."""
    try:
        password = config.get("password", "")
        if not password:
            return {"status": "warning", "message": "Password no configurado"}
        return verificar_transporte_gvm(config=config, timeout=30)
    except Exception as e:
        return {"status": "error", "message": f"Error de conexión GVM: {str(e)}"}

FEED_TYPES = ('NVT', 'SCAP', 'CERT', 'GVMD_DATA')


def parse_feed_version_date(version_str):
    """
    Parsea versión de feed a datetime. Acepta:
    - YYYYMMDDTHHMM (p. ej. 20260814T0620, como en la UI)
    - YYYYMMDDHHMM  (p. ej. 202608140620, como a veces devuelve GMP)
    - YYYYMMDD      (p. ej. 20260814)
    Devuelve None si el formato no es válido.
    """
    if not version_str:
        return None
    value = str(version_str).strip()
    if not value:
        return None

    if 'T' in value:
        fecha_str = value.split('T')[0]
    else:
        # Solo dígitos: YYYYMMDD o YYYYMMDDHHMM...
        digits = ''.join(c for c in value if c.isdigit())
        if len(digits) < 8:
            return None
        fecha_str = digits[:8]

    if len(fecha_str) != 8 or not fecha_str.isdigit():
        return None
    try:
        return datetime.datetime.strptime(fecha_str, '%Y%m%d')
    except ValueError:
        return None


def _gmp_response_root(response):
    """Normaliza respuesta GMP a ElementTree root (str o Element)."""
    if response is None:
        return None
    if isinstance(response, str):
        return ET.fromstring(response)
    # ElementTree Element o compatible
    if hasattr(response, 'tag'):
        return response
    if hasattr(response, 'getroot'):
        return response.getroot()
    return ET.fromstring(str(response))


def obtener_feeds_via_gmp(config):
    """
    Obtiene versiones/fechas de feeds vía GMP get_feeds() (misma fuente que la UI).
    Returns:
        dict: { 'NVT': {'fecha': datetime, 'version': str, 'fuente': 'GMP'}, ... }
              Vacío si falla la consulta.
    """
    resultados = {}
    try:
        user = config.get('user', 'admin')
        password = config.get('password', '')
        if not password:
            escribir_log("Feeds GMP: password no configurado", 'WARNING')
            return resultados

        connection = connect_gvm(config=config, timeout=30, probe_timeout=15)
        with Gmp(connection=connection) as gmp:
            gmp.authenticate(user, password)
            response = gmp.get_feeds()

        root = _gmp_response_root(response)
        if root is None:
            escribir_log("Feeds GMP: respuesta vacía", 'WARNING')
            return resultados

        for feed_el in root.findall('.//feed'):
            feed_type = (feed_el.findtext('type') or '').strip().upper()
            version = (feed_el.findtext('version') or '').strip()
            if feed_type not in FEED_TYPES:
                # Algunas respuestas usan name en lugar de type
                name = (feed_el.findtext('name') or '').strip().upper()
                for ft in FEED_TYPES:
                    if ft in name or name == ft:
                        feed_type = ft
                        break
            if feed_type not in FEED_TYPES:
                continue

            fecha = parse_feed_version_date(version)
            if fecha is None:
                escribir_log(
                    f"Feed {feed_type}: GMP version no parseable: {version!r}",
                    'WARNING'
                )
                continue

            resultados[feed_type] = {
                'fecha': fecha,
                'version': version,
                'fuente': 'GMP'
            }
            escribir_log(
                f"Feed {feed_type}: Fecha desde GMP: {fecha.strftime('%Y-%m-%d')} "
                f"(version={version})",
                'INFO'
            )

        return resultados
    except Exception as e:
        escribir_log(f"Feeds GMP: error al consultar get_feeds(): {e}", 'WARNING')
        return resultados


def obtener_fecha_feed_psql_docker(feed_type):
    """
    Fallback: fecha del feed desde tabla info vía docker exec + psql (solo contenedor).
    """
    feed_db_names = {
        'NVT': 'nvt',
        'SCAP': 'scap',
        'CERT': 'cert',
        'GVMD_DATA': 'gvmd_data'
    }
    db_name = feed_db_names.get(feed_type, feed_type.lower())
    queries = [
        f"SELECT value FROM info WHERE name = '{db_name}_version' OR name = '{db_name}_feed_version';",
        f"SELECT value FROM info WHERE name LIKE '%{db_name}%version%' ORDER BY name LIMIT 1;",
    ]

    for query in queries:
        try:
            result = subprocess.run(
                [
                    'docker', 'exec', CONTAINER_NAME,
                    'sudo', '-u', 'postgres',
                    'psql', '-U', 'postgres', '-d', 'gvmd', '-t', '-A', '-c', query
                ],
                capture_output=True,
                text=True,
                timeout=15
            )
            if result.returncode != 0:
                continue
            value = (result.stdout or '').strip()
            if not value or value == '0':
                continue
            fecha = parse_feed_version_date(value)
            if fecha is not None:
                escribir_log(
                    f"Feed {feed_type}: Fecha desde psql (docker): "
                    f"{fecha.strftime('%Y-%m-%d')} (value={value})",
                    'INFO'
                )
                return fecha
        except Exception as e:
            escribir_log(f"Feed {feed_type}: error psql docker: {e}", 'DEBUG')
            continue
    return None


def verificar_feeds(config, feed_stale_days=30):
    """
    Verifica la edad de los feeds OpenVAS.

    Fuente primaria: GMP get_feeds() (como la UI).
    Fallback: psql dentro del contenedor Docker.
    Telegram/alerta warning solo si hay edad CONFIRMADA >= feed_stale_days.
    Feeds sin fecha legible → log WARNING, status ok (no falso positivo).
    """
    fecha_actual = datetime.datetime.now()
    feeds_info = {}
    feeds_stale = []
    feeds_unverified = []

    gmp_feeds = obtener_feeds_via_gmp(config)

    for feed_name in FEED_TYPES:
        escribir_log(f"Verificando feed {feed_name}...", 'INFO')
        fecha_actualizacion = None
        fuente = None
        version = None

        if feed_name in gmp_feeds:
            fecha_actualizacion = gmp_feeds[feed_name]['fecha']
            fuente = gmp_feeds[feed_name]['fuente']
            version = gmp_feeds[feed_name].get('version')
        else:
            fecha_actualizacion = obtener_fecha_feed_psql_docker(feed_name)
            if fecha_actualizacion is not None:
                fuente = 'PostgreSQL (docker)'

        if fecha_actualizacion is not None:
            if fecha_actualizacion.tzinfo is not None:
                fecha_actualizacion = fecha_actualizacion.replace(tzinfo=None)

            dias = (fecha_actual - fecha_actualizacion).days
            escribir_log(
                f"Feed {feed_name}: {dias} días desde última actualización "
                f"(máximo: {feed_stale_days} días, fuente={fuente})",
                'INFO'
            )

            feeds_info[feed_name] = {
                'fecha': fecha_actualizacion.strftime('%Y-%m-%d'),
                'dias': dias,
                'actualizado': dias < feed_stale_days,
                'fuente': fuente,
                'version': version
            }

            if dias >= feed_stale_days:
                escribir_log(
                    f"Feed {feed_name}: DESACTUALIZADO ({dias} días >= {feed_stale_days})",
                    'WARNING'
                )
                feeds_stale.append({
                    'nombre': feed_name,
                    'dias': dias,
                    'fecha': fecha_actualizacion.strftime('%Y-%m-%d')
                })
        else:
            feeds_info[feed_name] = {
                'fecha': 'No disponible',
                'dias': None,
                'actualizado': None,
                'fuente': 'No encontrado'
            }
            feeds_unverified.append(feed_name)
            escribir_log(
                f"Feed {feed_name}: No se pudo obtener fecha (GMP/psql); "
                f"no se alerta por Telegram",
                'WARNING'
            )

    details = {
        'feeds_stale': feeds_stale,
        'feeds_unverified': feeds_unverified,
        'all_feeds': feeds_info,
        'stale_days': feed_stale_days
    }

    if feeds_stale:
        return {
            'status': 'warning',
            'message': f"{len(feeds_stale)} feed(s) desactualizado(s) (>={feed_stale_days} días)",
            'details': details
        }

    if feeds_unverified:
        # Sin edad confirmada: no warning (evita falso positivo Telegram)
        return {
            'status': 'ok',
            'message': (
                f"Feeds sin alerta: {len(feeds_unverified)} sin fecha verificable "
                f"(revisar logs); resto OK"
            ),
            'details': details
        }

    return {
        'status': 'ok',
        'message': f'Todos los feeds actualizados (<{feed_stale_days} días)',
        'details': details
    }


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
        'gvm_connection': '🔌',
        'feeds': '📦',
        'disk': '💾'
    }
    
    # Nombres descriptivos
    nombres = {
        'container': 'Contenedor Docker',
        'docker': 'Docker Daemon',
        'gvmd': 'GVM (Puerto 9390)',
        'gsad': 'GSAD Web UI (Puerto 9392)',
        'gvm_connection': 'Conexión GVM TLS',
        'feeds': 'Feeds de Vulnerabilidades',
        'disk': 'Espacio en Disco'
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
    
    # Añadir información detallada de feeds desactualizados si existe
    if 'feeds_details' in resultados and resultados.get('feeds_details'):
        feeds_details = resultados['feeds_details']
        feeds_stale = feeds_details.get('feeds_stale', [])
        feeds_unverified = feeds_details.get('feeds_unverified', [])
        
        if feeds_stale:
            mensaje += "\n" + "="*40 + "\n"
            mensaje += "<b>📦 FEEDS DESACTUALIZADOS:</b>\n\n"
            for feed in feeds_stale:
                mensaje += f"• <b>{feed['nombre']}:</b> {feed['dias']} días sin actualizar\n"
                mensaje += f"  Última actualización: {feed['fecha']}\n\n"
            
            # Mostrar también el estado de todos los feeds
            all_feeds = feeds_details.get('all_feeds', {})
            if all_feeds:
                mensaje += "<b>Estado de todos los feeds:</b>\n"
                for feed_name, feed_info in all_feeds.items():
                    if feed_info.get('dias') is not None:
                        estado_emoji = "✅" if feed_info.get('actualizado', False) else "⚠️"
                        mensaje += f"{estado_emoji} <b>{feed_name}:</b> {feed_info.get('dias', 'N/A')} días"
                        if feed_info.get('fecha') and feed_info.get('fecha') != 'No disponible':
                            mensaje += f" (Última: {feed_info['fecha']})"
                        fuente = feed_info.get('fuente')
                        if fuente:
                            mensaje += f" [{fuente}]"
                        mensaje += "\n"
                    else:
                        mensaje += (
                            f"❓ <b>{feed_name}:</b> no se pudo verificar "
                            f"({feed_info.get('fecha', 'Desconocido')})\n"
                        )
                mensaje += "\n"

        elif feeds_unverified:
            # Solo aparece si hay otras alertas en el mismo mensaje compuesto
            mensaje += "\n" + "="*40 + "\n"
            mensaje += "<b>📦 FEEDS (sin fecha verificable):</b>\n\n"
            mensaje += (
                "No es desactualización confirmada; falló la lectura GMP/psql.\n"
            )
            for name in feeds_unverified:
                mensaje += f"• <b>{name}</b>\n"
            mensaje += "\n"
    
    # Añadir detalle de espacio en disco si hay problemas
    if 'disk_details' in resultados and resultados.get('disk_details'):
        disk_details = resultados['disk_details']
        low = disk_details.get('low', [])
        if low:
            mensaje += "\n" + "="*40 + "\n"
            mensaje += "<b>💾 ESPACIO EN DISCO BAJO:</b>\n\n"
            min_free = disk_details.get('min_free_gb', 5)
            mensaje += f"Umbral: {min_free:g} GB libres\n\n"
            for part in low:
                path = part.get('path', '?')
                free_gb = part.get('free_gb')
                total_gb = part.get('total_gb')
                if free_gb is not None and total_gb is not None:
                    mensaje += f"• <b>{path}:</b> {free_gb:.2f} GB libres / {total_gb:.2f} GB total\n"
                else:
                    mensaje += f"• <b>{path}:</b> {part.get('message', 'Error')}\n"
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
            'gvm_connection': "🔌 Conexión: Verificar credenciales y que GVM esté funcionando",
            'feeds': "📦 Feeds: Ejecutar '/opt/gvm/Cron/actualiza_gvm.sh'",
            'disk': "💾 Disco: Liberar espacio (logs, imágenes Docker huérfanas, reportes antiguos)"
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
    
    # Verificar listener GVM (TCP 9390 o socket Unix)
    gvmd_port = verificar_gvm_listener(config)
    resultados['checks']['gvmd'] = gvmd_port['status']
    escribir_log(f"Listener GVM: {gvmd_port['message']}")
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
    
    # Verificar feeds (solo si GVM está conectado)
    if gvm_conn['status'] == 'ok':
        monitoring_config = config.get('monitoring', {})
        feed_stale_days = monitoring_config.get('feed_stale_days', 30)
        feeds = verificar_feeds(config, feed_stale_days)
        resultados['checks']['feeds'] = feeds['status']
        resultados['feeds_details'] = feeds.get('details', {})
        escribir_log(f"Feeds: {feeds['message']}")

        # Auto-update de feeds si hay alguno con >= 15 días sin actualizar (umbral fijo).
        all_feeds = resultados.get('feeds_details', {}).get('all_feeds', {}) or {}
        max_days = None
        for feed_info in all_feeds.values():
            dias = feed_info.get('dias')
            if dias is not None:
                max_days = dias if max_days is None else max(max_days, dias)

        resultados['auto_update_feeds'] = {
            'ran': False,
            'status': 'skipped',
            'reason': None,
            'max_days': max_days
        }

        if max_days is not None and max_days >= AUTO_UPDATE_FEEDS_AFTER_DAYS:
            puede_ejecutar, restante = puede_ejecutar_auto_update_feeds()

            if puede_ejecutar:
                escribir_log(
                    f"Auto-update feeds: max_days={max_days} >= {AUTO_UPDATE_FEEDS_AFTER_DAYS}. Ejecutando Cron/actualiza_gvm.sh...",
                    'INFO'
                )
                try:
                    proc = subprocess.run(
                        ['/bin/bash', '/opt/gvm/Cron/actualiza_gvm.sh'],
                        capture_output=True,
                        text=True,
                        timeout=3600
                    )

                    registrar_auto_update_feeds()
                    resultados['auto_update_feeds']['ran'] = True

                    if proc.returncode == 0:
                        resultados['auto_update_feeds']['status'] = 'ok'
                        resultados['auto_update_feeds']['reason'] = 'Actualización realizada'
                        escribir_log("Auto-update feeds: OK", 'INFO')
                    else:
                        resultados['auto_update_feeds']['status'] = 'error'
                        resultados['auto_update_feeds']['reason'] = f"exit code {proc.returncode}"
                        escribir_log(f"Auto-update feeds: ERROR (exit code {proc.returncode})", 'ERROR')

                        stderr = (proc.stderr or '').strip()
                        if stderr:
                            escribir_log(f"Auto-update feeds stderr (head): {stderr[:500]}", 'ERROR')
                except subprocess.TimeoutExpired:
                    registrar_auto_update_feeds()
                    resultados['auto_update_feeds']['ran'] = True
                    resultados['auto_update_feeds']['status'] = 'error'
                    resultados['auto_update_feeds']['reason'] = 'timeout'
                    escribir_log("Auto-update feeds: ERROR (timeout ejecutando actualiza_gvm.sh)", 'ERROR')
                except Exception as e:
                    registrar_auto_update_feeds()
                    resultados['auto_update_feeds']['ran'] = True
                    resultados['auto_update_feeds']['status'] = 'error'
                    resultados['auto_update_feeds']['reason'] = str(e)[:120]
                    escribir_log(f"Auto-update feeds: ERROR ({str(e)})", 'ERROR')
            else:
                resultados['auto_update_feeds']['status'] = 'skipped'
                resultados['auto_update_feeds']['reason'] = f"cooldown activo ({int(restante)}s restantes)"
                escribir_log(
                    f"Auto-update feeds: cooldown activo, se omite ({int(restante)}s restantes)",
                    'INFO'
                )

        if feeds['status'] == 'warning':
            resultados['status'] = 'warning' if resultados['status'] == 'ok' else resultados['status']
        elif feeds['status'] == 'error':
            resultados['status'] = 'error' if resultados['status'] == 'ok' else resultados['status']
    else:
        # Si GVM no está conectado, no podemos verificar feeds
        resultados['checks']['feeds'] = 'error'
        resultados['feeds_details'] = {}
        escribir_log("Feeds: No se puede verificar (GVM no conectado)")

    # Verificar espacio en disco
    disco = verificar_disco(config)
    resultados['checks']['disk'] = disco['status']
    resultados['disk_details'] = disco.get('details', {})
    escribir_log(f"Disco: {disco['message']}")
    if disco['status'] != 'ok':
        resultados['status'] = 'error'
    
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
    
    # Verificar feeds: solo alerta si hay desactualización CONFIRMADA (warning/error)
    if monitoring_config.get('alert_on_feeds_stale', True):
        if checks.get('feeds') == 'warning' or checks.get('feeds') == 'error':
            tiene_problemas = True
        # feeds ok con feeds_unverified no dispara Telegram (política anti-falso-positivo)

    # Verificar espacio en disco
    if monitoring_config.get('alert_on_disk_low', True) and checks.get('disk') != 'ok':
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

