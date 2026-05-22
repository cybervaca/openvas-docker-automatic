import warnings
# Suprimir warnings de deprecación de paramiko y gvm
warnings.filterwarnings('ignore', category=DeprecationWarning)
warnings.filterwarnings('ignore', category=UserWarning)

from gvm.connections import TLSConnection
from gvm.protocols.gmp import Gmp
from gvm.errors import GvmError
import xml.etree.ElementTree as ET
import getpass
import datetime
import smtplib
import os, json
import sys
import argparse
import subprocess
import time
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders

GVM_CONNECTION_TIMEOUT = 900  # Listar muchas tareas/reportes puede tardar más de 60s.
SHAREPOINT_UPLOAD_SCRIPT = "/opt/gvm/Reports/subida_share.py"

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

def get_pass():
    password = getpass.getpass(prompt="Enter password: ")
    return password

def write_log(mensaje, log):
    mensaje_tiempo=f"{datetime.datetime.now()} - {mensaje}\n"
    with open(log, "a") as archivo:
        archivo.write(mensaje_tiempo)
        print(mensaje_tiempo)
        
def email(file1, file2, configuracion):
    smtp_server = configuracion.get('mailserver')
    smtp_user = configuracion.get('smtp_user')
    smtp_pass = configuracion.get('smtp_pass')
    site = configuracion.get('site')
    smtp_port = 587  # Puerto 25 para autenticación anónima
    from_address = configuracion.get('from')
    to_address = configuracion.get('to')
    pais = configuracion.get('pais')
    subject = f'[{pais}-{site}]Openvas tasks finalizadas'
    message = """<html>
    <head></head>
    <body>
    <p>Se han finalizado las tasks de la region. Se procede a las subidas y eliminar reports.</p>
    </body>
    </html>
    """
    msg = MIMEMultipart()
    msg['From'] = from_address
    msg['To'] = to_address
    msg['Subject'] = subject
    msg.attach(MIMEText(message, 'html'))
    # Adjuntar file1.txt
    file1_attachment = open(file1, 'rb')
    file1_mime = MIMEBase('application', 'octet-stream')
    file1_mime.set_payload(file1_attachment.read())
    encoders.encode_base64(file1_mime)
    file1_mime.add_header('Content-Disposition', f'attachment; filename=tasksend.txt')
    msg.attach(file1_mime)
    file1_attachment.close()

    # Adjuntar file2.txt
    file2_attachment = open(file2, 'rb')
    file2_mime = MIMEBase('application', 'octet-stream')
    file2_mime.set_payload(file2_attachment.read())
    encoders.encode_base64(file2_mime)
    file2_mime.add_header('Content-Disposition', f'attachment; filename=taskslog.txt')
    msg.attach(file2_mime)
    file2_attachment.close()
    #smtp = smtplib.SMTP(smtp_server, smtp_port)
    #smtp.sendmail(from_address, to_address, msg.as_string())
    #smtp.quit()
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

def connect_gvm():
    # Conexión TLS a GVM
    connection = TLSConnection(hostname="127.0.0.1", port=9390, timeout=GVM_CONNECTION_TIMEOUT)
    return connection


def verificar_mantenimiento_activo():
    """
    Verifica si hay un mantenimiento en curso consultando el archivo de lock.
    
    Returns:
        tuple: (bool, str) - (True si hay mantenimiento activo, mensaje descriptivo)
    """
    lock_file = '/opt/gvm/.maintenance.lock'
    
    if not os.path.exists(lock_file):
        return False, ""
    
    try:
        with open(lock_file, 'r') as f:
            lock_data = json.load(f)
        
        timestamp_str = lock_data.get('timestamp', '')
        pid = lock_data.get('pid', 0)
        
        # Verificar si el proceso aún está corriendo
        try:
            os.kill(pid, 0)  # No mata el proceso, solo verifica si existe
            # El proceso existe, el mantenimiento está activo
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
                os.remove(lock_file)
            except Exception:
                pass
            return False, "Lock obsoleto eliminado"
    except Exception as e:
        # Si hay error al leer el lock, asumir que no está activo
        return False, f"Error al leer lock: {e}"


