#!/usr/bin/env python3
"""
Script de mantenimiento completo para OpenVAS
Automatiza todas las tareas de mantenimiento: servicios, feeds, limpieza, optimización
"""

import subprocess
import json
import os
import shutil
import glob
import fnmatch
import argparse
import datetime
import time
import re
from pathlib import Path
from gvm.connections import TLSConnection
from gvm.protocols.gmp import Gmp
import xml.etree.ElementTree as ET

# Valores por defecto hardcodeados
REPORT_RETENTION_DAYS = 90
LOG_RETENTION_DAYS = 30
MIN_DISK_SPACE_GB = 10
RESTART_FAILED_SERVICES = False
STOP_SERVICES_FOR_DB_MAINTENANCE = True

# Configuración de verificación de feeds
FEED_VERIFICATION_TIMEOUT_MINUTES = 480  # Tiempo máximo de espera por feed (8 horas)
FEED_VERIFICATION_INTERVAL_SECONDS = 30  # Intervalo entre verificaciones
VERIFY_FEEDS_BEFORE_DB_MAINTENANCE = True  # Verificar feeds antes de optimizar BD
FEED_MAX_AGE_DAYS = 30  # Si los feeds tienen menos de 30 días, no se actualizan

# Archivo de lock para mantenimiento
MAINTENANCE_LOCK_FILE = '/opt/gvm/.maintenance.lock'

class MaintenanceReport:
    """Clase para generar reportes de mantenimiento"""
    def __init__(self):
        self.report = {
            'timestamp': datetime.datetime.now().isoformat(),
            'services': {},
            'feeds': {},
            'cleanup': {},
            'disk_space': {},
            'database': {},
            'certificates': {},
            'errors': [],
            'warnings': [],
            'summary': {}
        }
    
    def add_service_status(self, service, status, message=""):
        self.report['services'][service] = {'status': status, 'message': message}
    
    def add_feed_update(self, feed_type, status, message=""):
        self.report['feeds'][feed_type] = {'status': status, 'message': message}
    
    def add_cleanup(self, item_type, count, size_freed=0):
        if item_type not in self.report['cleanup']:
            self.report['cleanup'][item_type] = {'count': 0, 'size_freed_mb': 0}
        self.report['cleanup'][item_type]['count'] += count
        self.report['cleanup'][item_type]['size_freed_mb'] += size_freed
    
    def add_error(self, error):
        self.report['errors'].append(error)
    
    def add_warning(self, warning):
        self.report['warnings'].append(warning)
    
    def save(self, filepath):
        """Guarda el reporte en formato JSON"""
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, 'w') as f:
            json.dump(self.report, f, indent=2)
    
    def get_summary_text(self):
        """Genera un resumen en texto del reporte"""
        lines = []
        lines.append("=" * 60)
        lines.append("REPORTE DE MANTENIMIENTO OPENVAS")
        lines.append("=" * 60)
        lines.append(f"Fecha: {self.report['timestamp']}")
        lines.append("")
        
        # Servicios
        lines.append("SERVICIOS:")
        for service, info in self.report['services'].items():
            status_icon = "✓" if info['status'] == 'ok' else "✗"
            lines.append(f"  {status_icon} {service}: {info['status']}")
            if info['message']:
                lines.append(f"    {info['message']}")
        lines.append("")
        
        # Feeds
        lines.append("ACTUALIZACIÓN DE FEEDS:")
        for feed, info in self.report['feeds'].items():
            status_icon = "✓" if info['status'] == 'ok' else "✗"
            lines.append(f"  {status_icon} {feed}: {info['status']}")
        lines.append("")
        
        # Limpieza
        lines.append("LIMPIEZA:")
        total_freed = 0
        for item_type, info in self.report['cleanup'].items():
            lines.append(f"  {item_type}: {info['count']} elementos, {info['size_freed_mb']:.2f} MB liberados")
            total_freed += info['size_freed_mb']
        lines.append(f"  Total liberado: {total_freed:.2f} MB")
        lines.append("")
        
        # Errores y advertencias
        if self.report['errors']:
            lines.append("ERRORES:")
            for error in self.report['errors']:
                lines.append(f"  ✗ {error}")
            lines.append("")
        
        if self.report['warnings']:
            lines.append("ADVERTENCIAS:")
            for warning in self.report['warnings']:
                lines.append(f"  ⚠ {warning}")
            lines.append("")
        
        lines.append("=" * 60)
        return "\n".join(lines)


def crear_lock_mantenimiento():
    """
    Crea un archivo de lock para indicar que el mantenimiento está en curso.
    El archivo contiene información sobre cuándo comenzó el mantenimiento.
    """
    try:
        lock_data = {
            'timestamp': datetime.datetime.now().isoformat(),
            'pid': os.getpid(),
            'status': 'running'
        }
        with open(MAINTENANCE_LOCK_FILE, 'w') as f:
            json.dump(lock_data, f, indent=2)
        return True
    except Exception as e:
        print(f"Error al crear lock de mantenimiento: {e}")
        return False


def eliminar_lock_mantenimiento():
    """
    Elimina el archivo de lock cuando el mantenimiento termina.
    """
    try:
        if os.path.exists(MAINTENANCE_LOCK_FILE):
            os.remove(MAINTENANCE_LOCK_FILE)
        return True
    except Exception as e:
        print(f"Error al eliminar lock de mantenimiento: {e}")
        return False


def verificar_lock_mantenimiento():
    """
    Verifica si existe un lock de mantenimiento activo.
    
    Returns:
        tuple: (bool, str) - (True si hay lock activo, mensaje descriptivo)
    """
    if not os.path.exists(MAINTENANCE_LOCK_FILE):
        return False, ""
    
    try:
        with open(MAINTENANCE_LOCK_FILE, 'r') as f:
            lock_data = json.load(f)
        
        timestamp_str = lock_data.get('timestamp', '')
        pid = lock_data.get('pid', 0)
        
        # Verificar si el proceso aún está corriendo
        try:
            os.kill(pid, 0)  # No mata el proceso, solo verifica si existe
            # El proceso existe, el lock es válido
            timestamp = datetime.datetime.fromisoformat(timestamp_str)
            tiempo_transcurrido = datetime.datetime.now() - timestamp.replace(tzinfo=None)
            horas = int(tiempo_transcurrido.total_seconds() / 3600)
            minutos = int((tiempo_transcurrido.total_seconds() % 3600) / 60)
            mensaje = f"Mantenimiento en curso desde {timestamp_str} ({horas}h {minutos}m)"
            return True, mensaje
        except OSError:
            # El proceso no existe, el lock es obsoleto
            # Eliminar el lock obsoleto
            try:
                os.remove(MAINTENANCE_LOCK_FILE)
            except Exception:
                pass
            return False, "Lock obsoleto eliminado"
    except Exception as e:
        # Si hay error al leer el lock, asumir que no está activo
        return False, f"Error al leer lock: {e}"


