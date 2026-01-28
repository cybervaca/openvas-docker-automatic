#!/usr/bin/env python3
import sys
import argparse
import os
from pathlib import Path
import requests
import msal
import os, json

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

    print(f"[OK] Archivo subido: {file_name} -> {remote_path}")

# ==== MAIN ====
def main():
    parser = argparse.ArgumentParser(
        description="Subir un archivo a SharePoint vía Graph API con Client Credentials"
    )
    parser.add_argument("-f", "--file", required=True, help="Ruta al archivo local")
    parser.add_argument(
        "-p",
        "--pais",
        help="País (si no se proporciona, se usa lee_config('pais'))"
    )
    parser.add_argument("-a", "--aplicacion", required=True, help="Aplicacion")
    parser.add_argument("-o", "--overwrite", action="store_true", help="Sobreescribir si existe")
    args = parser.parse_args()

    local_file = args.file
    pais = args.pais if args.pais else lee_config("pais")
    aplicacion = args.aplicacion
    overwrite = args.overwrite

    if not os.path.isfile(local_file):
        print(f"[ERROR] No se encuentra el archivo: {local_file}", file=sys.stderr)
        sys.exit(1)

    # p.ej. "Openvas_Interno/PUERTO_RICO"
    remote_path = f"{aplicacion}/{pais}"

    # 1. Obtener token
    token = get_token()
    # 2. Obtener site_id y drive_id
    site_id = get_site_id(token)
    drive_id = get_drive_id(token, site_id)

    # 3. Subir el archivo
    upload_file(token, site_id, drive_id, local_file, remote_path, overwrite)

if __name__ == "__main__":
    main()

