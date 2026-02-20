#!/usr/bin/env python3
"""
Script de diagnóstico para el servicio de monitoreo
Ejecuta las mismas verificaciones que el servicio pero con más detalles
"""

import json
import os
import sys
import subprocess
from datetime import datetime

# Configuración
CONFIG_PATH = '/opt/gvm/Config/config.json'
MONITOR_CONFIG_PATH = '/opt/gvm/Monitor/config.json'
LOG_DIR = '/opt/gvm/logs/monitoring'
ALERT_COOLDOWN_FILE = f'{LOG_DIR}/alert_cooldown.json'

def print_section(title):
    print(f"\n{'='*60}")
    print(f" {title}")
    print('='*60)

def check_file_permissions(path, description):
    print(f"\n{description}: {path}")
    if os.path.exists(path):
        stat = os.stat(path)
        print(f"  ✓ Existe")
        print(f"  Propietario: {stat.st_uid} (UID)")
        print(f"  Grupo: {stat.st_gid} (GID)")
        print(f"  Permisos: {oct(stat.st_mode)[-3:]}")
        
        # Verificar si el usuario actual puede leerlo
        if os.access(path, os.R_OK):
            print(f"  ✓ Lectura: OK")
        else:
            print(f"  ✗ Lectura: DENEGADO")
            
        if os.access(path, os.W_OK):
            print(f"  ✓ Escritura: OK")
        else:
            print(f"  ✗ Escritura: DENEGADO")
    else:
        print(f"  ✗ No existe")

def check_directory_permissions(path, description):
    print(f"\n{description}: {path}")
    if os.path.exists(path):
        stat = os.stat(path)
        print(f"  ✓ Existe")
        print(f"  Propietario: {stat.st_uid} (UID)")
        print(f"  Grupo: {stat.st_gid} (GID)")
        print(f"  Permisos: {oct(stat.st_mode)[-3:]}")
        
        if os.access(path, os.R_OK):
            print(f"  ✓ Lectura: OK")
        else:
            print(f"  ✗ Lectura: DENEGADO")
            
        if os.access(path, os.W_OK):
            print(f"  ✓ Escritura: OK")
        else:
            print(f"  ✗ Escritura: DENEGADO")
            
        if os.access(path, os.X_OK):
            print(f"  ✓ Ejecución (navegación): OK")
        else:
            print(f"  ✗ Ejecución (navegación): DENEGADO")
    else:
        print(f"  ✗ No existe")

