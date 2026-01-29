#!/usr/bin/env python3
import argparse
import json
import csv
import xml.etree.ElementTree as ET

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

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Exporta todos los targets de OpenVAS a CSV (Titulo;Rango;Desc)"
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
        help="Número de elementos a solicitar en cada página (no debe superar el límite Max Rows Per Page)"
    )
    args = parser.parse_args()
    export_targets_csv(args.config, args.output, args.page_size)