def leer_configuracion(main_config_path='/opt/gvm/Config/config.json'):
    """Lee solo las credenciales de GVM desde config.json"""
    config = {'user': 'admin', 'password': 'admin'}  # Valores por defecto
    
    try:
        with open(main_config_path, 'r') as f:
            main_config = json.load(f)
            config['user'] = main_config.get('user', 'admin')
            config['password'] = main_config.get('password', 'admin')
    except FileNotFoundError:
        print(f"Advertencia: No se encontró el archivo de configuración: {main_config_path}")
        print("Usando credenciales por defecto (admin/admin)")
    except json.JSONDecodeError as e:
        print(f"Error al decodificar config.json: {e}")
        print("Usando credenciales por defecto (admin/admin)")
    
    return config


def verificar_servicio(service_name, report):
    """Verifica el estado de un servicio systemd"""
    try:
        result = subprocess.run(
            ['systemctl', 'is-active', service_name],
            capture_output=True,
            text=True,
            timeout=5
        )
        is_active = result.stdout.strip() == 'active'
        
        if is_active:
            report.add_service_status(service_name, 'ok', 'Servicio activo')
            return True
        else:
            report.add_service_status(service_name, 'failed', f'Servicio no activo: {result.stdout.strip()}')
            report.add_error(f"Servicio {service_name} no está activo")
            return False
    except subprocess.TimeoutExpired:
        report.add_service_status(service_name, 'timeout', 'Timeout al verificar servicio')
        report.add_warning(f"Timeout al verificar servicio {service_name}")
        return False
    except Exception as e:
        report.add_service_status(service_name, 'error', str(e))
        report.add_error(f"Error al verificar servicio {service_name}: {e}")
        return False


def detener_servicio(service_name, report, dry_run=False):
    """Detiene un servicio"""
    if dry_run:
        print(f"[DRY-RUN] Detendría servicio: {service_name}")
        return True
    
    try:
        result = subprocess.run(
            ['sudo', 'systemctl', 'stop', service_name],
            capture_output=True,
            text=True,
            timeout=60
        )
        if result.returncode == 0:
            report.add_service_status(service_name, 'stopped', 'Servicio detenido exitosamente')
            return True
        else:
            report.add_error(f"Error al detener {service_name}: {result.stderr}")
            return False
    except subprocess.TimeoutExpired:
        report.add_error(f"Timeout al detener {service_name}")
        return False
    except Exception as e:
        report.add_error(f"Excepción al detener {service_name}: {e}")
        return False


def iniciar_servicio(service_name, report, dry_run=False):
    """Inicia un servicio"""
    if dry_run:
        print(f"[DRY-RUN] Iniciaría servicio: {service_name}")
        return True
    
    try:
        result = subprocess.run(
            ['sudo', 'systemctl', 'start', service_name],
            capture_output=True,
            text=True,
            timeout=60
        )
        if result.returncode == 0:
            # Esperar un momento para que el servicio se inicie completamente
            import time
            time.sleep(2)
            report.add_service_status(service_name, 'started', 'Servicio iniciado exitosamente')
            return True
        else:
            report.add_error(f"Error al iniciar {service_name}: {result.stderr}")
            return False
    except subprocess.TimeoutExpired:
        report.add_error(f"Timeout al iniciar {service_name}")
        return False
    except Exception as e:
        report.add_error(f"Excepción al iniciar {service_name}: {e}")
        return False


def reiniciar_servicio(service_name, report, dry_run=False):
    """Reinicia un servicio si está fallando"""
    if dry_run:
        print(f"[DRY-RUN] Reiniciaría servicio: {service_name}")
        return True
    
    try:
        result = subprocess.run(
            ['sudo', 'systemctl', 'restart', service_name],
            capture_output=True,
            text=True,
            timeout=30
        )
        if result.returncode == 0:
            report.add_service_status(service_name, 'restarted', 'Servicio reiniciado exitosamente')
            return True
        else:
            report.add_error(f"Error al reiniciar {service_name}: {result.stderr}")
            return False
    except Exception as e:
        report.add_error(f"Excepción al reiniciar {service_name}: {e}")
        return False


def verificar_servicios(config, report, restart_failed=False, dry_run=False):
    """Verifica todos los servicios críticos de OpenVAS"""
    print("\n[1/7] Verificando servicios del sistema...")
    
    servicios_criticos = ['gvmd', 'ospd-openvas', 'gsad', 'notus-scanner']
    servicios_soporte = ['postgresql', 'redis-server@openvas', 'mosquitto']
    
    todos_servicios = servicios_criticos + servicios_soporte
    
    servicios_fallidos = []
    for servicio in todos_servicios:
        if not verificar_servicio(servicio, report):
            servicios_fallidos.append(servicio)
    
    # Reiniciar servicios fallidos si está configurado
    if restart_failed and servicios_fallidos and not dry_run:
        print(f"Reiniciando servicios fallidos: {', '.join(servicios_fallidos)}")
        for servicio in servicios_fallidos:
            reiniciar_servicio(servicio, report, dry_run)
    
    print(f"Servicios verificados: {len(todos_servicios)}, Fallidos: {len(servicios_fallidos)}")


