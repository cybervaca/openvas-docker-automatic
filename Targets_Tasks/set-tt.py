import pandas as pd
import getpass
import csv
import os
import re
import sys
import importlib
import xml.etree.ElementTree as ET
from gvm.protocols.gmp import Gmp

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
from gvm_connect import connect_gvm
# Intentar importar HostsOrdering desde diferentes ubicaciones posibles
try:
    HostsOrdering = getattr(importlib.import_module('gvm.protocols.gmp.types'), 'HostsOrdering')
except (ImportError, AttributeError):
    try:
        HostsOrdering = getattr(importlib.import_module('gvm.protocols.gmp'), 'HostsOrdering')
    except (ImportError, AttributeError):
        # Si no se puede importar, usar None y eliminar el parámetro
        HostsOrdering = None

EXCLUSIONS_CSV_PATH = '/opt/gvm/Reports/exclusion.csv'


def normalize_exclusions(value):
    """
    Normaliza exclusiones separadas por coma, punto y coma o espacios.
    Devuelve una lista sin vacíos ni duplicados, manteniendo el orden.
    """
    if value is None or pd.isna(value):
        return []

    exclusions = []
    seen = set()
    for item in re.split(r'[,;\s]+', str(value).strip()):
        exclusion = item.strip()
        if exclusion and exclusion not in seen:
            exclusions.append(exclusion)
            seen.add(exclusion)

    return exclusions


def merge_unique(existing, new_values):
    """Une listas sin duplicados, manteniendo el orden."""
    merged = list(existing or [])
    seen = set(merged)
    for value in new_values or []:
        if value not in seen:
            merged.append(value)
            seen.add(value)
    return merged


def load_exclusions_csv(path=EXCLUSIONS_CSV_PATH):
    """
    Carga exclusiones históricas exportadas por Reports/get-reports-test.py.
    Formato esperado: task_name,excluded_ips,date
    """
    exclusions_by_task = {}
    if not os.path.exists(path):
        print(f"[EXCLUSIONES] No se encontró {path}; se usará solo la columna Exclusiones si existe")
        return exclusions_by_task

    try:
        with open(path, newline='', encoding='utf-8') as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                task_name = (row.get('task_name') or '').strip()
                excluded_ips = normalize_exclusions(row.get('excluded_ips'))
                if task_name and excluded_ips:
                    exclusions_by_task[task_name] = merge_unique(
                        exclusions_by_task.get(task_name, []),
                        excluded_ips
                    )
        print(f"[EXCLUSIONES] Cargadas exclusiones para {len(exclusions_by_task)} tarea(s) desde {path}")
    except Exception as e:
        print(f"[EXCLUSIONES] ADVERTENCIA: No se pudieron cargar exclusiones desde {path}: {e}")

    return exclusions_by_task


def load_csv(file):
    try:
        df = pd.read_csv(file, delimiter=';')
        print(f"CSV cargado: {len(df)} filas encontradas")
        if len(df) == 0:
            print("ERROR: El archivo CSV está vacío")
            return None
        # Eliminar filas completamente vacías
        df = df.dropna(how='all')
        # Eliminar filas donde Titulo, Rango o Desc estén vacíos
        df = df.dropna(subset=['Titulo', 'Rango', 'Desc'])
        print(f"Después de filtrar vacíos: {len(df)} filas válidas")
        if len(df) == 0:
            print("ERROR: No hay filas válidas después de filtrar")
            return None
        print(f"Columnas encontradas: {list(df.columns)}")
        
        # Resolver títulos duplicados
        df = resolve_duplicate_titles(df)
        
        return df
    except FileNotFoundError:
        print(f"ERROR: No se encontró el archivo {file}")
        return None
    except Exception as e:
        print(f"ERROR al leer el CSV: {e}")
        return None


def resolve_duplicate_titles(df):
    """
    Detecta títulos duplicados en el CSV y les agrega un sufijo numérico (_2, _3, etc.)
    También actualiza la descripción para reflejar el nuevo título.
    
    Args:
        df: DataFrame con columnas Titulo, Rango, Desc
    
    Returns:
        DataFrame con títulos únicos
    """
    print("\n[PARSEO] Verificando títulos duplicados...")
    
    # Contador para cada título
    title_counts = {}
    new_titles = []
    new_descs = []
    duplicates_found = 0
    
    for index, row in df.iterrows():
        titulo = str(row['Titulo']).strip()
        desc = str(row['Desc']).strip()
        
        if titulo in title_counts:
            # Es un duplicado, agregar sufijo
            title_counts[titulo] += 1
            new_titulo = f"{titulo}_{title_counts[titulo]}"
            new_desc = f"{desc}_{title_counts[titulo]}"
            new_titles.append(new_titulo)
            new_descs.append(new_desc)
            duplicates_found += 1
            print(f"  ⚠ Duplicado detectado: '{titulo}' → '{new_titulo}'")
        else:
            # Primera aparición, no modificar
            title_counts[titulo] = 1
            new_titles.append(titulo)
            new_descs.append(desc)
    
    # Actualizar el DataFrame
    df['Titulo'] = new_titles
    df['Desc'] = new_descs
    
    if duplicates_found > 0:
        print(f"\n[PARSEO] ✓ {duplicates_found} título(s) duplicado(s) renombrado(s)")
    else:
        print(f"[PARSEO] ✓ No se encontraron títulos duplicados")
    
    return df

