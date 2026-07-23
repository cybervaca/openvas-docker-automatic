#!/usr/bin/env python3
"""Arranca una tarea GVM/OpenVAS por nombre exacto (sin distinguir mayúsculas)."""
import warnings

warnings.filterwarnings("ignore", category=DeprecationWarning)
warnings.filterwarnings("ignore", category=UserWarning)

import argparse
import datetime
import json
import os
import sys
import time
import xml.etree.ElementTree as ET

from gvm.connections import TLSConnection
from gvm.errors import GvmError
from gvm.protocols.gmp import Gmp

GVM_CONNECTION_TIMEOUT = 900
TASK_LOG = "/opt/gvm/taskslog.txt"
MAINTENANCE_LOCK = "/opt/gvm/.maintenance.lock"
RUNNING_STATUSES = frozenset({"Running", "Requested", "Queued"})


def write_log(mensaje, log=TASK_LOG):
    mensaje_tiempo = f"{datetime.datetime.now()} - {mensaje}\n"
    with open(log, "a") as archivo:
        archivo.write(mensaje_tiempo)
    print(mensaje_tiempo, end="")


def leer_configuracion(config_path):
    with open(config_path, "r", encoding="utf-8") as archivo:
        return json.load(archivo)


def connect_gvm():
    return TLSConnection(hostname="127.0.0.1", port=9390, timeout=GVM_CONNECTION_TIMEOUT)


def verificar_mantenimiento_activo():
    """
    Returns:
        tuple: (bool, str) - (True si hay mantenimiento activo, mensaje)
    """
    if not os.path.exists(MAINTENANCE_LOCK):
        return False, ""

    try:
        with open(MAINTENANCE_LOCK, "r") as f:
            lock_data = json.load(f)

        timestamp_str = lock_data.get("timestamp", "")
        pid = lock_data.get("pid", 0)

        try:
            os.kill(pid, 0)
            timestamp = datetime.datetime.fromisoformat(timestamp_str)
            tiempo_transcurrido = datetime.datetime.now() - timestamp.replace(tzinfo=None)
            horas = int(tiempo_transcurrido.total_seconds() / 3600)
            minutos = int((tiempo_transcurrido.total_seconds() % 3600) / 60)
            mensaje = f"Mantenimiento en curso desde {timestamp_str} ({horas}h {minutos}m)"
            return True, mensaje
        except OSError:
            try:
                os.remove(MAINTENANCE_LOCK)
            except Exception:
                pass
            return False, "Lock obsoleto eliminado"
    except Exception as e:
        return False, f"Error al leer lock: {e}"


def ejecutar_operacion_gmp(operacion_func, user, password, max_intentos=3, delay=2):
    ultimo_error = None
    for intento in range(1, max_intentos + 1):
        try:
            nueva_conexion = connect_gvm()
            with Gmp(connection=nueva_conexion) as gmp:
                gmp.authenticate(user, password)
                return operacion_func(gmp)
        except GvmError as e:
            ultimo_error = e
            error_str = str(e)
            if "Remote closed the connection" in error_str or "Connection" in error_str:
                if intento < max_intentos:
                    print(
                        f"[WARNING] Error de conexión GVM "
                        f"(intento {intento}/{max_intentos}). Reintentando en {delay}s..."
                    )
                    time.sleep(delay)
                    continue
            raise
        except TimeoutError as e:
            ultimo_error = e
            if intento < max_intentos:
                print(
                    f"[WARNING] Timeout GVM (intento {intento}/{max_intentos}). "
                    f"Reintentando en {delay}s..."
                )
                time.sleep(delay)
                continue
            raise
        except Exception:
            raise

    raise ultimo_error


def list_matching_tasks(user, password, wanted_name):
    """Lista tareas y filtra por nombre exacto sin mayúsculas."""
    want_norm = wanted_name.strip().lower()
    # Filtro GMP por nombre + rows alto; el match final es case-insensitive en Python.
    respuesta = ejecutar_operacion_gmp(
        lambda gmp: gmp.get_tasks(filter_string=f'name="{wanted_name.strip()}" rows=-1'),
        user,
        password,
    )
    root = ET.fromstring(respuesta)
    matches = []
    for task_elem in root.findall(".//task"):
        name = (task_elem.findtext("name") or "").strip()
        if name.lower() != want_norm:
            continue
        matches.append(
            {
                "id": task_elem.get("id"),
                "name": name,
                "status": (task_elem.findtext("status") or "").strip(),
            }
        )

    # Si el filtro GMP es case-sensitive y no encontró nada, listar todas y filtrar.
    if not matches:
        respuesta = ejecutar_operacion_gmp(
            lambda gmp: gmp.get_tasks(filter_string="rows=-1"),
            user,
            password,
        )
        root = ET.fromstring(respuesta)
        for task_elem in root.findall(".//task"):
            name = (task_elem.findtext("name") or "").strip()
            if name.lower() != want_norm:
                continue
            matches.append(
                {
                    "id": task_elem.get("id"),
                    "name": name,
                    "status": (task_elem.findtext("status") or "").strip(),
                }
            )
    return matches


