#!/usr/bin/env python3
import argparse
import json
import csv
import xml.etree.ElementTree as ET
import subprocess
import sys
import os

from gvm.connections import TLSConnection
from gvm.protocols.gmp import Gmp

def export_targets_csv(config_path: str, csv_path: str, page_size: int = 1000) -> None:
    """
    Exporta todos los targets de OpenVAS en formato CSV, evitando el límite de 1 000 filas
    mediante paginación. El CSV tendrá columnas Titulo;Rango;Desc.
    """
    # Cargar credenciales
    with open(config_path, 'r', encoding='utf-8') as f:
        config = json.load(f)
    user = config.get("user")
    password = config.get("password")

    # Conexión TLS (compatible con Docker y entornos locales)
    connection = TLSConnection(hostname="127.0.0.1", port=9390)

    all_targets = []
    with Gmp(connection=connection) as gmp:
        gmp.authenticate(user, password)
        start = 1
        while True:
            # Pedimos un bloque de targets con el filtro first/rows
            filter_str = f"first={start} rows={page_size}"
            response_xml = gmp.get_targets(filter_string=filter_str)
            root = ET.fromstring(response_xml)
            targets = root.findall('.//target')

            # Añadir a la lista global
            all_targets.extend(targets)
            # Si recibimos menos de page_size, no hay más páginas
            if len(targets) < page_size:
                break
            # Avanzar al siguiente bloque
            start += page_size

    # Escribir el CSV
    with open(csv_path, 'w', newline='', encoding='utf-8') as f_out:
        writer = csv.writer(f_out, delimiter=';')
        writer.writerow(["Titulo", "Rango", "Desc"])
        for target in all_targets:
            titulo = (target.findtext("name") or "").strip()
            rangos_str = (target.findtext("hosts") or "").strip()
            desc = (target.findtext("comment") or "").strip()
            titulo = " ".join(titulo.split())
            desc = " ".join(desc.split())
            
            # Dividir rangos por comas y crear una fila por cada rango
            if rangos_str:
                rangos = [r.strip() for r in rangos_str.split(',') if r.strip()]
                for rango in rangos:
                    writer.writerow([titulo, rango, desc])
            else:
                # Si no hay rangos, escribir una fila vacía
                writer.writerow([titulo, "", desc])
    
    return len(all_targets)

def upload_to_sharepoint(csv_path: str, config_path: str) -> bool:
    """
    Sube el CSV exportado a SharePoint usando subida_share.py
    NOTA: subida_share.py lee el config de /opt/gvm/Config/config.json
          así que solo funciona si ese archivo tiene las credenciales correctas
    """
    # Cargar config para obtener país
    with open(config_path, 'r', encoding='utf-8') as f:
        config = json.load(f)
    pais = config.get("pais", "UNKNOWN")
    
    # Verificar que existe el archivo a subir
    if not os.path.isfile(csv_path):
        print(f"[ERROR] No se encuentra el archivo: {csv_path}", file=sys.stderr)
        return False
    
    # Ruta al script de subida
    subida_script = "/opt/gvm/Reports/subida_share.py"
    if not os.path.isfile(subida_script):
        print(f"[ERROR] No se encuentra subida_share.py: {subida_script}", file=sys.stderr)
        return False
    
    # IMPORTANTE: subida_share.py lee /opt/gvm/Config/config.json automáticamente
    # Si estás usando un config diferente (-c), la subida puede fallar
    if config_path != "/opt/gvm/Config/config.json":
        print(f"[WARNING] Usando config no estándar: {config_path}")
        print(f"[WARNING] subida_share.py leerá /opt/gvm/Config/config.json para credenciales SharePoint")
    
    # Ejecutar subida_share.py
    print(f"[INFO] Subiendo {csv_path} a SharePoint...")
    result = subprocess.run([
        "python3", subida_script,
        "-f", csv_path,
        "-p", pais,
        "-a", "Targets_Export"
    ], capture_output=True, text=True)
    
    if result.returncode == 0:
        print(result.stdout)
        return True
    else:
        print(f"[ERROR] Fallo al subir a SharePoint: {result.stderr}", file=sys.stderr)
        return False

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Exporta todos los targets de OpenVAS a CSV y opcionalmente los sube a SharePoint"
    )
    parser.add_argument(
        "-c", "--config",
        default="/opt/gvm/Config/config.json",
        help="Ruta al fichero config.json (por defecto: /opt/gvm/Config/config.json)"
    )
    parser.add_argument(
        "-o", "--output",
        default="openvas.csv",
        help="Ruta del CSV de salida (por defecto: openvas.csv)"
    )
    parser.add_argument(
        "--page-size",
        type=int,
        default=1000,
        help="Número de elementos a solicitar en cada página (no debe superar el límite Max Rows Per Page)"
    )
    parser.add_argument(
        "--no-upload",
        action="store_true",
        help="NO subir el CSV a SharePoint (por defecto siempre sube)"
    )
    args = parser.parse_args()
    
    # Exportar targets
    print(f"[INFO] Exportando targets desde OpenVAS...")
    num_targets = export_targets_csv(args.config, args.output, args.page_size)
    print(f"[OK] Exportados {num_targets} targets a {args.output}")
    
    # Subir a SharePoint (siempre, excepto si se usa --no-upload)
    if not args.no_upload:
        success = upload_to_sharepoint(args.output, args.config)
        if success:
            print("[OK] Exportación y subida completadas exitosamente")
            sys.exit(0)
        else:
            print("[ERROR] Exportación OK pero fallo la subida a SharePoint", file=sys.stderr)
            sys.exit(1)
    else:
        print("[INFO] Subida a SharePoint omitida (--no-upload)")
        sys.exit(0)