def get_pass():
    password=getpass.getpass(prompt='Enter password: ')
    return password

def get_full_and_fast_config_id(gmp):
    """
    Obtiene dinámicamente el ID de la configuración 'Full and Fast'.
    
    Args:
        gmp: Objeto GMP autenticado
    
    Returns:
        str: ID de la configuración 'Full and Fast' o None si no se encuentra
    """
    try:
        respuesta = gmp.get_scan_configs()
        root = ET.fromstring(respuesta)
        scan_configs = root.findall('.//config')
        
        for config in scan_configs:
            name_elem = config.find('name')
            if name_elem is not None and name_elem.text:
                config_name = name_elem.text.strip()
                # Buscar "Full and Fast" (puede variar el formato)
                if 'full' in config_name.lower() and 'fast' in config_name.lower():
                    config_id = config.get('id')
                    print(f"Configuración encontrada: '{config_name}' (ID: {config_id})")
                    return config_id
        
        # Si no se encuentra, buscar variaciones comunes
        for config in scan_configs:
            name_elem = config.find('name')
            if name_elem is not None and name_elem.text:
                config_name = name_elem.text.strip().lower()
                if 'full' in config_name or 'fast' in config_name:
                    config_id = config.get('id')
                    print(f"Configuración alternativa encontrada: '{name_elem.text}' (ID: {config_id})")
                    return config_id
        
        print("ERROR: No se encontró la configuración 'Full and Fast'")
        return None
    except Exception as e:
        print(f"ERROR al obtener configuración 'Full and Fast': {e}")
        import traceback
        traceback.print_exc()
        return None

def ready_target(connection,user,password,df):
    if df is None or len(df) == 0:
        print("ERROR: No hay datos para procesar")
        return
    
    rangos_duplicados = {}
    exclusions_by_task = load_exclusions_csv()
    has_exclusions_column = 'Exclusiones' in df.columns
    # using the with statement to automatically connect and disconnect to gvmd
    try:
        with Gmp(connection=connection) as gmp:
            # get the response message returned as a utf-8 encoded string
            response = gmp.get_version()
            root=ET.fromstring(response)
            status = root.get('status')
            version = root.find('version').text
            print(f'Status: {status}')
            print(f'Version: {version}')
            gmp.authenticate(user,password)
            print(f"Procesando {len(df)} filas del CSV...")
            for index, row in df.iterrows():
                try:
                    titulo = row['Titulo']
                    rango = row['Rango']
                    desc = row['Desc']
                    # Verificar que los valores no sean NaN o vacíos
                    if pd.isna(titulo) or pd.isna(rango) or pd.isna(desc):
                        print(f"ADVERTENCIA: Fila {index} tiene valores vacíos, saltando...")
                        continue
                    titulo = str(titulo).strip()
                    rango = str(rango).strip()
                    desc = str(desc).strip()

                    csv_exclusions = []
                    if has_exclusions_column:
                        csv_exclusions = normalize_exclusions(row.get('Exclusiones'))

                    # Prioridad: columna Exclusiones; fallback: Reports/exclusion.csv por task_name == Titulo.
                    exclusiones = csv_exclusions or exclusions_by_task.get(titulo, [])

                    if titulo in rangos_duplicados:
                        rangos_duplicados[titulo]['rangos'].append(rango)
                        rangos_duplicados[titulo]['exclusiones'] = merge_unique(
                            rangos_duplicados[titulo].get('exclusiones', []),
                            exclusiones
                        )
                    else:
                        rangos_duplicados[titulo] = {
                            'rangos': [rango],
                            'desc': desc,
                            'exclusiones': exclusiones
                        }
                except KeyError as e:
                    print(f"ERROR: Fila {index} no tiene la columna requerida: {e}")
                    continue
                except Exception as e:
                    print(f"ERROR procesando fila {index}: {e}")
                    continue
            
            print(f"Total de targets a crear: {len(rangos_duplicados)}")
            
            # Obtener el ID de la configuración 'Full and Fast' dinámicamente
            print("Obteniendo ID de configuración 'Full and Fast'...")
            config_id = get_full_and_fast_config_id(gmp)
            if config_id is None:
                print("ERROR: No se pudo obtener el ID de configuración. Abortando.")
                return
            
            with open('log.txt','w+') as log_file:
                for titulo, datos in rangos_duplicados.items():
                    desc = datos['desc']
                    exclusiones = datos.get('exclusiones', [])
                    if (len(datos['rangos']) > 9):
                        j=0
                        for i in range(0,len(datos['rangos']),9 ):
                            rangos=datos['rangos'][i:i+9]
                            titulocontador = f'{titulo}_{j}'
                            create_target(titulocontador,rangos,desc,gmp,log_file,config_id,exclusiones)
                            j+=1
                    else:
                        rangos=datos['rangos']
                        create_target(titulo,rangos,desc,gmp,log_file,config_id,exclusiones)
            print("Proceso completado. Revisa log.txt para detalles.")
    except Exception as e:
        print(f"ERROR crítico en ready_target: {e}")
        import traceback
        traceback.print_exc()
                    
