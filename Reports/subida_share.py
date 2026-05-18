#!/usr/bin/env python3
import sys
import argparse
import os
import json
import datetime
from pathlib import Path
from urllib.parse import quote

import requests
import msal

def lee_config(dato):
    try:
        with open("/opt/gvm/Config/config.json", 'r') as archivo:
            configuracion = json.load(archivo)
            return str(configuracion.get(dato, "SITE_NO_DEFINIDO"))
    except FileNotFoundError:
        return "ERROR_NO_FILE"
    except json.JSONDecodeError:
        return "ERROR_JSON"
    except Exception:
        return "ERROR_DESCONOCIDO"



# ==== CONFIGURACIÓN ====

SITE = (lee_config("site"))
TENANT_ID = (lee_config("tenant_id"))
CLIENT_ID = (lee_config("client_id"))
CLIENT_SECRET = (lee_config("client_secret"))

SITE_HOSTNAME = "atentoglobal.sharepoint.com"
SITE_PATH = "/sites/RedTeam"   # Ruta de tu sitio


def informa(msg):
    print (Color.GREEN + "[" + Color.RED + "+" + Color.GREEN + "] " +  msg)

# ==== AUTENTICACIÓN ====
def get_token():
    """Obtiene un access_token con Client Credentials Flow"""
    app = msal.ConfidentialClientApplication(
        client_id=CLIENT_ID,
        client_credential=CLIENT_SECRET,
        authority=f"https://login.microsoftonline.com/{TENANT_ID}"
    )
    result = app.acquire_token_for_client(scopes=["https://graph.microsoft.com/.default"])
    if "access_token" not in result:
        print(f"[ERROR] No se pudo obtener token: {result}", file=sys.stderr)
        sys.exit(1)

    #print("Access_Token : " + result["access_token"])
    return result["access_token"]

# ==== GRAPH HELPERS ====
def get_site_id(token):
    """Obtiene el site-id del sitio RedTeam"""
    url = f"https://graph.microsoft.com/v1.0/sites/{SITE_HOSTNAME}:{SITE_PATH}"
    resp = requests.get(url, headers={"Authorization": f"Bearer {token}"})
    if resp.status_code != 200:
        print(f"[ERROR] No se pudo obtener site-id: {resp.text}", file=sys.stderr)
        sys.exit(1)
    #print("Site_ID : " + resp.json()["id"])
    return resp.json()["id"]

def get_drive_id(token, site_id):
    """Obtiene el drive-id de la biblioteca Documents"""
    url = f"https://graph.microsoft.com/v1.0/sites/{site_id}/drives"
    resp = requests.get(url, headers={"Authorization": f"Bearer {token}"})
    if resp.status_code != 200:
        print(f"[ERROR] No se pudo obtener drives: {resp.text}", file=sys.stderr)
        sys.exit(1)

    drives = resp.json().get("value", [])
    for d in drives:
        if d.get("name") in ["Documents"]:
            return d["id"]

    print("[ERROR] No se encontró la biblioteca 'Documents'", file=sys.stderr)
    sys.exit(1)
 

def upload_file(token, site_id, drive_id, local_path, remote_path, overwrite=False):
    """Sube archivo a SharePoint usando Graph API"""
    file_name = Path(local_path).name
    with open(local_path, "rb") as f:
        data = f.read()

    url = f"https://graph.microsoft.com/v1.0/sites/{site_id}/drives/{drive_id}/root:/{remote_path}/{file_name}:/content"

    if not overwrite:
        url += "?@microsoft.graph.conflictBehavior=fail"
    else:
        url += "?@microsoft.graph.conflictBehavior=replace"

    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.put(url, headers=headers, data=data)

    if resp.status_code not in (200, 201):
        print(f"[ERROR] Falló subida: {resp.status_code} {resp.text}", file=sys.stderr)
        sys.exit(1)

    print(f"[OK] Archivo subido: {resp.json()['webUrl']}")