def ejecutar_operacion_gmp(operacion_func, user, password, max_intentos=3, delay=2):
    """
    Ejecuta una operación GMP con reintentos en caso de error de conexión.
    Crea una nueva conexión en cada intento.
    
    Args:
        operacion_func: Función que recibe un objeto Gmp y ejecuta la operación
        user: Usuario GVM
        password: Contraseña GVM
        max_intentos: Número máximo de intentos
        delay: Tiempo de espera entre intentos (segundos)
    
    Returns:
        Resultado de la operación
    """
    ultimo_error = None
    for intento in range(1, max_intentos + 1):
        try:
            # Crear nueva conexión para cada intento
            nueva_conexion = connect_gvm()
            with Gmp(connection=nueva_conexion) as gmp:
                gmp.authenticate(user, password)
                return operacion_func(gmp)
        except GvmError as e:
            ultimo_error = e
            error_str = str(e)
            if "Remote closed the connection" in error_str or "Connection" in error_str:
                if intento < max_intentos:
                    print(f"⚠️  Error de conexión GVM (intento {intento}/{max_intentos}). Reintentando en {delay}s...")
                    time.sleep(delay)
                    continue
            # Si no es un error de conexión o se agotaron los intentos, relanzar
            raise
        except TimeoutError as e:
            ultimo_error = e
            if intento < max_intentos:
                print(f"⚠️  Timeout leyendo respuesta GVM (intento {intento}/{max_intentos}). Reintentando en {delay}s...")
                time.sleep(delay)
                continue
            raise
        except Exception:
            # Para otros errores, no reintentar
            raise
    
    # Si llegamos aquí, todos los intentos fallaron
    raise ultimo_error


