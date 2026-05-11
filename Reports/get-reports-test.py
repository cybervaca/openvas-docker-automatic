import warnings
# Suprimir warnings de deprecación
warnings.filterwarnings('ignore', category=DeprecationWarning)
warnings.filterwarnings('ignore', category=UserWarning)

import pandas as pd
import getpass
import xml.etree.ElementTree as ET
from gvm.connections import TLSConnection
from gvm.protocols.gmp import Gmp
from gvm.xml import pretty_print
import untangle
import base64
import csv, json
import os, glob
import datetime
import subprocess
import shutil
import smtplib
import socket
import time
import html
import requests
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
import ipaddress
from concurrent.futures import ThreadPoolExecutor, as_completed

REPORTS_DIR = "/opt/gvm/Reports"
CSV_FILE = os.path.join(REPORTS_DIR, "exclusion.csv")
GVM_CONNECTION_TIMEOUT = 900  # Reportes grandes pueden tardar varios minutos en descargarse.
MONITOR_CONFIG_PATH = "/opt/gvm/Monitor/config.json"
SHAREPOINT_UPLOAD_SCRIPT = "/opt/gvm/Reports/subida_share.py"
REPORT_EXPORT_WORKERS = 5

# Función para leer la configuración
def leer_configuracion():
    try:
        with open('/opt/gvm/Config/config.json', 'r') as archivo:
            configuracion = json.load(archivo)
            return configuracion
    except FileNotFoundError:
        print("El archivo 'config.json' no se encontró.")
    except json.JSONDecodeError as e:
        print(f"Error al decodificar el archivo JSON: {e}")
    except Exception as e:
        print(f"Ocurrió un error: {e}")

def leer_configuracion_monitor():
    """Lee configuración opcional del monitor (túnel SOCKS para Telegram)."""
    try:
        if os.path.exists(MONITOR_CONFIG_PATH):
            with open(MONITOR_CONFIG_PATH, 'r') as archivo:
                return json.load(archivo)
    except Exception as e:
        print(f"[WARNING] No se pudo leer {MONITOR_CONFIG_PATH}: {e}")
    return {}

def truncate_text(value, max_chars=1200):
    text = (value or "").strip()
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "... [truncado]"

def crear_tunel_ssh_socks(config_monitor):
    """Crea un túnel SOCKS temporal para Telegram si está configurado."""
    ssh_config = config_monitor.get('ssh_tunnel', {})
    if not ssh_config.get('enabled', False):
        return None

    vps_host = ssh_config.get('vps_host')
    vps_port = ssh_config.get('vps_port', 22)
    vps_user = ssh_config.get('vps_user')
    ssh_key = ssh_config.get('ssh_key_path')
    socks_host = ssh_config.get('socks_host', '127.0.0.1')
    socks_port = ssh_config.get('socks_port', 1080)

    if not vps_host or not vps_user:
        print("[WARNING] Túnel SOCKS habilitado pero incompleto; Telegram se intentará sin proxy")
        return None

    cmd = [
        "ssh",
        "-N",
        "-D", f"{socks_host}:{socks_port}",
        "-o", "StrictHostKeyChecking=no",
        "-o", "ExitOnForwardFailure=yes",
    ]
    if ssh_key:
        cmd.extend(["-i", ssh_key])
    cmd.append(f"{vps_user}@{vps_host}")
    if vps_port:
        cmd.extend(["-p", str(vps_port)])

    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    for _ in range(10):
        if process.poll() is not None:
            stderr = process.stderr.read().decode("utf-8", errors="ignore")
            print(f"[WARNING] No se pudo crear túnel SOCKS: {stderr}")
            return None
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)
            if sock.connect_ex((socks_host, int(socks_port))) == 0:
                sock.close()
                return process
            sock.close()
        except Exception:
            pass
        time.sleep(0.5)

    process.terminate()
    print("[WARNING] Timeout creando túnel SOCKS para Telegram")
    return None