def run_check_mensual():
    """
    Lista la carpeta de informes en SharePoint y detecta CSV/XLSX del mes calendario actual.

    Salida: 0 = ya hay informe este mes; 1 = no hay; 2 = error Graph/config (run-task hace fail-open).
    Criterio: nombre con prefijo YYYY_MM_ (como generan los scripts) o lastModifiedDateTime
    en el mes actual (excluye exclusion.csv en la rama por fecha).
    """
    def _config_invalid(val):
        return val is None or str(val).startswith("ERROR") or str(val) == "SITE_NO_DEFINIDO"

    if _config_invalid(TENANT_ID) or _config_invalid(CLIENT_ID) or _config_invalid(CLIENT_SECRET):
        print("[ERROR] Config SharePoint inválida (tenant_id / client_id / client_secret)", file=sys.stderr)
        return 2
    if _config_invalid(SITE):
        print("[ERROR] site no definido en config.json", file=sys.stderr)
        return 2

    pais = lee_config("pais")
    if _config_invalid(pais):
        print("[ERROR] pais no definido en config.json", file=sys.stderr)
        return 2

    automatizacion = "Openvas_Interno"
    remote_folder = f"General/Subidas/{pais}/{automatizacion}/{SITE}"

    try:
        app = msal.ConfidentialClientApplication(
            client_id=CLIENT_ID,
            client_credential=CLIENT_SECRET,
            authority=f"https://login.microsoftonline.com/{TENANT_ID}",
        )
        result = app.acquire_token_for_client(scopes=["https://graph.microsoft.com/.default"])
        token = result.get("access_token")
        if not token:
            print(f"[ERROR] No se pudo obtener token: {result}", file=sys.stderr)
            return 2
    except Exception as e:
        print(f"[ERROR] MSAL: {e}", file=sys.stderr)
        return 2

    try:
        url_site = f"https://graph.microsoft.com/v1.0/sites/{SITE_HOSTNAME}:{SITE_PATH}"
        r_site = requests.get(url_site, headers={"Authorization": f"Bearer {token}"}, timeout=60)
        if r_site.status_code != 200:
            print(f"[ERROR] site-id: {r_site.status_code} {r_site.text}", file=sys.stderr)
            return 2
        site_id = r_site.json()["id"]

        url_drives = f"https://graph.microsoft.com/v1.0/sites/{site_id}/drives"
        r_drives = requests.get(url_drives, headers={"Authorization": f"Bearer {token}"}, timeout=60)
        if r_drives.status_code != 200:
            print(f"[ERROR] drives: {r_drives.status_code} {r_drives.text}", file=sys.stderr)
            return 2
        drive_id = None
        for d in r_drives.json().get("value", []):
            if d.get("name") == "Documents":
                drive_id = d["id"]
                break
        if not drive_id:
            print("[ERROR] No se encontró la biblioteca 'Documents'", file=sys.stderr)
            return 2

        enc_path = "/".join(quote(part, safe="") for part in remote_folder.split("/") if part)
        list_url = (
            f"https://graph.microsoft.com/v1.0/sites/{site_id}/drives/{drive_id}/root:"
            f"/{enc_path}:/children"
        )

        now = datetime.datetime.now()
        year, month = now.year, now.month
        prefix = f"{year:04d}_{month:02d}_"
        month_start = datetime.datetime(year, month, 1, tzinfo=datetime.timezone.utc)
        if month == 12:
            month_end = datetime.datetime(year + 1, 1, 1, tzinfo=datetime.timezone.utc)
        else:
            month_end = datetime.datetime(year, month + 1, 1, tzinfo=datetime.timezone.utc)

        headers = {"Authorization": f"Bearer {token}"}
        next_link = list_url

        while next_link:
            r_list = requests.get(next_link, headers=headers, timeout=120)
            if r_list.status_code != 200:
                print(
                    f"[ERROR] Listar carpeta SharePoint: {r_list.status_code} {r_list.text}",
                    file=sys.stderr,
                )
                return 2
            payload = r_list.json()
            for item in payload.get("value", []):
                if item.get("folder") is not None:
                    continue
                name = item.get("name") or ""
                lower = name.lower()
                if not (lower.endswith(".csv") or lower.endswith(".xlsx")):
                    continue
                if name.startswith(prefix):
                    print(f"[INFO] Informe del mes en SharePoint (nombre): {name}")
                    return 0
                lm = item.get("lastModifiedDateTime")
                if lower == "exclusion.csv":
                    continue
                if lm:
                    try:
                        parsed = datetime.datetime.fromisoformat(lm.replace("Z", "+00:00"))
                        if month_start <= parsed < month_end:
                            print(f"[INFO] Informe del mes en SharePoint (lastModified): {name}")
                            return 0
                    except (ValueError, TypeError):
                        pass
            next_link = payload.get("@odata.nextLink")

        print("[INFO] No hay informe CSV/XLSX del mes actual en la ruta de SharePoint.")
        return 1
    except requests.RequestException as e:
        print(f"[ERROR] Red/Graph: {e}", file=sys.stderr)
        return 2
    except (KeyError, ValueError) as e:
        print(f"[ERROR] Respuesta Graph inesperada: {e}", file=sys.stderr)
        return 2


# ==== MAIN ====
def main():
    parser = argparse.ArgumentParser(description="Subida a SharePoint con Graph API (App-Only Auth)")
    parser.add_argument(
        "--check-mensual",
        action="store_true",
        help="Comprobar si existe informe CSV/XLSX del mes (salida 0=sí, 1=no, 2=error)",
    )
    parser.add_argument("-f", "--file", help="Ruta local del archivo a subir")
    parser.add_argument("-p", "--pais", help="Nombre del país para carpeta")
    parser.add_argument("-a", "--automatizacion", help="Nombre de la automatización para carpeta")
    #parser.add_argument("--overwrite", action="store_true", help="Sobrescribir archivo si existe")

    args = parser.parse_args()
    if args.check_mensual:
        if args.file is not None or args.pais is not None or args.automatizacion is not None:
            parser.error("--check-mensual no se puede combinar con -f, -p ni -a")
        sys.exit(run_check_mensual())

    if not args.file or not args.pais or not args.automatizacion:
        parser.error("La subida requiere -f, -p y -a (o use solo --check-mensual)")

    lp = Path(args.file).expanduser()
    if not lp.is_file():
        # Muchos OpenVAS nunca generan exclusion.csv; no es un fallo operativo.
        if lp.name.lower() == "exclusion.csv":
            print(
                f"[INFO] Sin exclusion.csv en {lp}; se omite subida "
                "(normal si no hay exclusiones)."
            )
            sys.exit(0)
        print(f"[ERROR] Archivo no encontrado: {lp}", file=sys.stderr)
        sys.exit(1)

    if lp.name.lower() == "exclusion.csv" and lp.stat().st_size == 0:
        print("[INFO] exclusion.csv vacío; se omite subida a SharePoint.")
        sys.exit(0)

    # Construir ruta de destino en SharePoint
    remote_path = f"General/Subidas/{args.pais}/{args.automatizacion}/{SITE}"

    # Obtener token y site/drive ids
    token = get_token()
    site_id = get_site_id(token)
    drive_id = get_drive_id(token, site_id)

    #print(f"[INFO] Subiendo {lp} a {remote_path} (site={site_id}, drive={drive_id})")
    upload_file(token, site_id, drive_id, str(lp), remote_path, overwrite=True)

if __name__ == "__main__":
    main()

