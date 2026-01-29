import requests
import json
import subprocess
import smtplib
import os
import shutil
import argparse
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

def email(version, configuracion, resultado):
    smtp_server = configuracion.get('mailserver')
    smtp_user = configuracion.get('smtp_user')
    smtp_pass = configuracion.get('smtp_pass')
    smtp_port = 587  # Puerto 25 para autenticación anónima
    from_address = configuracion.get('from')
    site = configuracion.get('site')
    to_address = configuracion.get('to')
    pais = configuracion.get('pais')
    subject = f'[{pais}-{site}]Script automatizado de Openvas actualizado {version}'
    message = f'''<html>
    <head></head>
    <body>
    <p>El script automatizado de openvas se ha actualizado con el siguiente resultado:</p>
    <p>{resultado}</p>
    </body>
    </html>
    '''
    msg = MIMEMultipart()
    msg['From'] = from_address
    msg['To'] = to_address
    msg['Subject'] = subject
    msg.attach(MIMEText(message, 'html'))
#    smtp = smtplib.SMTP(smtp_server, smtp_port)
#    smtp.sendmail(from_address, to_address, msg.as_string())
#    smtp.quit()
    try:
        # Establece la conexión con el servidor
        smtp = smtplib.SMTP(smtp_server, smtp_port)
        smtp.ehlo()  # Identifícate con el servidor
        smtp.starttls()  # Inicia la conexión TLS
        smtp.ehlo()  # Vuelve a identificarse como una conexión segura
        smtp.login(smtp_user, smtp_pass)  # Inicia sesión en el servidor SMTP

        # Envía el correo
        smtp.sendmail(from_address, to_address, msg.as_string())
        print("Correo enviado exitosamente.")
    except Exception as e:
        print(f"Error al enviar el correo: {e}")
    finally:
        # Cierra la conexión
        smtp.quit()


def get_version_github(url):
    try:
        response = requests.get(url)
        if response.status_code == 200:
            json_data = response.json()
            version = json_data.get("version")
            if version:
                return version
            else:
                print("No se encontró la clave 'version' en el JSON.")
                return 0
        else:
            print(f"Error en la solicitud. Código de estado: {response.status_code}")
            return 0
    except Exception as e:
        print(f"Error: {e}")
        return 0
        
def leer_configuracion(fichero):
    try:
        with open(fichero, 'r') as archivo:
            configuracion = json.load(archivo)
            return configuracion
    except FileNotFoundError:
        print("El archivo 'config.json' no se encontró.")
        return 0
    except json.JSONDecodeError as e:
        print(f"Error al decodificar el archivo JSON: {e}")
        return 0
    except Exception as e:
        print(f"Ocurrió un error: {e}")
        return 0

def descargar_archivo(url, destino):
    """Descarga un archivo desde una URL y lo guarda en el destino especificado"""
    try:
        response = requests.get(url)
        if response.status_code == 200:
            # Crear directorio si no existe
            os.makedirs(os.path.dirname(destino), exist_ok=True)
            with open(destino, 'wb') as f:
                f.write(response.content)
            print(f"Archivo descargado: {destino}")
            # Hacer el archivo ejecutable si es un script Python
            if destino.endswith('.py'):
                os.chmod(destino, 0o755)
            return True
        else:
            print(f"Error al descargar: código {response.status_code}")
            return False
    except Exception as e:
        print(f"Error al descargar archivo: {e}")
        return False

def ejecutar_export_target():
    """Ejecuta export-target.py y guarda el resultado en openvas.csv.export"""
    try:
        script_path = '/opt/gvm/Targets_Tasks/export-target.py'
        output_path = '/opt/gvm/Targets_Tasks/openvas.csv.export'
        config_path = '/opt/gvm/Config/config.json'
        
        # Ejecutar export-target.py
        resultado = subprocess.run(
            ['python3', script_path, '-c', config_path, '-o', output_path],
            cwd='/opt/gvm/Targets_Tasks/',
            capture_output=True,
            text=True
        )
        
        if resultado.returncode == 0:
            print(f"Export completado: {output_path}")
            return True
        else:
            print(f"Error al ejecutar export-target.py: {resultado.stderr}")
            return False
    except Exception as e:
        print(f"Error al ejecutar export-target: {e}")
        return False

def git_pull_forzado(repo_path):
    """Hace un git pull forzado, descartando cambios locales"""
    try:
        # Primero hacer reset hard para descartar cambios locales
        subprocess.run(['git', 'reset', '--hard', 'HEAD'], cwd=repo_path, check=True)
        # Luego hacer fetch
        subprocess.run(['git', 'fetch', 'origin'], cwd=repo_path, check=True)
        # Finalmente hacer reset hard al origin/main para forzar la actualización
        subprocess.run(['git', 'reset', '--hard', 'origin/main'], cwd=repo_path, check=True)
        print("Git pull forzado completado")
        return True
    except subprocess.CalledProcessError as e:
        print(f"Error en git pull forzado: {e}")
        return False
    except Exception as e:
        print(f"Error inesperado en git pull: {e}")
        return False