def enviar_telegram_alerta_sharepoint(configuracion, mensaje):
    """Envía alerta Telegram usando la misma configuración que el monitor."""
    monitoring = (configuracion or {}).get('monitoring', {})
    telegram = monitoring.get('telegram', {})
    bot_token = telegram.get('bot_token')
    chat_id = telegram.get('chat_id')

    if not bot_token or not chat_id:
        print("[WARNING] Telegram no configurado; no se envía alerta de SharePoint")
        return False

    config_monitor = leer_configuracion_monitor()
    ssh_process = crear_tunel_ssh_socks(config_monitor)
    ssh_config = config_monitor.get('ssh_tunnel', {})
    proxies = None
    if ssh_process is not None:
        socks_host = ssh_config.get('socks_host', '127.0.0.1')
        socks_port = ssh_config.get('socks_port', 1080)
        proxies = {
            'http': f'socks5://{socks_host}:{socks_port}',
            'https': f'socks5://{socks_host}:{socks_port}'
        }

    try:
        response = requests.post(
            f"https://api.telegram.org/bot{bot_token}/sendMessage",
            json={
                'chat_id': str(chat_id),
                'text': mensaje,
                'parse_mode': 'HTML'
            },
            proxies=proxies,
            timeout=30
        )
        response.raise_for_status()
        print("[OK] Alerta Telegram enviada por fallo de SharePoint")
        return True
    except Exception as e:
        print(f"[ERROR] No se pudo enviar alerta Telegram: {e}")
        return False
    finally:
        if ssh_process is not None:
            ssh_process.terminate()

def format_sharepoint_failure_message(configuracion, file_path, pais, automatizacion, fase, result):
    site = (configuracion or {}).get('site', 'N/A')
    region = (configuracion or {}).get('region', 'N/A')
    scope = (configuracion or {}).get('scope', 'N/A')
    stderr = html.escape(truncate_text(result.stderr))
    stdout = html.escape(truncate_text(result.stdout))
    return (
        "<b>ALERTA: Fallo subida SharePoint OpenVAS</b>\n\n"
        f"<b>País:</b> {html.escape(str(pais))}\n"
        f"<b>Site:</b> {html.escape(str(site))}\n"
        f"<b>Región:</b> {html.escape(str(region))}\n"
        f"<b>Scope:</b> {html.escape(str(scope))}\n"
        f"<b>Fase:</b> {html.escape(str(fase))}\n"
        f"<b>Archivo:</b> <code>{html.escape(str(file_path))}</code>\n"
        f"<b>Destino:</b> {html.escape(str(automatizacion))}\n"
        f"<b>Return code:</b> {result.returncode}\n\n"
        f"<b>STDERR:</b>\n<code>{stderr or 'N/A'}</code>\n\n"
        f"<b>STDOUT:</b>\n<code>{stdout or 'N/A'}</code>"
    )

def upload_sharepoint_or_alert(file_path, pais, automatizacion, fase, configuracion, notify_on_failure=True):
    """Sube a SharePoint y envía Telegram si falla (solo si notify_on_failure=True)."""
    is_exclusion = fase == "exclusion.csv" or os.path.basename(file_path) == "exclusion.csv"
    if is_exclusion:
        if not os.path.isfile(file_path):
            print(
                "[INFO] exclusion.csv no existe (sin exclusiones registradas); "
                "se omite subida a SharePoint."
            )
            return True
        if os.path.getsize(file_path) == 0:
            print("[INFO] exclusion.csv está vacío; se omite subida a SharePoint.")
            return True

    result = subprocess.run([
        "python3", SHAREPOINT_UPLOAD_SCRIPT,
        "-f", file_path,
        "-p", pais,
        "-a", automatizacion
    ], capture_output=True, text=True)

    if result.returncode == 0:
        if result.stdout:
            print(result.stdout)
        return True

    # exclusion.csv: nunca Telegram (falta de fichero o fallo Graph); ver subida_share.py y CHANGELOG.
    alert_telegram = notify_on_failure and not is_exclusion
    level = "[ERROR]" if alert_telegram else "[WARNING]"
    print(f"{level} Fallo subida SharePoint ({fase}): {result.stderr}")
    if alert_telegram:
        mensaje = format_sharepoint_failure_message(
            configuracion,
            file_path,
            pais,
            automatizacion,
            fase,
            result
        )
        enviar_telegram_alerta_sharepoint(configuracion, mensaje)
    return False

