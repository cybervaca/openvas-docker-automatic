#!/usr/bin/env python3
import sys
import argparse
import os
import json
import datetime
from pathlib import Path
from urllib.parse import quote

try:
    import requests
    import msal
except ImportError as e:
    sys.stderr.write(
        "[ERROR] Instale requests y msal en el mismo entorno Python que ejecute este "
        f"script (p. ej. pip install -r requirements.txt). Detalle: {e}\n"
    )
    sys.exit(2)


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
    """Obtiene el drive-id de la biblioteca Documents (nombre sin distinguir mayúsculas)."""
    url = f"https://graph.microsoft.com/v1.0/sites/{site_id}/drives"
    resp = requests.get(url, headers={"Authorization": f"Bearer {token}"})
    if resp.status_code != 200:
        print(f"[ERROR] No se pudo obtener drives: {resp.text}", file=sys.stderr)
        sys.exit(1)

    drives = resp.json().get("value", [])
    for d in drives:
        if (d.get("name") or "").lower() == "documents":
            return d["id"]

    print("[ERROR] No se encontró la biblioteca 'Documents'", file=sys.stderr)
    sys.exit(1)


def list_all_drive_children(site_id, drive_id, headers, parent_item_id=None):
    """Lista hijos directos del root o del item carpeta (paginación completa)."""
    items = []
    if parent_item_id is None:
        next_link = (
            f"https://graph.microsoft.com/v1.0/sites/{site_id}/drives/{drive_id}/root/children"
        )
    else:
        next_link = (
            f"https://graph.microsoft.com/v1.0/sites/{site_id}/drives/{drive_id}/items/"
            f"{parent_item_id}/children"
        )
    while next_link:
        r = requests.get(next_link, headers=headers, timeout=120)
        if r.status_code != 200:
            return None, f"HTTP {r.status_code} {r.text}"
        payload = r.json()
        items.extend(payload.get("value", []))
        next_link = payload.get("@odata.nextLink")
    return items, None


def create_drive_folder(site_id, drive_id, headers, parent_item_id, folder_name):
    """
    Crea una carpeta bajo el padre indicado (o bajo root si parent_item_id es None).
    Devuelve (item_dict, texto_error_o_None).
    """
    body = {
        "name": folder_name,
        "folder": {},
        "@microsoft.graph.conflictBehavior": "fail",
    }
    if parent_item_id is None:
        url = (
            f"https://graph.microsoft.com/v1.0/sites/{site_id}/drives/{drive_id}/root/children"
        )
    else:
        url = (
            f"https://graph.microsoft.com/v1.0/sites/{site_id}/drives/{drive_id}/items/"
            f"{parent_item_id}/children"
        )
    r = requests.post(url, headers={**headers, "Content-Type": "application/json"}, json=body, timeout=120)
    if r.status_code not in (200, 201):
        return None, f"HTTP {r.status_code} {r.text}"
    item = r.json()
    if item.get("folder") is None:
        return None, f"«{folder_name}» ya existe como archivo, no como carpeta"
    return item, None


def resolve_nested_drive_folder_insensitive(
    site_id, drive_id, headers, segments_wanted, create_missing=False
):
    """
    Bajo Documents; en cada nivel elige carpeta cuyo name coincide sin distinguir mayúsculas.
    Si create_missing=True, crea la subcarpeta faltante vía Graph y continúa.
    Devuelve (folder_item_id, ruta_mostrar, texto_error_o_None).
    """
    trimmed = [s.strip() for s in segments_wanted if s and str(s).strip()]
    if not trimmed:
        return None, None, "lista de segmentos vacía"

    parent_id = None
    resolved_chunks = []

    for want in trimmed:
        want_norm = want.lower()
        kids, err = list_all_drive_children(site_id, drive_id, headers, parent_id)
        if err:
            ctx = "/".join(resolved_chunks) if resolved_chunks else "/"
            return None, None, f"Graph al listar (tras «{ctx}»): {err}"
        found = None
        for item in kids:
            if item.get("folder") is None:
                continue
            if (item.get("name") or "").lower() == want_norm:
                found = item
                break
        if found is None:
            if not create_missing:
                return (
                    None,
                    None,
                    f"no existe subcarpeta «{want}» tras "
                    f"{'/' + '/'.join(resolved_chunks) if resolved_chunks else '/'} "
                    "(comparación sin mayúsculas).",
                )
            created, cerr = create_drive_folder(
                site_id, drive_id, headers, parent_id, want
            )
            if cerr:
                ctx = "/".join(resolved_chunks) if resolved_chunks else "/"
                return None, None, f"no se pudo crear «{want}» tras «{ctx}»: {cerr}"
            found = created
            print(
                "[INFO] Carpeta SharePoint creada: "
                + "/".join(resolved_chunks + [found["name"]])
            )
        resolved_chunks.append(found["name"])
        parent_id = found["id"]

    return parent_id, "/".join(resolved_chunks), None