def verificar_cambios_remotos(repo_path):
    """Verifica si hay cambios remotos disponibles"""
    try:
        # Hacer fetch para obtener información de cambios remotos
        subprocess.run(['git', 'fetch', 'origin'], cwd=repo_path, check=True, 
                      capture_output=True, text=True, stderr=subprocess.DEVNULL)
        # Comparar HEAD local con origin/main
        resultado = subprocess.run(
            ['git', 'rev-list', '--count', 'HEAD..origin/main'],
            cwd=repo_path,
            capture_output=True,
            text=True
        )
        if resultado.returncode == 0 and resultado.stdout.strip():
            commits_ahead = int(resultado.stdout.strip())
            if commits_ahead > 0:
                print(f"Se detectaron {commits_ahead} commit(s) remoto(s) disponible(s)")
                return True
        return False
    except subprocess.CalledProcessError:
        # Si falla, asumir que hay cambios para ser seguros
        return True
    except Exception as e:
        print(f"Error al verificar cambios remotos: {e}")
        # En caso de error, asumir que hay cambios para ser seguros
        return True

def proceso_actualizacion():
    """Ejecuta el proceso completo de actualización"""
    config = leer_configuracion('/opt/gvm/Config/config.json')
    
    # Paso 1: Descargar export-target.py desde GitHub
    print("Paso 1: Descargando export-target.py...")
    url_export_target = "https://raw.githubusercontent.com/cybervaca/openvas-docker-automatic/refs/heads/main/Targets_Tasks/export-target.py"
    destino_export_target = "/opt/gvm/Targets_Tasks/export-target.py"
    if not descargar_archivo(url_export_target, destino_export_target):
        print("Error: No se pudo descargar export-target.py")
        return False
    
    # Paso 2: Ejecutar export-target.py y guardar en openvas.csv.export
    print("Paso 2: Ejecutando export-target.py...")
    if not ejecutar_export_target():
        print("Error: No se pudo ejecutar export-target.py")
        return False
    
    # Paso 3: Hacer git pull forzado
    print("Paso 3: Haciendo git pull forzado...")
    if not git_pull_forzado('/opt/gvm/'):
        print("Error: No se pudo hacer git pull forzado")
        return False
    
    # Paso 4: Copiar el backup a openvas.csv
    print("Paso 4: Restaurando openvas.csv desde backup...")
    backup_path = '/opt/gvm/Targets_Tasks/openvas.csv.export'
    destino_csv = '/opt/gvm/Targets_Tasks/openvas.csv'
    try:
        if os.path.exists(backup_path):
            shutil.copy2(backup_path, destino_csv)
            print(f"Backup restaurado: {destino_csv}")
        else:
            print(f"Advertencia: No se encontró el archivo de backup {backup_path}")
    except Exception as e:
        print(f"Error al restaurar backup: {e}")
    
    print("Actualización completada exitosamente")
    return True

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Script de actualización automática de OpenVAS"
    )
    parser.add_argument(
        '--force',
        action='store_true',
        help='Forzar actualización incluso si la versión es la misma'
    )
    args = parser.parse_args()
    
    url_github = "https://raw.githubusercontent.com/cybervaca/openvas-docker-automatic/main/Config/config_example.json"
    version_github = get_version_github(url_github)
    configuracion = leer_configuracion('/opt/gvm/Config/config_example.json')
    version_local = configuracion.get('version')
    
    # Verificar si hay cambios remotos disponibles
    hay_cambios_remotos = verificar_cambios_remotos('/opt/gvm/')
    
    # Si se fuerza la actualización, ejecutarla directamente
    if args.force:
        print("Modo forzado: ejecutando actualización...")
        proceso_actualizacion()
    elif(version_github == 0 or version_local == 0):
        print("No se puede comprobar la version")
        # Si hay cambios remotos, ejecutar actualización de todas formas
        if hay_cambios_remotos:
            print("Se detectaron cambios remotos, ejecutando actualización...")
            proceso_actualizacion()
    else:
        if(version_github==version_local):
            print("Misma version")
            # Si hay cambios remotos aunque la versión sea la misma, ejecutar actualización
            if hay_cambios_remotos:
                print("Se detectaron cambios remotos, ejecutando actualización...")
                proceso_actualizacion()
        else:
            print("Diferente version")
            proceso_actualizacion()
    