# Función para enviar correo electrónico
def email(configuracion):
    smtp_server = configuracion.get('mailserver')
    smtp_user = configuracion.get('smtp_user')
    smtp_pass = configuracion.get('smtp_pass')
    site = configuracion.get('site')
    smtp_port = 587  # Puerto 25 para autenticación anónima
    from_address = configuracion.get('from')
    to_address = configuracion.get('to')
    pais = configuracion.get('pais')
    subject = f'[{pais}-{site}]Openvas Exteno Reportes generados'
    message = """<html>
    <head></head>
    <body>
    <p>Se han generado los reportes. Se procede a subirlos a Sharepoint y Balbix.</p>
    </body>
    </html>
    """
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

# Función para obtener la contraseña
def get_pass():
    password = getpass.getpass(prompt="Enter password: ")
    return password

# Función para conectarse a GVM
def connect_gvm():
    # Conexión TLS a GVM
    connection = TLSConnection(hostname="127.0.0.1", port=9390, timeout=GVM_CONNECTION_TIMEOUT)
    return connection

def export_single_report(report_info, user, password, reportformat, export):
    """Exporta un único reporte usando una conexión GMP dedicada para el thread."""
    reportID = report_info["report_id"]
    task_id = report_info["task_id"]
    name = report_info["task_name"]
    print("Report ID:", reportID)
    print("Task ID:", task_id)
    print("Task Name:", name)
    print("\n")
    print("########{0}-{1}########".format(reportID, name))

    try:
        with Gmp(connection=connect_gvm()) as gmp:
            gmp.authenticate(user, password)
            reportscv = gmp.get_report(
                report_id=reportID,
                report_format_id=reportformat,
                filter_string="apply_overrides=1 min_qod=70 severity>0",
                ignore_pagination=True,
                details=True,
            )

        obj = untangle.parse(reportscv)
        resultID = obj.get_reports_response.report["id"]
        base64CVSData = obj.get_reports_response.report.cdata
        data = str(base64.b64decode(base64CVSData), "utf-8")
        fichero = "{0}/{1}.csv".format(export, resultID)

        if noexiste(fichero):
            guardar(fichero, data)

        if os.path.exists(fichero) and os.path.getsize(fichero) > 0:
            return fichero

        print(f"ADVERTENCIA: No se generó correctamente el fichero {fichero}; se omite")
        return None
    except Exception as e:
        print(f"ADVERTENCIA: Falló export de reporte {reportID} ({name}); se omite: {e}")
        return None