def start_task(connection, user, password, configuracion, mensual=False):
    informacion_tareas = []
    logfinal='/opt/gvm/tasksend.txt'
    tasklog='/opt/gvm/taskslog.txt'
    
    # Verificar si hay mantenimiento en curso antes de ejecutar tareas nuevas
    mantenimiento_activo, mensaje = verificar_mantenimiento_activo()
    if mantenimiento_activo:
        write_log(f"MANTENIMIENTO EN CURSO: No se pueden ejecutar tareas nuevas. {mensaje}", tasklog)
        print(f"⚠ MANTENIMIENTO EN CURSO: {mensaje}")
        print("No se ejecutarán tareas nuevas hasta que el mantenimiento finalice.")
        return 3  # Nuevo código de retorno para mantenimiento activo

    if mensual:
        proc = subprocess.run(
            [sys.executable, SHAREPOINT_UPLOAD_SCRIPT, "--check-mensual"],
            capture_output=True,
            text=True,
        )
        if proc.stdout:
            for line in proc.stdout.splitlines():
                print(line)
        if proc.returncode == 0:
            write_log(
                "MODO MENSUAL: Ya existe informe en SharePoint este mes. No se ejecutan tareas nuevas.",
                tasklog,
            )
            print("⚠ MODO MENSUAL: informe del mes ya presente en SharePoint; no se lanzan tareas nuevas.")
            return 4
        if proc.returncode == 2:
            err = (proc.stderr or "").strip() or "Error desconocido al consultar SharePoint"
            write_log(
                f"ADVERTENCIA MODO MENSUAL: falló la comprobación SharePoint; se continúa (fail-open). {err}",
                tasklog,
            )
            print(f"⚠ MODO MENSUAL: no se pudo verificar SharePoint; se continúa el flujo.\n{err}")
        elif proc.returncode != 1:
            err = (proc.stderr or "").strip() or f"código de salida {proc.returncode}"
            write_log(
                f"ADVERTENCIA MODO MENSUAL: respuesta inesperada de subida_share.py; se continúa. {err}",
                tasklog,
            )
            print(f"⚠ MODO MENSUAL: comprobación SharePoint devolvió {proc.returncode}; se continúa.\n{err}")
    
    try:
        # Verificar tareas en ejecución
        respuesta = ejecutar_operacion_gmp(
            lambda gmp: gmp.get_tasks(filter_string='status="Running" status="Requested" status="Queued"'),
            user, password
        )
        root = ET.fromstring(respuesta)
        for task_elem in root.findall(".//task"):
            task_id = task_elem.get("id")
            name = task_elem.findtext("name")
            status = task_elem.findtext("status")
            if(status=='Running' or status=='Requested' or status=='Queued'):
                write_log("La tarea {0} con id {1} está corriendo aun. Finalizamos script.".format(name,task_id),tasklog)
                return 1
        
        # Verificar tareas nuevas
        respuesta = ejecutar_operacion_gmp(
            lambda gmp: gmp.get_tasks(filter_string='status="New"'),
            user, password
        )
        root = ET.fromstring(respuesta)
        for task_elem in root.findall(".//task"):
            task_id = task_elem.get("id")
            name = task_elem.findtext("name")
            status = task_elem.findtext("status")
            if(status=='New'):
                write_log("Arrancamos la tarea {0} con id {1}".format(name,task_id),tasklog)
                starttask = ejecutar_operacion_gmp(
                    lambda gmp: gmp.start_task(task_id),
                    user, password
                )
                write_log(starttask, tasklog)
                return 2
        
        # Obtener todas las tareas
        respuesta = ejecutar_operacion_gmp(
            lambda gmp: gmp.get_tasks(filter_string='rows=-1'),
            user, password
        )
        root = ET.fromstring(respuesta)
        for task_elem in root.findall(".//task"):
            task_id = task_elem.get("id")
            name = task_elem.findtext("name")
            status = task_elem.findtext("status")
            current_report_elem = task_elem.find(".//last_report/report")
            if current_report_elem is not None:
                report_id = current_report_elem.get("id")
                timestamp = current_report_elem.findtext("timestamp")
                scan_start = current_report_elem.findtext("scan_start")
                scan_end = current_report_elem.findtext("scan_end")
                print("Task ID:", task_id)
                print("Name:", name)
                print("Status:", status)
                print("Report ID:", report_id)
                print("Timestamp:", timestamp)
                print("Scan Start:", scan_start)
                print("Scan End:", scan_end)
                print("-----------------------------")
                informacion_tarea = {
                        "report_id": report_id,
                        "name": name,
                        "status": status,
                        "timestamp": timestamp,
                        "scan_start": scan_start,
                        "scan_end": scan_end
                }
                informacion_tareas.append(informacion_tarea)
        
        if os.path.exists(logfinal):
            return 0
        else:
            #enviar email una vez finalizado con los logs y los reportes.
            with open(logfinal, "w") as archivo:
                for informacion_tarea in informacion_tareas:
                    archivo.write(str(informacion_tarea) + "\n")
            print("Todas las tareas finalizadas")
            #email(logfinal, tasklog, configuracion)
            print("Exportamos las tasks")
            subprocess.run(["python3", "/opt/gvm/Reports/get-reports-test.py"])
        return 0
    
    except GvmError as e:
        write_log(f"ERROR: Error de conexión GVM después de múltiples intentos: {e}", tasklog)
        print(f"❌ Error de conexión GVM: {e}")
        raise
    except Exception as e:
        write_log(f"ERROR: Error inesperado: {e}", tasklog)
        print(f"❌ Error inesperado: {e}")
        raise

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Orquestación de tareas OpenVAS / GVM")
    parser.add_argument(
        "--mensual",
        action="store_true",
        help="Si ya hay informe CSV/XLSX del mes en SharePoint, no iniciar tareas nuevas ni get-reports-test",
    )
    args = parser.parse_args()

    configuracion = leer_configuracion()
    user = configuracion.get('user')
    password = configuracion.get('password')
    connection = connect_gvm()
    resultado = start_task(connection, user, password, configuracion, mensual=args.mensual)
    if resultado == 0:
        print("Finalizamos sin lanzar")
    elif resultado == 1:
        print("Ya hay una corriendo")
    elif resultado == 2:
        print("Arrancamos una nueva")
    elif resultado == 3:
        print("Mantenimiento en curso: no se pueden ejecutar tareas nuevas")
    elif resultado == 4:
        print("Modo mensual: ya existe informe en SharePoint este mes; no se ejecutan tareas nuevas")