def create_target(titulo, rangos, desc,gmp,log_file,config_id,exclusiones=None):
    exclusiones = exclusiones or []
    print(f'[TARGET]Título: {titulo}, Rangos: {rangos}, Descripción: {desc}')
    if exclusiones:
        print(f'[TARGET]Exclusiones: {exclusiones}')
        response_create=gmp.create_target(
            name=titulo,
            hosts=rangos,
            comment=desc,
            exclude_hosts=exclusiones,
            port_list_id='730ef368-57e2-11e1-a90f-406186ea4fc5'
        )
    else:
        response_create=gmp.create_target(name=titulo,hosts=rangos,comment=desc,port_list_id='730ef368-57e2-11e1-a90f-406186ea4fc5')
    create_xml= ET.fromstring(response_create)
    status_target = create_xml.get('status')
    status_target_text = create_xml.get('status_text')
    id_target = create_xml.get('id')
    print(f'Status: {status_target}')
    print(f'Status Text: {status_target_text}')
    print(f'ID: {id_target}')
    log_file.write(f'[TARGET]Título: {titulo};Rangos: {rangos};Exclusiones: {exclusiones};Status: {status_target}; Status Text: {status_target_text};ID: {id_target}\n')
    if (status_target == '201'):
        create_task(titulo,id_target,desc,gmp,log_file,config_id)

def create_task(name,id,desc,gmp,log_file,config_id):
    task_preferences = {
        "max_checks": "2",
        "max_hosts": "5"
    }
    # Usar el enum HostsOrdering si está disponible, sino None (usará valor por defecto)
    if HostsOrdering is not None:
        scan_order = HostsOrdering.RANDOM
    else:
        scan_order = None
    print(f'[TASK]Título: {name}, Descripción: {desc}')
    # Usar el config_id obtenido dinámicamente (Full and Fast)
    configid = config_id
    # scanner id for openvas default 08b69003-5fc2-4037-a479-93b440211c73
    scannerid = '08b69003-5fc2-4037-a479-93b440211c73'
    # Si scan_order es None, no pasar el parámetro hosts_ordering
    if scan_order is not None:
        responsetask=gmp.create_task(name=name,config_id=configid,target_id=id,scanner_id=scannerid,comment=desc, hosts_ordering=scan_order, preferences=task_preferences)
    else:
        responsetask=gmp.create_task(name=name,config_id=configid,target_id=id,scanner_id=scannerid,comment=desc, preferences=task_preferences)
    create_xml= ET.fromstring(responsetask)
    status_task = create_xml.get('status')
    status_task_text = create_xml.get('status_text')
    id_task = create_xml.get('id')
    print(f'Status: {status_task}')
    print(f'Status Text: {status_task_text}')
    print(f'ID: {id_task}')
    log_file.write(f'[TASK]Título: {name};Status: {status_task}; Status Text: {status_task_text};ID: {id_task}\n')

if __name__ == '__main__':
    username = 'admin'
    password = get_pass()
    file= "openvas.csv"
    print(f"Leyendo archivo: {file}")
    df = load_csv(file)
    if df is None:
        print("No se pudo cargar el CSV. Abortando.")
        exit(1)
    print("Conectando a GVM...")
    try:
        connection = connect_gvm(verbose=True)
        ready_target(connection, username, password, df)
    except Exception as e:
        print(f"ERROR al conectar o procesar: {e}")
        import traceback
        traceback.print_exc()
        exit(1)