# Función para preparar el reporte
def ready_report(connection, user, password, reportformat, host):
    export = "/opt/gvm/Reports/exports"
    files = []
    with Gmp(connection=connection) as gmp:
        response = gmp.get_version()
        root = ET.fromstring(response)
        status = root.get("status")
        version = root.find("version").text
        print(f"Status: {status}")
        print(f"Version: {version}")
        gmp.authenticate(user, password)
        # Exportar solo el último reporte de cada tarea finalizada. Esto evita
        # recorrer todos los reports históricos y acelera mucho el export.
        respuesta = gmp.get_tasks(filter_string='status="Done" rows=-1')
        result_dict = {}
        root = ET.fromstring(respuesta)
        tasks = root.findall(".//task")
        for task in tasks:
            task_id = task.get("id")
            task_name = task.findtext("name")
            report = task.find(".//last_report/report")
            if report is None:
                continue
            report_id = report.get("id")
            if not report_id:
                continue
            result_dict[report_id] = {
                "report_id": report_id,
                "task_id": task_id,
                "task_name": task_name,
            }

        if not result_dict:
            print("No se encontraron reportes finalizados para exportar")
            return

        print(f"Exportando {len(result_dict)} reportes con {REPORT_EXPORT_WORKERS} threads...")
        with ThreadPoolExecutor(max_workers=REPORT_EXPORT_WORKERS) as executor:
            futures = [
                executor.submit(export_single_report, value, user, password, reportformat, export)
                for value in result_dict.values()
            ]
            for future in as_completed(futures):
                fichero = future.result()
                if fichero:
                    files.append(fichero)

        if files:
            delete_duplicates(files, export, host)
        else:
            print("No hay ficheros que unificar")

# Función para comprobar si un fichero existe
def noexiste(fichero):
    if os.path.exists(fichero):
        print("ya existe")
        return False
    else:
        return True

# Función para guardar datos en un fichero
def guardar(fichero, data):
    os.makedirs(os.path.dirname(fichero), exist_ok=True)
    with open(fichero, "w") as f:
        f.write(data)

def get_excluded_ips(gmp, target_id):
    """Obtiene las IPs excluidas de un target."""
    respuesta_target = gmp.get_target(target_id=target_id)
    root_target = ET.fromstring(respuesta_target)

    exclusions = []
    for tag in ["exclude", "exclude_hosts", "hosts_excluded"]:
        exclusions_elem = root_target.find(f".//{tag}")
        if exclusions_elem is not None and exclusions_elem.text:
            exclusions.extend([ip.strip() for ip in exclusions_elem.text.split(',') if ip.strip()])
    return exclusions

def load_existing_records():
    """Carga los registros existentes del CSV."""
    existing_records = []
    if os.path.exists(CSV_FILE):
        with open(CSV_FILE, 'r') as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                existing_records.append((row['task_name'], row['excluded_ips']))
    return existing_records



# Función para eliminar duplicados y unificar archivos
def delete_duplicates(files, export, host):
    configuracion = leer_configuracion()
    pais =  configuracion.get("pais")
    now = datetime.datetime.now()
    year = now.year
    month = now.month
    day = now.day
    hour = now.hour
    minute = now.minute
    nombre_archivo = f"{export}/{year:04d}_{month:02d}_{day:02d}_{hour:02d}_{minute:02d}.csv"
    dataframes = []
    for file in files:
        if not os.path.exists(file):
            print(f"ADVERTENCIA: Fichero de reporte no encontrado, se omite: {file}")
            continue
        if os.path.getsize(file) == 0:
            print(f"ADVERTENCIA: Fichero de reporte vacío, se omite: {file}")
            continue
        try:
            dataframes.append(pd.read_csv(file))
        except Exception as e:
            print(f"ADVERTENCIA: No se pudo leer {file}, se omite: {e}")
    if not dataframes:
        print("No hay ficheros CSV válidos para unificar")
        return
    columnas = ["IP", "Hostname", "Port", "Port Protocol", "CVSS", "NVT Name", "Summary", "Specific Result", "CVEs", "Solution"]
    dataframe = pd.concat(dataframes, ignore_index=True)[columnas]
    dataframe = dataframe.drop_duplicates()
    dataframe.to_csv(nombre_archivo, index=False)
    file_unif, file_excel = vulns_ip(nombre_archivo, host)
    
    #solo para la externa
    #print("Lanzamos subida a balbix")
    #subprocess.run(["python3", "/opt/gvm/Reports/upload-reports.py"] + [file_unif])
    #fin externa
    #enviamos sharepoint
    upload_sharepoint_or_alert(file_unif, pais, 'Openvas_Interno', 'reporte csv', configuracion)
    upload_sharepoint_or_alert(file_excel, pais, 'Openvas_Interno', 'reporte xlsx', configuracion)
    separar_cve(file_unif)