def start_task_by_name(user, password, task_name):
    """
    Arranca la tarea pedida aunque otras estén en curso.

    Returns:
        int: 0 OK / ya corriendo; 1 no encontrada / ambigua / error; 3 mantenimiento
    """
    mantenimiento_activo, mensaje = verificar_mantenimiento_activo()
    if mantenimiento_activo:
        write_log(f"MANTENIMIENTO EN CURSO: no se arranca «{task_name}». {mensaje}")
        print(f"[ERROR] Mantenimiento en curso: {mensaje}", file=sys.stderr)
        return 3

    try:
        matches = list_matching_tasks(user, password, task_name)
    except Exception as e:
        write_log(f"ERROR al listar tareas buscando «{task_name}»: {e}")
        print(f"[ERROR] No se pudieron listar tareas: {e}", file=sys.stderr)
        return 1

    if not matches:
        write_log(f"No se encontró tarea con nombre exacto (sin case) «{task_name}»")
        print(
            f"[ERROR] No hay tarea con nombre exacto (sin distinguir mayúsculas): «{task_name}»",
            file=sys.stderr,
        )
        return 1

    if len(matches) > 1:
        write_log(
            f"Nombre ambiguo «{task_name}»: {len(matches)} tareas coinciden; no se arranca."
        )
        print(
            f"[ERROR] Nombre ambiguo: {len(matches)} tareas coinciden con «{task_name}»:",
            file=sys.stderr,
        )
        for m in matches:
            print(f"  - id={m['id']} name={m['name']!r} status={m['status']}", file=sys.stderr)
        return 1

    task = matches[0]
    task_id = task["id"]
    name = task["name"]
    status = task["status"]

    if status in RUNNING_STATUSES:
        write_log(
            f"La tarea «{name}» (id {task_id}) ya está en estado {status}; no se relanza."
        )
        print(f"[OK] Ya en curso: «{name}» id={task_id} status={status}")
        return 0

    write_log(f"Arrancamos la tarea «{name}» con id {task_id} (status previo: {status})")
    try:
        start_resp = ejecutar_operacion_gmp(
            lambda gmp: gmp.start_task(task_id),
            user,
            password,
        )
        write_log(str(start_resp))
        print(f"[OK] Arrancada: «{name}» id={task_id}")
        return 0
    except Exception as e:
        write_log(f"ERROR al arrancar «{name}» (id {task_id}): {e}")
        print(f"[ERROR] Fallo al arrancar «{name}»: {e}", file=sys.stderr)
        return 1


def main():
    parser = argparse.ArgumentParser(
        description="Arranca una tarea OpenVAS/GVM por nombre exacto (sin distinguir mayúsculas)"
    )
    parser.add_argument(
        "task_name",
        help="Nombre exacto de la tarea a arrancar",
    )
    parser.add_argument(
        "-c",
        "--config",
        default="/opt/gvm/Config/config.json",
        help="Ruta al config.json (por defecto: /opt/gvm/Config/config.json)",
    )
    args = parser.parse_args()

    name = (args.task_name or "").strip()
    if not name:
        print("[ERROR] El nombre de la tarea no puede estar vacío", file=sys.stderr)
        sys.exit(1)

    try:
        configuracion = leer_configuracion(args.config)
    except FileNotFoundError:
        print(f"[ERROR] No se encuentra config: {args.config}", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"[ERROR] JSON inválido en {args.config}: {e}", file=sys.stderr)
        sys.exit(1)

    user = configuracion.get("user")
    password = configuracion.get("password")
    if not user or not password:
        print("[ERROR] config.json sin user/password", file=sys.stderr)
        sys.exit(1)

    code = start_task_by_name(user, password, name)
    if code == 3:
        print("[ERROR] Mantenimiento en curso: no se pueden ejecutar tareas nuevas")
    sys.exit(code)


if __name__ == "__main__":
    main()