def obtener_fecha_feed(config, feed_type):
    """
    Obtiene la fecha de última actualización de un feed.
    Intenta múltiples métodos: archivos de feed, base de datos, y comandos de feed-sync.
    
    Args:
        config: Configuración con credenciales de GVM
        feed_type: Tipo de feed (NVT, SCAP, CERT, GVMD_DATA)
    
    Returns:
        datetime.datetime o None: Fecha de última actualización del feed, o None si no se puede obtener
    """
    # Método 1: Verificar archivos de feed directamente (más confiable)
    feed_dirs = {
        'NVT': '/var/lib/openvas/plugins',
        'SCAP': '/var/lib/gvm/scap-data',
        'CERT': '/var/lib/gvm/cert-data',
        'GVMD_DATA': '/var/lib/gvm/data-objects'
    }
    
    feed_dir = feed_dirs.get(feed_type)
    if feed_dir and os.path.exists(feed_dir):
        try:
            # Buscar archivos reales dentro del directorio y obtener la fecha más reciente
            max_mtime = 0
            archivos_encontrados = 0
            
            # Patrones de archivos específicos por tipo de feed
            file_patterns = {
                'NVT': ['*.nasl'],
                'SCAP': ['*.xml', '*.gz'],
                'CERT': ['*.xml', '*.gz'],
                'GVMD_DATA': ['*.xml', '*.gz']
            }
            
            patterns = file_patterns.get(feed_type, ['*'])
            
            # Buscar archivos con los patrones específicos
            for pattern in patterns:
                for root, dirs, files in os.walk(feed_dir):
                    for file in files:
                        if fnmatch.fnmatch(file, pattern):
                            file_path = os.path.join(root, file)
                            try:
                                file_mtime = os.path.getmtime(file_path)
                                if file_mtime > max_mtime:
                                    max_mtime = file_mtime
                                archivos_encontrados += 1
                                # Limitar búsqueda para eficiencia (500 archivos máximo)
                                if archivos_encontrados >= 500:
                                    break
                            except (OSError, IOError):
                                continue
                    if archivos_encontrados >= 500:
                        break
                if archivos_encontrados >= 500:
                    break
            
            # Si encontramos archivos, usar la fecha más reciente
            if max_mtime > 0:
                fecha = datetime.datetime.fromtimestamp(max_mtime)
                return fecha
            
            # Si no encontramos archivos con patrones, buscar cualquier archivo
            if archivos_encontrados == 0:
                for root, dirs, files in os.walk(feed_dir):
                    for file in files[:200]:  # Limitar a primeros 200 archivos
                        file_path = os.path.join(root, file)
                        try:
                            file_mtime = os.path.getmtime(file_path)
                            if file_mtime > max_mtime:
                                max_mtime = file_mtime
                        except (OSError, IOError):
                            continue
                
                if max_mtime > 0:
                    fecha = datetime.datetime.fromtimestamp(max_mtime)
                    return fecha
        except Exception as e:
            # Si hay error, continuar con otros métodos
            pass
    
    # Método 2: Usar greenbone-feed-sync --describe para obtener información del feed
    feed_commands = {
        'NVT': 'greenbone-nvt-sync',
        'SCAP': 'greenbone-feed-sync --type SCAP',
        'CERT': 'greenbone-feed-sync --type CERT',
        'GVMD_DATA': 'greenbone-feed-sync --type GVMD_DATA'
    }
    
    command = feed_commands.get(feed_type)
    if command:
        try:
            # Intentar obtener información del feed usando --describe si está disponible
            cmd_parts = command.split()
            if 'greenbone-feed-sync' in cmd_parts:
                # Agregar --describe si el comando lo soporta
                result = subprocess.run(
                    ['sudo', '-u', 'gvm'] + cmd_parts + ['--describe'],
                    capture_output=True,
                    text=True,
                    timeout=30
                )
                if result.returncode == 0:
                    # Parsear la salida para encontrar fecha (formato puede variar)
                    output = result.stdout
                    # Buscar patrones de fecha en la salida
                    date_patterns = [
                        r'(\d{4}-\d{2}-\d{2})',  # YYYY-MM-DD
                        r'(\d{2}/\d{2}/\d{4})',  # MM/DD/YYYY
                    ]
                    for pattern in date_patterns:
                        matches = re.findall(pattern, output)
                        if matches:
                            try:
                                # Intentar parsear la fecha más reciente
                                for match in matches:
                                    if '-' in match:
                                        fecha = datetime.datetime.strptime(match, '%Y-%m-%d')
                                        return fecha
                            except ValueError:
                                continue
        except Exception:
            pass
    
    # Método 3: Consultar base de datos para obtener versión del feed (más confiable)
    try:
        feed_db_names = {
            'NVT': 'nvt',
            'SCAP': 'scap',
            'CERT': 'cert',
            'GVMD_DATA': 'gvmd_data'
        }
        
        db_name = feed_db_names.get(feed_type, feed_type.lower())
        
        # Consultar tabla info para obtener versión del feed
        # Las versiones suelen tener formato: YYYYMMDDTHHMM (ej: 20240126T0719)
        queries = [
            f"SELECT value FROM info WHERE name = '{db_name}_version' OR name = '{db_name}_feed_version';",
            f"SELECT value FROM info WHERE name LIKE '%{db_name}%version%' ORDER BY name LIMIT 1;",
            f"SELECT value FROM info WHERE name LIKE '%feed%{db_name}%' AND name LIKE '%version%' LIMIT 1;"
        ]
        
        for query in queries:
            try:
                result = subprocess.run(
                    ['sudo', '-u', 'postgres', 'psql', '-d', 'gvmd', '-t', '-c', query],
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                
                if result.returncode == 0:
                    value = result.stdout.strip()
                    if value and value != '' and value != '0':
                        # Los valores de versión suelen tener formato de timestamp
                        # Ejemplo: 20240126T0719 (YYYYMMDDTHHMM)
                        try:
                            if 'T' in value and len(value) >= 8:
                                # Formato: YYYYMMDDTHHMM
                                fecha_str = value.split('T')[0]
                                if len(fecha_str) == 8:  # Asegurar formato correcto
                                    fecha = datetime.datetime.strptime(fecha_str, '%Y%m%d')
                                    return fecha
                        except ValueError:
                            continue
            except Exception:
                continue
    except Exception:
        pass
    
    return None


def necesita_actualizar_feed(config, feed_type, report, dry_run=False):
    """
    Verifica si un feed necesita ser actualizado basándose en su antigüedad.
    
    Args:
        config: Configuración con credenciales de GVM
        feed_type: Tipo de feed (NVT, SCAP, CERT, GVMD_DATA)
        report: Objeto MaintenanceReport para registrar estado
        dry_run: Si es True, solo simula la verificación
    
    Returns:
        bool: True si el feed necesita actualización (tiene más de FEED_MAX_AGE_DAYS días), False en caso contrario
    """
    if dry_run:
        print(f"  [DRY-RUN] Verificaría antigüedad de feed {feed_type}")
        return True
    
    print(f"  Verificando antigüedad de feed {feed_type}...")
    
    fecha_feed = obtener_fecha_feed(config, feed_type)
    
    if fecha_feed is None:
        # Si no se puede obtener la fecha, asumir que necesita actualización por seguridad
        report.add_warning(f"No se pudo obtener la fecha del feed {feed_type}, se actualizará por seguridad")
        print(f"    ⚠ No se pudo obtener fecha de {feed_type}, se actualizará por seguridad")
        return True
    
    # Asegurar que la fecha no tenga timezone para el cálculo
    if fecha_feed.tzinfo is not None:
        fecha_feed = fecha_feed.replace(tzinfo=None)
    
    edad_dias = (datetime.datetime.now() - fecha_feed).days
    
    # Mostrar información detallada
    fecha_str = fecha_feed.strftime('%Y-%m-%d %H:%M:%S')
    print(f"    Fecha del feed {feed_type}: {fecha_str}")
    print(f"    Edad del feed: {edad_dias} días (máximo permitido: {FEED_MAX_AGE_DAYS} días)")
    
    if edad_dias >= FEED_MAX_AGE_DAYS:
        print(f"    → Feed {feed_type} necesita actualización (tiene {edad_dias} días, máximo: {FEED_MAX_AGE_DAYS})")
        return True
    else:
        print(f"    ✓ Feed {feed_type} NO necesita actualización (tiene {edad_dias} días, máximo: {FEED_MAX_AGE_DAYS})")
        return False


def verificar_estado_feeds(config, feed_type, report, timeout_minutes=None, check_interval=None, dry_run=False):
    """
    Verifica que un feed NO esté en estado "Update in progress...".
    Verifica que no haya actividad de actualización activa.
    
    Args:
        config: Configuración con credenciales de GVM
        feed_type: Tipo de feed (NVT, SCAP, CERT, GVMD_DATA)
        report: Objeto MaintenanceReport para registrar estado
        timeout_minutes: Tiempo máximo de espera en minutos (None = usar constante)
        check_interval: Intervalo entre verificaciones en segundos (None = usar constante)
        dry_run: Si es True, solo simula la verificación
    
    Returns:
        bool: True si el feed NO está en "Update in progress...", False si hay timeout o error
    """
    if dry_run:
        print(f"  [DRY-RUN] Verificaría estado de feed {feed_type}")
        return True
    
    if timeout_minutes is None:
        timeout_minutes = FEED_VERIFICATION_TIMEOUT_MINUTES
    if check_interval is None:
        check_interval = FEED_VERIFICATION_INTERVAL_SECONDS
    
    timeout_seconds = timeout_minutes * 60
    start_time = time.time()
    check_count = 0
    consecutive_no_activity = 0
    
    print(f"  Verificando que {feed_type} NO esté en 'Update in progress...'...")
    
    # Mapeo de tipos de feed a palabras clave para búsqueda
    feed_keywords = {
        'NVT': ['nvt', 'nvts'],
        'SCAP': ['scap', 'cve', 'cpe'],
        'CERT': ['cert', 'advisory'],
        'GVMD_DATA': ['gvmd_data', 'port_list', 'scan_config', 'report_format']
    }
    
    keywords = feed_keywords.get(feed_type, [feed_type.lower()])
    
    # Método 0: Verificar directamente el estado del feed en la base de datos (más confiable)
    # Consultar la tabla info para ver si hay un proceso de actualización activo
    feed_db_names = {
        'NVT': 'nvt',
        'SCAP': 'scap',
        'CERT': 'cert',
        'GVMD_DATA': 'gvmd_data'
    }
    
    db_name = feed_db_names.get(feed_type, feed_type.lower())
    
    while (time.time() - start_time) < timeout_seconds:
        check_count += 1
        has_activity = False
        
        # Método 0: Verificar directamente en la base de datos si hay proceso de actualización
        try:
            # Buscar si hay algún proceso de actualización activo en la tabla de información
            # o verificar si hay locks de actualización
            query = f"""
            SELECT COUNT(*) FROM pg_stat_activity 
            WHERE state = 'active' 
            AND (query ILIKE '%{db_name}%update%' OR query ILIKE '%{db_name}%sync%' OR query ILIKE '%feed%{db_name}%')
            AND query NOT ILIKE '%pg_stat_activity%';
            """
            
            result = subprocess.run(
                ['sudo', '-u', 'postgres', 'psql', '-d', 'gvmd', '-t', '-c', query],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode == 0:
                active_queries = result.stdout.strip()
                if active_queries and int(active_queries) > 0:
                    has_activity = True
        except Exception:
            pass
        
        # Método 1: Verificar procesos activos de gvmd relacionados con feeds (solo si no se encontró actividad en BD)
        if not has_activity:
            try:
                result = subprocess.run(
                    ['ps', 'aux'],
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                
                if result.returncode == 0:
                    processes = result.stdout
                    processes_lower = processes.lower()
                    
                    # Buscar procesos de gvmd que puedan estar actualizando feeds
                    # Buscar específicamente procesos de feed-sync o nvt-sync
                    sync_keywords = ['feed-sync', 'nvt-sync', 'scapdata-sync', 'certdata-sync']
                    for sync_keyword in sync_keywords:
                        if sync_keyword in processes_lower:
                            # Verificar si es el tipo de feed correcto
                            for keyword in keywords:
                                if keyword in processes_lower:
                                    has_activity = True
                                    break
                            if has_activity:
                                break
            except Exception:
                pass
        
        # Método 2: Verificar queries activas en la base de datos relacionadas con feeds (solo si no se encontró actividad)
        if not has_activity:
            try:
                # Construir query más específica para buscar actividad relacionada con el feed
                query_keywords = ' OR '.join([f"query ILIKE '%{kw}%'" for kw in keywords])
                query = f"""
                SELECT count(*) FROM pg_stat_activity 
                WHERE state = 'active' 
                AND ({query_keywords})
                AND query NOT ILIKE '%pg_stat_activity%'
                AND query NOT ILIKE '%SELECT%';
                """
                
                result = subprocess.run(
                    ['sudo', '-u', 'postgres', 'psql', '-d', 'gvmd', '-t', '-c', query],
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                
                if result.returncode == 0:
                    active_queries = result.stdout.strip()
                    if active_queries and int(active_queries) > 0:
                        has_activity = True
            except Exception:
                pass
        
        # Si no hay actividad, incrementar contador
        if not has_activity:
            consecutive_no_activity += 1
            # Si no hay actividad durante al menos 3 verificaciones consecutivas (más conservador), asumir que terminó
            if consecutive_no_activity >= 3:
                elapsed = int(time.time() - start_time)
                print(f"  ✓ {feed_type} NO está en 'Update in progress...' (sin actividad después de {elapsed}s, {check_count} verificaciones)")
                return True
        else:
            consecutive_no_activity = 0
            elapsed = int(time.time() - start_time)
            print(f"    [{elapsed}s] {feed_type} aún procesándose... (verificación {check_count})")
        
        time.sleep(check_interval)
    
    # Timeout alcanzado (máximo 8 horas)
    elapsed_hours = int((time.time() - start_time) / 3600)
    elapsed_minutes = int(((time.time() - start_time) % 3600) / 60)
    warning_msg = f"Timeout al verificar {feed_type} después de {elapsed_hours}h {elapsed_minutes}m (máximo 8 horas)"
    report.add_warning(warning_msg)
    print(f"  ⚠ {warning_msg}")
    return False


def verificar_todos_los_feeds(config, report, dry_run=False):
    """
    Verifica que todos los feeds estén en estado 'Current' (completamente actualizados).
    
    Returns:
        bool: True si todos los feeds están completos, False si alguno está en progreso
    """
    if dry_run:
        print("[DRY-RUN] Verificaría estado de todos los feeds")
        return True
    
    feeds_a_verificar = ['NVT', 'SCAP', 'CERT', 'GVMD_DATA']
    todos_completos = True
    
    print("\nVerificando estado final de todos los feeds...")
    
    for feed_type in feeds_a_verificar:
        # Usar timeout de 8 horas también para la verificación final
        if not verificar_estado_feeds(config, feed_type, report, timeout_minutes=480, 
                                      check_interval=30, dry_run=dry_run):
            todos_completos = False
    
    return todos_completos


def verificar_comando_disponible(comando):
    """
    Verifica si un comando está disponible en el sistema.
    
    Args:
        comando: Nombre del comando a verificar
    
    Returns:
        bool: True si el comando está disponible, False en caso contrario
    """
    try:
        result = subprocess.run(
            ['which', comando],
            capture_output=True,
            text=True,
            timeout=5
        )
        return result.returncode == 0
    except Exception:
        return False


def actualizar_feeds(config, report, dry_run=False):
    """Actualiza los feeds de vulnerabilidades de OpenVAS"""
    print("\n[2/7] Actualizando feeds de vulnerabilidades...")
    
    # Verificar si los comandos específicos están disponibles (según documentación oficial)
    usar_scapdata_sync = verificar_comando_disponible('greenbone-scapdata-sync')
    usar_certdata_sync = verificar_comando_disponible('greenbone-certdata-sync')
    
    if usar_scapdata_sync:
        print("  ✓ Comando 'greenbone-scapdata-sync' disponible, se usará en lugar de 'greenbone-feed-sync --type SCAP'")
    if usar_certdata_sync:
        print("  ✓ Comando 'greenbone-certdata-sync' disponible, se usará en lugar de 'greenbone-feed-sync --type CERT'")
    
    # Construir lista de feeds con comandos preferidos si están disponibles
    feeds = [
        ('NVT', 'greenbone-nvt-sync'),
        ('GVMD_DATA', 'greenbone-feed-sync --type GVMD_DATA'),
        ('SCAP', 'greenbone-scapdata-sync' if usar_scapdata_sync else 'greenbone-feed-sync --type SCAP'),
        ('CERT', 'greenbone-certdata-sync' if usar_certdata_sync else 'greenbone-feed-sync --type CERT')
    ]
    
    for feed_type, command in feeds:
        if dry_run:
            print(f"[DRY-RUN] Ejecutaría: sudo -u gvm {command}")
            report.add_feed_update(feed_type, 'simulated', 'Simulado en dry-run')
            continue
        
        # Verificar si el feed necesita actualización (antigüedad > 1 mes)
        if not necesita_actualizar_feed(config, feed_type, report, dry_run):
            report.add_feed_update(feed_type, 'skipped', f'Feed tiene menos de {FEED_MAX_AGE_DAYS} días, no necesita actualización')
            print(f"  ⊘ {feed_type} omitido (no necesita actualización)")
            continue
        
        try:
            cmd_parts = command.split()
            # Timeout de 8 horas para la sincronización (28800 segundos)
            result = subprocess.run(
                ['sudo', '-u', 'gvm'] + cmd_parts,
                capture_output=True,
                text=True,
                timeout=28800  # 8 horas máximo
            )
            
            if result.returncode == 0:
                print(f"  ✓ {feed_type} sincronizado, verificando inserción en BD...")
                
                # Verificar que el feed haya terminado de insertarse en la base de datos
                # Usar timeout de 8 horas también para la verificación
                feed_verified = verificar_estado_feeds(config, feed_type, report, 
                                                      timeout_minutes=480, dry_run=dry_run)
                
                if feed_verified:
                    report.add_feed_update(feed_type, 'ok', 'Actualización e inserción completadas')
                    print(f"  ✓ {feed_type} completamente actualizado e insertado")
                else:
                    report.add_feed_update(feed_type, 'warning', 'Sincronización completada pero verificación de inserción con timeout (8h)')
                    report.add_warning(f"Feed {feed_type} sincronizado pero la verificación de inserción alcanzó timeout de 8 horas")
                    print(f"  ⚠ {feed_type} sincronizado pero verificación de inserción incompleta (timeout 8h)")
            else:
                report.add_feed_update(feed_type, 'error', result.stderr[:200])
                report.add_warning(f"Error al actualizar feed {feed_type}")
                print(f"  ✗ {feed_type} error: {result.stderr[:100]}")
        except subprocess.TimeoutExpired:
            report.add_feed_update(feed_type, 'timeout', 'Timeout en actualización (8 horas)')
            report.add_warning(f"Timeout al actualizar feed {feed_type} después de 8 horas")
            print(f"  ✗ {feed_type} timeout en sincronización (8 horas)")
        except Exception as e:
            report.add_feed_update(feed_type, 'error', str(e))
            report.add_error(f"Excepción al actualizar {feed_type}: {e}")
            print(f"  ✗ {feed_type} excepción: {e}")


def limpiar_reportes_antiguos(config, report, dry_run=False):
    """Limpia reportes antiguos de OpenVAS"""
    print("\n[3/7] Limpiando reportes antiguos...")
    
    retention_days = REPORT_RETENTION_DAYS
    # Asegurar que cutoff_date tenga timezone para comparar correctamente
    cutoff_date = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=retention_days)
    
    try:
        # Usar TLS en lugar de Unix Socket (compatible con Docker)
        connection = TLSConnection(hostname="127.0.0.1", port=9390)
        
        with Gmp(connection=connection) as gmp:
            user = config.get('user', 'admin')
            password = config.get('password', 'admin')
            gmp.authenticate(user, password)
            
            # Obtener todos los reportes
            response = gmp.get_reports(filter_string='rows=-1')
            root = ET.fromstring(response)
            reports = root.findall(".//report")
            
            deleted_count = 0
            for report_elem in reports:
                report_id = report_elem.get('id')
                timestamp_elem = report_elem.find('.//timestamp')
                
                if timestamp_elem is not None:
                    timestamp_str = timestamp_elem.text
                    try:
                        # Formato: 2024-01-15T10:30:00Z
                        report_date = datetime.datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                        # Asegurar que ambas fechas tengan timezone para comparar
                        if report_date.tzinfo is None:
                            report_date = report_date.replace(tzinfo=datetime.timezone.utc)
                        if cutoff_date.tzinfo is None:
                            cutoff_date = cutoff_date.replace(tzinfo=datetime.timezone.utc)
                        if report_date < cutoff_date:
                            if not dry_run:
                                gmp.delete_report(report_id)
                            deleted_count += 1
                    except (ValueError, AttributeError):
                        # Si no se puede parsear la fecha, saltar
                        continue
            
            report.add_cleanup('reports', deleted_count)
            print(f"  Reportes eliminados: {deleted_count}")
            
    except Exception as e:
        report.add_error(f"Error al limpiar reportes: {e}")
        print(f"  Error: {e}")


def limpiar_archivos_temporales(config, report, dry_run=False):
    """Limpia archivos CSV y logs temporales"""
    print("\n[4/7] Limpiando archivos temporales...")
    
    # Limpiar CSVs en Reports/exports
    csv_dir = '/opt/gvm/Reports/exports/'
    csv_count = 0
    csv_size = 0
    
    if os.path.exists(csv_dir):
        csv_files = glob.glob(os.path.join(csv_dir, '*.csv'))
        for csv_file in csv_files:
            try:
                size = os.path.getsize(csv_file)
                if not dry_run:
                    os.remove(csv_file)
                csv_count += 1
                csv_size += size
            except Exception as e:
                report.add_warning(f"Error al eliminar {csv_file}: {e}")
    
    report.add_cleanup('csv_files', csv_count, csv_size / (1024 * 1024))
    
    # Limpiar logs antiguos
    log_retention_days = LOG_RETENTION_DAYS
    log_cutoff = datetime.datetime.now() - datetime.timedelta(days=log_retention_days)
    
    log_dirs = [
        '/var/log/gvm/',
        '/opt/gvm/'
    ]
    
    log_count = 0
    log_size = 0
    
    for log_dir in log_dirs:
        if os.path.exists(log_dir):
            for log_file in glob.glob(os.path.join(log_dir, '*.log')):
                try:
                    mtime = datetime.datetime.fromtimestamp(os.path.getmtime(log_file))
                    if mtime < log_cutoff:
                        size = os.path.getsize(log_file)
                        if not dry_run:
                            os.remove(log_file)
                        log_count += 1
                        log_size += size
                except Exception as e:
                    report.add_warning(f"Error al eliminar log {log_file}: {e}")
    
    report.add_cleanup('log_files', log_count, log_size / (1024 * 1024))
    
    # Limpiar archivos temporales específicos
    temp_files = [
        '/opt/gvm/tasksend.txt',
        '/opt/gvm/taskslog.txt',
        '/opt/gvm/logbalbix.txt'
    ]
    
    temp_count = 0
    for temp_file in temp_files:
        if os.path.exists(temp_file):
            try:
                if not dry_run:
                    os.remove(temp_file)
                temp_count += 1
            except Exception as e:
                report.add_warning(f"Error al eliminar {temp_file}: {e}")
    
    report.add_cleanup('temp_files', temp_count)
    print(f"  Archivos CSV eliminados: {csv_count}")
    print(f"  Archivos log eliminados: {log_count}")
    print(f"  Archivos temporales eliminados: {temp_count}")


def verificar_espacio_disco(config, report):
    """Verifica el espacio disponible en disco"""
    print("\n[5/7] Verificando espacio en disco...")
    
    min_space_gb = MIN_DISK_SPACE_GB
    
    try:
        result = subprocess.run(
            ['df', '-h', '/'],
            capture_output=True,
            text=True
        )
        
        lines = result.stdout.strip().split('\n')
        if len(lines) > 1:
            parts = lines[1].split()
            if len(parts) >= 4:
                # parts[3] es el espacio disponible
                available = parts[3]
                # Convertir a GB
                if 'G' in available:
                    available_gb = float(available.replace('G', ''))
                elif 'M' in available:
                    available_gb = float(available.replace('M', '')) / 1024
                else:
                    available_gb = 0
                
                report.report['disk_space'] = {
                    'available_gb': available_gb,
                    'min_required_gb': min_space_gb,
                    'status': 'ok' if available_gb >= min_space_gb else 'warning'
                }
                
                if available_gb < min_space_gb:
                    report.add_warning(f"Espacio en disco bajo: {available_gb:.2f} GB disponible (mínimo: {min_space_gb} GB)")
                else:
                    print(f"  Espacio disponible: {available_gb:.2f} GB")
    except Exception as e:
        report.add_error(f"Error al verificar espacio en disco: {e}")


def optimizar_base_datos(config, report, dry_run=False):
    """Optimiza la base de datos PostgreSQL"""
    print("\n[6/7] Optimizando base de datos PostgreSQL...")
    
    if dry_run:
        print("[DRY-RUN] Detendría servicios, ejecutaría VACUUM, ANALYZE y REINDEX, luego reiniciaría servicios")
        report.report['database'] = {'status': 'simulated'}
        return
    
    # Servicios críticos que deben detenerse antes de VACUUM
    # Orden de detención: gsad, gvmd, ospd-openvas (orden inverso al de inicio)
    servicios_criticos = ['gsad', 'gvmd', 'ospd-openvas']
    servicios_detenidos = []
    stop_services = STOP_SERVICES_FOR_DB_MAINTENANCE
    
    try:
        # Detener servicios críticos antes de VACUUM
        if stop_services:
            print("  Deteniendo servicios críticos antes de optimización de BD...")
            for servicio in servicios_criticos:
                if detener_servicio(servicio, report, dry_run):
                    servicios_detenidos.append(servicio)
                    print(f"    ✓ {servicio} detenido")
                else:
                    report.add_warning(f"No se pudo detener {servicio}, continuando de todas formas...")
            
            if servicios_detenidos:
                import time
                print("  Esperando 5 segundos para que las conexiones se cierren...")
                time.sleep(5)
        
        # Obtener tamaño de la base de datos antes
        result_before = subprocess.run(
            ['sudo', '-u', 'postgres', 'psql', '-d', 'gvmd', '-c', 
             "SELECT pg_size_pretty(pg_database_size('gvmd'));"],
            capture_output=True,
            text=True
        )
        
        size_before = result_before.stdout.strip() if result_before.returncode == 0 else "N/A"
        
        # Ejecutar VACUUM (optimiza la BD sin lock exclusivo, más rápido)
        result_vacuum = subprocess.run(
            ['sudo', '-u', 'postgres', 'psql', '-d', 'gvmd', '-c', 'VACUUM;'],
            capture_output=True,
            text=True,
            timeout=3600
        )
        
        if result_vacuum.returncode == 0:
            print("  ✓ VACUUM completado")
        else:
            report.add_warning(f"VACUUM completado con advertencias: {result_vacuum.stderr[:200]}")
        
        # Ejecutar ANALYZE para actualizar estadísticas del optimizador
        result_analyze = subprocess.run(
            ['sudo', '-u', 'postgres', 'psql', '-d', 'gvmd', '-c', 'ANALYZE;'],
            capture_output=True,
            text=True,
            timeout=1800  # 30 minutos máximo para ANALYZE
        )
        
        if result_analyze.returncode == 0:
            print("  ✓ ANALYZE completado")
        else:
            report.add_warning(f"ANALYZE completado con advertencias: {result_analyze.stderr[:200]}")
        
        # Ejecutar REINDEX
        result_reindex = subprocess.run(
            ['sudo', '-u', 'postgres', 'psql', '-d', 'gvmd', '-c', 'REINDEX DATABASE gvmd;'],
            capture_output=True,
            text=True,
            timeout=3600
        )
        
        if result_reindex.returncode == 0:
            print("  ✓ REINDEX completado")
        else:
            report.add_warning(f"REINDEX completado con advertencias: {result_reindex.stderr[:200]}")
        
        # Obtener tamaño después
        result_after = subprocess.run(
            ['sudo', '-u', 'postgres', 'psql', '-d', 'gvmd', '-c', 
             "SELECT pg_size_pretty(pg_database_size('gvmd'));"],
            capture_output=True,
            text=True
        )
        
        size_after = result_after.stdout.strip() if result_after.returncode == 0 else "N/A"
        
        report.report['database'] = {
            'status': 'ok',
            'size_before': size_before,
            'size_after': size_after
        }
        
        # Reiniciar servicios que fueron detenidos
        # Según la documentación oficial de GVM, el orden correcto es:
        # 1. ospd-openvas (scanner debe estar corriendo antes que gvmd)
        # 2. gvmd (manager necesita el scanner)
        # 3. gsad (frontend necesita el manager)
        if stop_services and servicios_detenidos:
            print("  Reiniciando servicios críticos después de optimización...")
            import time
            
            # Orden correcto de reinicio según documentación oficial de GVM
            orden_reinicio = ['ospd-openvas', 'gvmd', 'gsad']
            
            for servicio in orden_reinicio:
                if servicio in servicios_detenidos:
                    # Verificar socket del scanner antes de iniciar gvmd
                    if servicio == 'gvmd':
                        socket_path = '/run/ospd/ospd-openvas.sock'
                        if not verificar_socket_scanner(socket_path, dry_run):
                            report.add_warning(f"Socket del scanner no encontrado antes de iniciar gvmd: {socket_path}")
                            print(f"    ⚠ Advertencia: Socket del scanner no encontrado, pero continuando...")
                    
                    if iniciar_servicio(servicio, report, dry_run):
                        print(f"    ✓ {servicio} iniciado")
                        time.sleep(5)  # Esperar más tiempo entre reinicios para estabilidad
                    else:
                        report.add_error(f"Error crítico: No se pudo reiniciar {servicio}")
            
            print("  Esperando 15 segundos para que los servicios se estabilicen...")
            time.sleep(15)
            
            # Verificar que los scanners estén disponibles después del reinicio
            print("  Verificando disponibilidad de scanners después del reinicio...")
            scanners_disponibles = verificar_scanners_disponibles(config, report, max_retries=5, retry_delay=5, dry_run=dry_run)
            
            if not scanners_disponibles:
                report.add_warning("Algunos scanners no están disponibles después del reinicio. Puede ser necesario reiniciar gvmd nuevamente.")
                print("    ⚠ Algunos scanners no están disponibles. Considerando reinicio de gvmd...")
                
                # Intentar reiniciar gvmd una vez más si los scanners no están disponibles
                if not dry_run:
                    print("    Reiniciando gvmd nuevamente para asegurar disponibilidad de scanners...")
                    if iniciar_servicio('gvmd', report, dry_run):
                        time.sleep(10)
                        verificar_scanners_disponibles(config, report, max_retries=3, retry_delay=5, dry_run=dry_run)
        
    except subprocess.TimeoutExpired:
        report.add_error("Timeout al optimizar base de datos")
        # Intentar reiniciar servicios incluso si hubo timeout
        if stop_services and servicios_detenidos:
            print("  Intentando reiniciar servicios después del error...")
            orden_reinicio = ['ospd-openvas', 'gvmd', 'gsad']
            for servicio in orden_reinicio:
                if servicio in servicios_detenidos:
                    iniciar_servicio(servicio, report, dry_run)
                    time.sleep(5)
            # Verificar scanners después del reinicio de emergencia
            if not dry_run:
                time.sleep(10)
                verificar_scanners_disponibles(config, report, max_retries=3, retry_delay=5, dry_run=dry_run)
    except Exception as e:
        report.add_error(f"Error al optimizar base de datos: {e}")
        # Intentar reiniciar servicios incluso si hubo error
        if stop_services and servicios_detenidos:
            print("  Intentando reiniciar servicios después del error...")
            orden_reinicio = ['ospd-openvas', 'gvmd', 'gsad']
            for servicio in orden_reinicio:
                if servicio in servicios_detenidos:
                    iniciar_servicio(servicio, report, dry_run)
                    time.sleep(5)
            # Verificar scanners después del reinicio de emergencia
            if not dry_run:
                time.sleep(10)
                verificar_scanners_disponibles(config, report, max_retries=3, retry_delay=5, dry_run=dry_run)


def verificar_socket_scanner(socket_path='/run/ospd/ospd-openvas.sock', dry_run=False):
    """
    Verifica que el socket del scanner exista y esté disponible.
    Según la documentación oficial de GVM, el socket debe existir antes de iniciar gvmd.
    
    Args:
        socket_path: Ruta del socket del scanner
        dry_run: Si es True, solo simula la verificación
    
    Returns:
        bool: True si el socket existe, False en caso contrario
    """
    if dry_run:
        print(f"  [DRY-RUN] Verificaría existencia del socket: {socket_path}")
        return True
    
    if os.path.exists(socket_path):
        print(f"  ✓ Socket del scanner encontrado: {socket_path}")
        return True
    else:
        print(f"  ✗ Socket del scanner NO encontrado: {socket_path}")
        return False


def verificar_scanners_disponibles(config, report, max_retries=5, retry_delay=5, dry_run=False):
    """
    Verifica que los scanners estén disponibles usando gvmd --get-scanners.
    Según la documentación oficial de GVM, los scanners deben estar disponibles después de reiniciar servicios.
    
    Args:
        config: Configuración con credenciales de GVM
        report: Objeto MaintenanceReport para registrar estado
        max_retries: Número máximo de intentos
        retry_delay: Tiempo de espera entre intentos (segundos)
        dry_run: Si es True, solo simula la verificación
    
    Returns:
        bool: True si los scanners están disponibles, False en caso contrario
    """
    if dry_run:
        print("  [DRY-RUN] Verificaría disponibilidad de scanners")
        return True
    
    print("  Verificando disponibilidad de scanners...")
    
    for attempt in range(1, max_retries + 1):
        try:
            result = subprocess.run(
                ['sudo', '-u', 'gvm', 'gvmd', '--get-scanners'],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode == 0:
                output = result.stdout.strip()
                lines = output.split('\n')
                
                scanners_ok = True
                scanners_info = []
                
                for line in lines:
                    if line.strip():
                        parts = line.split()
                        if len(parts) >= 3:
                            scanner_id = parts[0]
                            scanner_name = parts[1]
                            scanner_status = parts[2]
                            
                            scanners_info.append({
                                'id': scanner_id,
                                'name': scanner_name,
                                'status': scanner_status
                            })
                            
                            # Status '0' significa que el scanner no está disponible
                            if scanner_status == '0':
                                scanners_ok = False
                                print(f"    ⚠ Scanner {scanner_name} ({scanner_id}) tiene status '0' (no disponible)")
                            else:
                                print(f"    ✓ Scanner {scanner_name} ({scanner_id}) tiene status '{scanner_status}' (disponible)")
                
                if scanners_ok:
                    print(f"  ✓ Todos los scanners están disponibles después de {attempt} intento(s)")
                    report.report['scanners'] = {'status': 'ok', 'scanners': scanners_info}
                    return True
                else:
                    if attempt < max_retries:
                        print(f"    Esperando {retry_delay} segundos antes del siguiente intento ({attempt}/{max_retries})...")
                        time.sleep(retry_delay)
                    else:
                        report.add_warning("Algunos scanners no están disponibles después de reiniciar servicios")
                        report.report['scanners'] = {'status': 'warning', 'scanners': scanners_info}
                        print(f"  ⚠ Algunos scanners no están disponibles después de {max_retries} intentos")
                        return False
            else:
                if attempt < max_retries:
                    print(f"    Error al obtener scanners, reintentando en {retry_delay} segundos ({attempt}/{max_retries})...")
                    time.sleep(retry_delay)
                else:
                    report.add_error(f"Error al verificar scanners: {result.stderr}")
                    print(f"  ✗ Error al verificar scanners después de {max_retries} intentos: {result.stderr[:100]}")
                    return False
        except subprocess.TimeoutExpired:
            if attempt < max_retries:
                print(f"    Timeout al verificar scanners, reintentando en {retry_delay} segundos ({attempt}/{max_retries})...")
                time.sleep(retry_delay)
            else:
                report.add_error("Timeout al verificar scanners después de múltiples intentos")
                print(f"  ✗ Timeout al verificar scanners después de {max_retries} intentos")
                return False
        except Exception as e:
            if attempt < max_retries:
                print(f"    Excepción al verificar scanners, reintentando en {retry_delay} segundos ({attempt}/{max_retries}): {e}")
                time.sleep(retry_delay)
            else:
                report.add_error(f"Excepción al verificar scanners: {e}")
                print(f"  ✗ Excepción al verificar scanners después de {max_retries} intentos: {e}")
                return False
    
    return False


def verificar_certificados(config, report):
    """Verifica la validez de los certificados SSL/TLS"""
    print("\n[7/7] Verificando certificados SSL/TLS...")
    
    cert_paths = [
        '/var/lib/gvm/CA/cacert.pem',
        '/var/lib/gvm/CA/servercert.pem'
    ]
    
    cert_status = {}
    for cert_path in cert_paths:
        if os.path.exists(cert_path):
            try:
                result = subprocess.run(
                    ['openssl', 'x509', '-in', cert_path, '-noout', '-enddate'],
                    capture_output=True,
                    text=True
                )
                if result.returncode == 0:
                    # Parsear fecha de expiración
                    expiry_line = result.stdout.strip()
                    cert_status[cert_path] = {'status': 'ok', 'expiry': expiry_line}
                else:
                    cert_status[cert_path] = {'status': 'error', 'message': result.stderr}
            except Exception as e:
                cert_status[cert_path] = {'status': 'error', 'message': str(e)}
        else:
            cert_status[cert_path] = {'status': 'not_found'}
    
    report.report['certificates'] = cert_status
    print(f"  Certificados verificados: {len(cert_paths)}")


def main():
    parser = argparse.ArgumentParser(
        description='Script de mantenimiento completo para OpenVAS'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Simular ejecución sin hacer cambios reales'
    )
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Mostrar información detallada'
    )
    
    args = parser.parse_args()
    
    if args.dry_run:
        print("=" * 60)
        print("MODO DRY-RUN: No se realizarán cambios reales")
        print("=" * 60)
    
    # Verificar si ya hay un mantenimiento en curso
    if not args.dry_run:
        lock_activo, mensaje = verificar_lock_mantenimiento()
        if lock_activo:
            print("=" * 60)
            print("ERROR: Ya hay un mantenimiento en curso")
            print(mensaje)
            print("=" * 60)
            print("Si el proceso anterior falló, elimine manualmente el archivo:")
            print(f"  rm {MAINTENANCE_LOCK_FILE}")
            return 1
        
        # Crear lock de mantenimiento
        if not crear_lock_mantenimiento():
            print("ERROR: No se pudo crear el lock de mantenimiento")
            return 1
        print(f"Lock de mantenimiento creado: {MAINTENANCE_LOCK_FILE}")
    
    # Leer solo credenciales de GVM
    config = leer_configuracion()
    
    # Crear reporte
    report = MaintenanceReport()
    
    # Asegurar que se elimine el lock al finalizar (incluso si hay error)
    try:
        # Ejecutar tareas de mantenimiento
        restart_failed = RESTART_FAILED_SERVICES
        verificar_servicios(config, report, restart_failed, args.dry_run)
        actualizar_feeds(config, report, args.dry_run)
        limpiar_reportes_antiguos(config, report, args.dry_run)
        limpiar_archivos_temporales(config, report, args.dry_run)
        verificar_espacio_disco(config, report)
        
        # Verificar que todos los feeds estén completos antes de optimizar BD
        if VERIFY_FEEDS_BEFORE_DB_MAINTENANCE and not args.dry_run:
            print("\nVerificando estado final de feeds antes de optimización de BD...")
            todos_feeds_completos = verificar_todos_los_feeds(config, report, args.dry_run)
            
            if not todos_feeds_completos:
                warning_msg = "Algunos feeds aún están en proceso de actualización. Se recomienda esperar antes de optimizar la BD."
                report.add_warning(warning_msg)
                print(f"\n⚠ ADVERTENCIA: {warning_msg}")
                print("¿Desea continuar con la optimización de BD de todas formas? (puede causar problemas)")
                # En modo automático, continuamos pero con advertencia
                # En producción, se podría agregar una opción para abortar aquí
            else:
                print("✓ Todos los feeds están completamente actualizados. Procediendo con optimización de BD...")
        
        optimizar_base_datos(config, report, args.dry_run)
        verificar_certificados(config, report)
        
        # Generar resumen
        print("\n" + "=" * 60)
        print("RESUMEN DE MANTENIMIENTO")
        print("=" * 60)
        summary = report.get_summary_text()
        print(summary)
        
        # Guardar reporte
        log_dir = '/opt/gvm/logs/maintenance/'
        os.makedirs(log_dir, exist_ok=True)
        timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        report_file = os.path.join(log_dir, f'maintenance_report_{timestamp}.json')
        report.save(report_file)
        print(f"\nReporte guardado en: {report_file}")
        
        # Guardar también en texto
        text_file = os.path.join(log_dir, f'maintenance_report_{timestamp}.txt')
        with open(text_file, 'w') as f:
            f.write(summary)
        
        # Retornar código de salida basado en errores
        exit_code = 1 if report.report['errors'] else 0
    except Exception as e:
        # Asegurar que se elimine el lock incluso si hay excepción
        if not args.dry_run:
            eliminar_lock_mantenimiento()
            print(f"Lock de mantenimiento eliminado (después de error)")
        raise
    finally:
        # Eliminar lock de mantenimiento siempre al finalizar
        if not args.dry_run:
            eliminar_lock_mantenimiento()
            print(f"Lock de mantenimiento eliminado")
    
    return exit_code


if __name__ == "__main__":
    exit(main())