# Función para separar CVEs y misconfiguraciones
def separar_cve(nombre_archivo):
    try:
        df = pd.read_csv(nombre_archivo)
        con_info = df[df['CVEs'].notnull()]
        sin_info = df[df['CVEs'].isnull()]
        con_info.to_csv(nombre_archivo.replace('.csv', '_CVE.csv'), index=False)
        sin_info.to_csv(nombre_archivo.replace('.csv', '_Misconfigs.csv'), index=False)
        ficheros = [nombre_archivo.replace('.csv', '_CVE.csv'), nombre_archivo.replace('.csv', '_Misconfigs.csv')]
        print("Ya no sube a Balbix, se mantiene para la subida a Valbix")
        subprocess.run(["python3", "/opt/gvm/Reports/upload-reports.py"] + ficheros)
    except pd.errors.ParserError as pe:
        print(f"Error de análisis al procesar el archivo CSV: {pe}")
    except Exception as e:
        print(f"Error general al procesar el archivo CSV: {e}")

# Función para obtener el formato de reporte
def get_reportformat(connection, username, password):
    with Gmp(connection=connection) as gmp:
        gmp.authenticate(username, password)
        report_format = gmp.get_report_formats()
        report_root = ET.fromstring(report_format)
        reportsformat = report_root.findall(".//report_format")
        for report in reportsformat:
            id = report.get("id")
            name = report.find("name").text
            if name == "CSV Results":
                return id

# Función para obtener los hosts
def get_hosts(origen, destino):
    """
    Extrae información de hosts y sistemas operativos desde PostgreSQL.
    Intenta primero conexión directa localhost:5432, luego docker exec, luego conexión local.
    """
    if os.path.exists(origen):
        comando = f'sudo rm {origen}'
        subprocess.run(comando, shell=True)
    if os.path.exists(destino):
        os.remove(destino)
    
    # 1. Intentar conexión directa a localhost:5432 (puerto expuesto del contenedor)
    comando_directo = f"""
    psql -h 127.0.0.1 -U postgres -d gvmd -c \
    "\\copy (SELECT DISTINCT hosts.name AS IP, oss.name AS sistema_operativo \
    FROM host_oss \
    JOIN hosts ON host_oss.host = hosts.id \
    JOIN oss ON host_oss.os = oss.id) TO '{origen}' WITH CSV HEADER;"
    """
    
    # Configurar PGPASSWORD para evitar prompt de contraseña
    env = os.environ.copy()
    env['PGPASSWORD'] = 'admin'  # Contraseña por defecto del contenedor OpenVAS
    
    result_directo = subprocess.run(comando_directo, shell=True, capture_output=True, text=True, env=env)
    
    if result_directo.returncode == 0 and os.path.exists(origen):
        shutil.copyfile(origen, destino)
        print(f"✓ Información de hosts extraída exitosamente desde PostgreSQL (conexión directa)")
        return
    
    # 2. Fallback: intentar con docker exec (PostgreSQL dentro del contenedor)
    comando_docker = f"""
    docker exec openvas sudo -u postgres psql -U postgres -d gvmd -c \
    "\\copy (SELECT DISTINCT hosts.name AS IP, oss.name AS sistema_operativo \
    FROM host_oss \
    JOIN hosts ON host_oss.host = hosts.id \
    JOIN oss ON host_oss.os = oss.id) TO '/tmp/hosts.csv' WITH CSV HEADER;"
    """
    
    result = subprocess.run(comando_docker, shell=True, capture_output=True, text=True)
    
    if result.returncode == 0:
        # Copiar el archivo desde el contenedor
        subprocess.run(f"docker cp openvas:/tmp/hosts.csv {destino}", shell=True)
        print(f"✓ Información de hosts extraída exitosamente desde el contenedor")
        return
    
    # 3. Fallback: intentar conexión local (si PostgreSQL está disponible localmente)
    comando_postgresql = f"""
    sudo -u postgres -H sh -c "psql -U postgres -d gvmd -c \
    '\\copy (SELECT DISTINCT hosts.name AS IP, oss.name AS sistema_operativo \
    FROM host_oss \
    JOIN hosts ON host_oss.host = hosts.id \
    JOIN oss ON host_oss.os = oss.id) TO '{origen}' WITH CSV HEADER;'"
    """
    result_local = subprocess.run(comando_postgresql, shell=True, capture_output=True, text=True)
    
    if result_local.returncode == 0:
        shutil.copyfile(origen, destino)
        print(f"✓ Información de hosts extraída exitosamente desde PostgreSQL local")
        return
    
    # 4. Si todo falla, crear archivo vacío con headers
    print(f"⚠ No se pudo extraer información de SO desde PostgreSQL")
    print(f"  Los reportes se generarán sin información de sistema operativo")
    with open(destino, 'w') as f:
        f.write("ip,sistema_operativo\n")