def main():
    print_section("DIAGNÓSTICO DEL SERVICIO DE MONITOREO")
    
    # 1. Información del usuario actual
    print_section("1. Usuario Actual")
    print(f"Usuario: {os.getenv('USER', 'unknown')}")
    print(f"UID: {os.getuid()}")
    print(f"GID: {os.getgid()}")
    print(f"Grupos: {', '.join([str(g) for g in os.getgroups()])}")
    
    # Verificar si está en el grupo docker
    try:
        result = subprocess.run(['groups'], capture_output=True, text=True)
        if 'docker' in result.stdout:
            print(f"  ✓ Usuario en grupo docker")
        else:
            print(f"  ✗ Usuario NO está en grupo docker")
    except:
        pass
    
    # 2. Permisos de archivos
    print_section("2. Permisos de Archivos")
    check_file_permissions(CONFIG_PATH, "Configuración principal")
    check_file_permissions(MONITOR_CONFIG_PATH, "Configuración del monitor")
    check_file_permissions(ALERT_COOLDOWN_FILE, "Archivo de cooldown")
    check_directory_permissions(LOG_DIR, "Directorio de logs")
    check_directory_permissions('/opt/gvm', "Directorio base")
    check_directory_permissions('/opt/gvm/Monitor', "Directorio Monitor")
    check_directory_permissions('/opt/gvm/Config', "Directorio Config")
    
    # 3. Lectura de configuración
    print_section("3. Lectura de Configuración")
    try:
        with open(CONFIG_PATH, 'r') as f:
            config = json.load(f)
        print(f"  ✓ Configuración principal leída correctamente")
        
        monitoring = config.get('monitoring', {})
        print(f"\n  Sección monitoring:")
        print(f"    enabled: {monitoring.get('enabled', False)}")
        print(f"    alert_cooldown: {monitoring.get('alert_cooldown', 3600)}")
        print(f"    force_send: {monitoring.get('force_send', False)}")
        
        telegram = monitoring.get('telegram', {})
        bot_token = telegram.get('bot_token', '')
        chat_id = telegram.get('chat_id', '')
        
        if bot_token:
            print(f"    bot_token: {bot_token[:10]}...{bot_token[-5:] if len(bot_token) > 15 else ''}")
        else:
            print(f"    ✗ bot_token: NO CONFIGURADO")
            
        if chat_id:
            print(f"    chat_id: {chat_id}")
        else:
            print(f"    ✗ chat_id: NO CONFIGURADO")
    except PermissionError as e:
        print(f"  ✗ Error de permisos: {e}")
    except FileNotFoundError as e:
        print(f"  ✗ Archivo no encontrado: {e}")
    except Exception as e:
        print(f"  ✗ Error: {e}")
    
    # 4. Configuración del monitor (opcional)
    print_section("4. Configuración del Monitor (Opcional)")
    if os.path.exists(MONITOR_CONFIG_PATH):
        try:
            with open(MONITOR_CONFIG_PATH, 'r') as f:
                monitor_config = json.load(f)
            print(f"  ✓ Archivo existe y se puede leer")
            ssh_tunnel = monitor_config.get('ssh_tunnel', {})
            if ssh_tunnel.get('enabled', False):
                print(f"  Túnel SSH: Habilitado")
                print(f"    VPS: {ssh_tunnel.get('vps_host', 'N/A')}")
                print(f"    Usuario: {ssh_tunnel.get('vps_user', 'N/A')}")
            else:
                print(f"  Túnel SSH: Deshabilitado")
        except Exception as e:
            print(f"  ✗ Error al leer: {e}")
    else:
        print(f"  ℹ️  Archivo no existe (opcional, solo necesario si Telegram está bloqueado)")
    
    # 5. Estado del cooldown
    print_section("5. Estado del Cooldown")
    if os.path.exists(ALERT_COOLDOWN_FILE):
        try:
            with open(ALERT_COOLDOWN_FILE, 'r') as f:
                cooldown_data = json.load(f)
            print(f"  ✓ Archivo existe")
            if 'monitoring' in cooldown_data:
                ultimo_envio = datetime.fromisoformat(cooldown_data['monitoring'])
                tiempo_transcurrido = (datetime.now() - ultimo_envio).total_seconds()
                print(f"  Último envío: {ultimo_envio}")
                print(f"  Tiempo transcurrido: {int(tiempo_transcurrido)} segundos ({int(tiempo_transcurrido/60)} minutos)")
                
                # Leer cooldown de configuración
                try:
                    with open(CONFIG_PATH, 'r') as f:
                        config = json.load(f)
                    cooldown_seconds = config.get('monitoring', {}).get('alert_cooldown', 3600)
                    tiempo_restante = cooldown_seconds - tiempo_transcurrido
                    if tiempo_restante > 0:
                        print(f"  ⚠️  Cooldown activo: {int(tiempo_restante)} segundos restantes ({int(tiempo_restante/60)} minutos)")
                    else:
                        print(f"  ✓ Cooldown expirado, se puede enviar")
                except:
                    print(f"  ⚠️  No se pudo leer configuración para calcular tiempo restante")
            else:
                print(f"  ✓ No hay cooldown activo para 'monitoring'")
        except PermissionError as e:
            print(f"  ✗ Error de permisos: {e}")
        except Exception as e:
            print(f"  ✗ Error: {e}")
    else:
        print(f"  ✓ No hay archivo de cooldown (primera ejecución)")
    
    # 6. Verificar Docker
    print_section("6. Acceso a Docker")
    try:
        result = subprocess.run(['docker', 'ps'], capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            print(f"  ✓ Docker accesible")
            print(f"  Salida: {len(result.stdout.splitlines())} líneas")
        else:
            print(f"  ✗ Error al ejecutar docker ps")
            print(f"  Código de salida: {result.returncode}")
            print(f"  Error: {result.stderr}")
    except subprocess.TimeoutExpired:
        print(f"  ✗ Timeout al ejecutar docker")
    except FileNotFoundError:
        print(f"  ✗ Docker no encontrado en PATH")
    except PermissionError:
        print(f"  ✗ Permiso denegado para ejecutar docker")
    except Exception as e:
        print(f"  ✗ Error: {e}")
    
    # 7. Ejecutar el monitor real
    print_section("7. Ejecutar Monitor (Simulación)")
    print("Ejecutando monitor.py como el servicio lo haría...")
    try:
        monitor_script = '/opt/gvm/Monitor/monitor.py'
        if os.path.exists(monitor_script):
            result = subprocess.run(
                ['python3', monitor_script],
                capture_output=True,
                text=True,
                timeout=60
            )
            print(f"\nCódigo de salida: {result.returncode}")
            if result.stdout:
                print(f"\nSalida estándar:")
                print(result.stdout[-1000:])  # Últimos 1000 caracteres
            if result.stderr:
                print(f"\nSalida de error:")
                print(result.stderr[-1000:])  # Últimos 1000 caracteres
        else:
            print(f"  ✗ Script no encontrado: {monitor_script}")
    except subprocess.TimeoutExpired:
        print(f"  ⚠️  Timeout (el script tardó más de 60 segundos)")
    except Exception as e:
        print(f"  ✗ Error: {e}")
    
    print_section("DIAGNÓSTICO COMPLETADO")
    print("\nRecomendaciones:")
    print("1. Verifica que el usuario tenga permisos de lectura en /opt/gvm/Config/config.json")
    print("2. Verifica que el usuario tenga permisos de escritura en /opt/gvm/logs/monitoring/")
    print("3. Verifica que el usuario esté en el grupo docker: sudo usermod -aG docker redteam")
    print("4. Verifica los logs del servicio: sudo journalctl -u openvas-monitor.service -n 50")
    print("5. Ejecuta el servicio manualmente: sudo -u redteam python3 /opt/gvm/Monitor/monitor.py")

if __name__ == '__main__':
    main()