def upload_file_to_drive_folder(token, site_id, drive_id, parent_folder_item_id, local_path, overwrite=False):
    """Sube usando el id del padre en Graph."""
    file_name = Path(local_path).name
    encoded = quote(file_name, safe="")
    with open(local_path, "rb") as f:
        data = f.read()

    url = (
        f"https://graph.microsoft.com/v1.0/sites/{site_id}/drives/{drive_id}/items/"
        f"{parent_folder_item_id}:/{encoded}:/content"
    )
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
    Rutas bajo Documents: cada segmento se resuelve contra Graph sin distinguir mayúsculas.
    Criterio: nombre con prefijo YYYY_MM_ (hora local del servidor) o lastModifiedDateTime
    en el mes actual UTC (excluye exclusion.csv en la rama por fecha).
    """
    def _config_invalid(val):
        return val is None or str(val).startswith("ERROR") or str(val) == "SITE_NO_DEFINIDO"

    if _config_invalid(TENANT_ID) or _config_invalid(CLIENT_ID) or _config_invalid(CLIENT_SECRET):
        print("[ERROR] Config SharePoint inválida (tenant_id / client_id / client_secret)", file=sys.stderr)
        return 2
    if _config_invalid(SITE):
        print("[ERROR] site no definido en config.json", file=sys.stderr)
        return 2

    pais = lee_config("pais").strip()
    if _config_invalid(pais):
        print("[ERROR] pais no definido en config.json", file=sys.stderr)
        return 2

    automatizacion = "Openvas_Interno"
    path_hints = ["General", "Subidas", pais, automatizacion, str(SITE).strip()]
    hints_txt = "/".join(path_hints)

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

        headers = {"Authorization": f"Bearer {token}"}
        drive_id = get_drive_id(token, site_id)
        folder_id, resolved_under_docs, ferr = resolve_nested_drive_folder_insensitive(
            site_id, drive_id, headers, path_hints
        )
        if ferr or not folder_id:
            print(f"[ERROR] Resolver carpeta SharePoint: {ferr}", file=sys.stderr)
            return 2

        print(f"[INFO] Comprobación mensual → hint ruta (sin case): {hints_txt}")
        print(f"[INFO] Carpeta resuelta Graph: {resolved_under_docs}")

        now = datetime.datetime.now()
        year, month = now.year, now.month
        prefix = f"{year:04d}_{month:02d}_"
        month_start = datetime.datetime(year, month, 1, tzinfo=datetime.timezone.utc)
        if month == 12:
            month_end = datetime.datetime(year + 1, 1, 1, tzinfo=datetime.timezone.utc)
        else:
            month_end = datetime.datetime(year, month + 1, 1, tzinfo=datetime.timezone.utc)

        children, list_err = list_all_drive_children(site_id, drive_id, headers, folder_id)
        if list_err:
            print(f"[ERROR] Listar carpeta SharePoint: {list_err}", file=sys.stderr)
            return 2

        for item in children:
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

    hints = ["General", "Subidas", str(args.pais).strip(), str(args.automatizacion).strip(), str(SITE).strip()]
    print(f"[INFO] Subida SharePoint: ruta solicitada sin case en carpetas → {'/'.join(hints)}")

    token = get_token()
    site_id = get_site_id(token)
    drive_id = get_drive_id(token, site_id)
    headers = {"Authorization": f"Bearer {token}"}
    fid, resolved, ferr = resolve_nested_drive_folder_insensitive(
        site_id, drive_id, headers, hints, create_missing=True
    )
    if ferr or not fid:
        print(f"[ERROR] No resuelvo carpeta de subida: {ferr}", file=sys.stderr)
        sys.exit(1)
    print(f"[INFO] Carpeta destino resuelta: {resolved}")

    upload_file_to_drive_folder(token, site_id, drive_id, fid, str(lp), overwrite=True)

if __name__ == "__main__":
    main()