# Función para cargar rangos de IP y países desde un archivo CSV
def cargar_rangos_ip(archivo):
    rangos_ip = []
    with open(archivo, 'r') as f:
        reader = csv.reader(f, delimiter=';')
        next(reader)  # Saltar el encabezado
        for row in reader:
            rango = ipaddress.ip_network(row[1], strict=False)
            pais = row[2]
            rangos_ip.append((rango, pais))
    return rangos_ip

# Función para consultar el país de una IP
def consultar_pais(ip, rangos_ip):
    ip_address = ipaddress.ip_address(ip.strip())
    for rango, pais in rangos_ip:
        if ip_address in rango:
            return pais
    return 'Desconocido'

# Función para determinar la severidad basada en el CVSS
def determinar_severidad(cvss):
    try:
        cvss = float(cvss)
        if cvss >= 9:
            return 'Critical'
        elif cvss >= 7:
            return 'High'
        elif cvss >= 4:
            return 'Medium'
        elif cvss >= 1:
            return 'Low'
        else:
            return 'Info'
    except ValueError:
        return 'Info'

def vulns_ip(vulns, host):
    export = '/opt/gvm/Reports/exports/vulns_host'
    now = datetime.datetime.now()
    year = now.year
    month = now.month
    day = now.day
    hour = now.hour
    minute = now.minute
    nombre_archivo_csv = f"{export}/{year:04d}_{month:02d}_{day:02d}_{hour:02d}_{minute:02d}.csv"
    nombre_archivo_xlsx = f"{export}/{year:04d}_{month:02d}_{day:02d}_{hour:02d}_{minute:02d}.xlsx"
    df_ips = pd.read_csv(vulns)
    df_sistemas = pd.read_csv(host)
    sistemas_operativos = []
    #rangos_ip = cargar_rangos_ip('/opt/gvm/Targets_Tasks/openvas_externa.csv')  # Cambia esta ruta al archivo CSV con los rangos de IP y países
    paises = []
    severidades = []
    regiones = []
    pais_region_map = {
            'COLOMBIA': 'SUR',
            'PERU': 'SUR',
            'ARGENTINA': 'SUR',
            'CHILE': 'SUR',
            'BAAGRI': 'NORTE',
            'EMEA': 'EMEA',
            'USNS': 'NORTE',
            'MEXICO': 'NORTE',
            'GUATEMALA': 'NORTE',
            'EL_SALVADOR': 'NORTE',
            'PUERTO_RICO': 'NORTE',
            'INTERFILE': 'BRASIL',
            'BRASIL': 'BRASIL'
        }
    for ip, cvss in zip(df_ips['IP'], df_ips['CVSS']):
        sistema = df_sistemas[df_sistemas['ip'] == ip]['sistema_operativo'].values
        if len(sistema) > 0:
            sistemas_operativos.append(sistema[0])
        else:
            sistemas_operativos.append('No encontrado')
        #pais = consultar_pais(ip, rangos_ip)
        #pais = pais.strip()
        pais = configuracion.get('pais')
        paises.append(pais)
        severidad = determinar_severidad(cvss)
        severidades.append(severidad)
        regiones.append(pais_region_map[pais.upper()])
    
    df_ips['sistema_operativo'] = sistemas_operativos
    df_ips['Region'] = configuracion.get('region')
    df_ips['Country'] = configuracion.get('pais')
    df_ips['Scope'] = configuracion.get('scope')
    df_ips['Process'] = 'redteam-scan'
    df_ips['Owner'] = ''
    df_ips['solucion_propuesta'] = df_ips['Solution']
    df_ips['issue_type_severity'] = severidades
    df_ips = df_ips.drop(columns=['Solution'])
    df_ips.to_csv(nombre_archivo_csv, index=False)
    df_ips.to_excel(nombre_archivo_xlsx, index=False)
    return nombre_archivo_csv,nombre_archivo_xlsx

def get_tasks_and_exclusions(connection, user, password, pais):
    """Obtiene las tareas y extrae las IPs excluidas de sus targets asociados."""
    # Cargar registros existentes
    existing_records = load_existing_records()
    
    with Gmp(connection=connection) as gmp:
        gmp.authenticate(user, password)

        # Obtener todas las tareas
        respuesta = gmp.get_tasks(filter_string='rows=-1')
        root = ET.fromstring(respuesta)

        # Preparar nuevos registros
        new_records = []
        for task_elem in root.findall(".//task"):
            name = task_elem.findtext("name")
            
            # Obtener target asociado
            target_elem = task_elem.find(".//target")
            if target_elem is not None:
                target_id = target_elem.get("id")
                excluded_ips = get_excluded_ips(gmp, target_id)
            else:
                excluded_ips = []

            # Solo procesar si hay IPs excluidas
            if excluded_ips:
                ips_str = ', '.join(sorted(excluded_ips))  # Ordenamos para consistencia
                # Comprobar si ya existe este registro
                if (name, ips_str) not in existing_records:
                    new_records.append({
                        'task_name': name,
                        'excluded_ips': ips_str,
                        'date': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    })

        # Escribir nuevos registros si los hay
        if new_records:
            file_exists = os.path.exists(CSV_FILE)
            with open(CSV_FILE, 'a', newline='') as csvfile:
                fieldnames = ['task_name', 'excluded_ips', 'date']
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                
                # Escribir encabezado solo si el archivo no existía
                if not file_exists:
                    writer.writeheader()
                writer.writerows(new_records)
                
        configuracion = leer_configuracion()
        upload_sharepoint_or_alert(
            CSV_FILE,
            pais,
            'Openvas_Interno',
            'exclusion.csv',
            configuracion,
            notify_on_failure=False,
        )

if __name__ == "__main__":
    dir_csv = '/opt/gvm/Reports/exports/'
    csv_files = glob.glob(os.path.join(dir_csv, '*.csv'))
    for csv_file in csv_files:
        try:
            os.remove(csv_file)
            print(f'Se ha borrado el archivo: {csv_file}')
        except OSError as e:
            print(f'Error al borrar el archivo {csv_file}: {e.strerror}')
    origen = '/tmp/hosts.csv'
    destino = '/opt/gvm/Reports/hosts.csv'
    configuracion = leer_configuracion()
    username = configuracion.get('user')
    password = configuracion.get('password')
    pais = configuracion.get('pais')
    connection = connect_gvm()
    get_hosts(origen, destino)
    get_tasks_and_exclusions(connection, username, password, pais)
    reportformat = get_reportformat(connection, username, password)
    ready_report(connection, username, password, reportformat, destino)
    #email(configuracion)
    print("finalizado")
