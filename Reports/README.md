# Reports - Módulo de Generación de Reportes OpenVAS

Este directorio contiene scripts para la generación, procesamiento y distribución de reportes de vulnerabilidades desde OpenVAS/GVM.

## 📋 Descripción de Scripts

### Scripts Principales de Generación de Reportes

#### `get-reports.py`
Script básico para obtener todos los reportes de OpenVAS.

**Características:**
- Obtiene todos los reportes disponibles (hasta 1500)
- Genera archivos CSV con las vulnerabilidades
- Separa CVEs de misconfiguraciones
- Formato simplificado sin información de sistema operativo

**Uso:**
```bash
python3 get-reports.py
```

#### `get-reports-os.py`
Script avanzado que incluye información del sistema operativo de los hosts.

**Características:**
- Extrae información de SO desde la base de datos PostgreSQL de GVM
- Genera reportes en formato CSV y Excel
- Incluye metadatos: región, país, scope, severidad
- Elimina duplicados automáticamente
- Integración con sistema de correo electrónico
- Subida automática a Balbix (opcional)

**Uso:**
```bash
python3 get-reports-os.py
```

**Salida:**
- CSV unificado con todas las vulnerabilidades
- Archivo Excel con formato mejorado
- Archivos separados: `*_CVE.csv` y `*_Misconfigs.csv`

#### `get-reports-unico.py`
Script para extraer un reporte específico por nombre o ID de tarea.

**Características:**
- Búsqueda por nombre de tarea o ID
- Filtrado específico de reportes
- Incluye información de SO y metadatos
- Clasificación automática de severidad (Critical/High/Medium/Low/Info)
- Soporte para múltiples regiones geográficas

**Uso:**
```bash
python3 get-reports-unico.py "nombre_tarea"
python3 get-reports-unico.py "task_id"
```

**Ejemplo:**
```bash
python3 get-reports-unico.py "Scan_Produccion_2024"
```

#### `get-reports-test.py`
Script de pruebas con funcionalidades extendidas.

**Características:**
- Extracción de IPs excluidas de los targets
- Registro de exclusiones en CSV
- Subida automática a SharePoint
- Generación de reportes con información completa de SO
- Envío de notificaciones por correo
- Limpieza automática de archivos temporales

**Uso:**
```bash
python3 get-reports-test.py
```

**Archivos generados:**
- `exclusion.csv`: Registro de IPs excluidas por tarea
- Reportes en formato CSV y Excel con timestamp
- Archivos separados por tipo de vulnerabilidad

### Scripts de Distribución

#### `upload-reports.py`
Script para subir reportes a plataformas externas (Balbix/Valbix).

**Uso:**
```bash
python3 upload-reports.py archivo1.csv archivo2.csv
```

#### `subida_share.py`
Script para subir reportes a SharePoint.

**Uso:**
```bash
python3 subida_share.py -f archivo.csv -p PAIS -a carpeta_destino
```

**Parámetros:**
- `-f`: Archivo a subir
- `-p`: País/región
- `-a`: Carpeta destino en SharePoint

## 📁 Estructura de Directorios

```
Reports/
├── exports/              # Reportes CSV temporales
│   └── vulns_host/      # Reportes finales con información de hosts
├── get-reports.py       # Script básico
├── get-reports-os.py    # Script con información de SO
├── get-reports-unico.py # Script para reporte específico
├── get-reports-test.py  # Script de pruebas avanzado
├── upload-reports.py    # Subida a Balbix/Valbix
├── subida_share.py      # Subida a SharePoint
└── README.md           # Este archivo
```

## 🔧 Configuración

Todos los scripts requieren el archivo de configuración `/home/redteam/gvm/Config/config.json` con la siguiente estructura:

```json
{
  "user": "admin",
  "password": "password",
  "mailserver": "smtp.example.com",
  "smtp_user": "user@example.com",
  "smtp_pass": "smtp_password",
  "from": "openvas@example.com",
  "to": "security@example.com",
  "pais": "COLOMBIA",
  "region": "SUR",
  "site": "SITE_NAME",
  "scope": "Internal"
}
```

## 📊 Formato de Reportes

### Columnas Básicas
- `IP`: Dirección IP del host
- `Hostname`: Nombre del host
- `Port`: Puerto afectado
- `Port Protocol`: Protocolo (TCP/UDP)
- `CVSS`: Puntuación CVSS
- `NVT Name`: Nombre de la vulnerabilidad
- `Summary`: Resumen de la vulnerabilidad
- `Specific Result`: Resultado específico
- `CVEs`: CVEs asociados
- `Solution`: Solución propuesta

### Columnas Extendidas (scripts avanzados)
- `sistema_operativo`: SO detectado
- `Region`: Región geográfica
- `Country`: País
- `Scope`: Alcance (Internal/External)
- `Process`: Proceso (redteam-scan)
- `Owner`: Propietario
- `issue_type_severity`: Severidad clasificada

## 🔍 Clasificación de Severidad

Los scripts clasifican automáticamente las vulnerabilidades según CVSS:

- **Critical**: CVSS ≥ 9.0
- **High**: CVSS ≥ 7.0
- **Medium**: CVSS ≥ 4.0
- **Low**: CVSS ≥ 1.0
- **Info**: CVSS < 1.0

## 🌍 Mapeo de Regiones

```
COLOMBIA, PERU, ARGENTINA, CHILE → SUR
MEXICO, GUATEMALA, EL_SALVADOR, PUERTO_RICO, USNS, BAAGRI → NORTE
BRASIL, INTERFILE → BRASIL
EMEA → EMEA
```

## 📧 Notificaciones por Correo

Los scripts pueden enviar notificaciones automáticas al completar la generación de reportes. La funcionalidad está comentada por defecto y puede activarse descomentando las líneas correspondientes.

## 🔒 Requisitos

- Python 3.x
- Acceso al socket de GVM (`/run/gvmd/gvmd.sock`)
- Permisos para acceder a PostgreSQL (para scripts con información de SO)
- Librerías Python (ver `requirements.txt` en el directorio raíz)

## ⚠️ Notas Importantes

1. Los scripts deben ejecutarse dentro del contenedor Docker de OpenVAS o con acceso al socket de GVM
2. La ruta `/home/redteam/gvm/` debe ajustarse según la instalación
3. Los reportes se generan con filtros: `min_qod=70` y `severity>0`
4. Los archivos temporales en `exports/` se limpian automáticamente en algunos scripts
5. La subida a Balbix está desactivada por defecto en algunos scripts (comentada)

## 🚀 Flujo de Trabajo Típico

1. **Generación de reportes**: Ejecutar `get-reports-test.py` o `get-reports-os.py`
2. **Procesamiento**: Los scripts automáticamente:
   - Extraen información de la base de datos
   - Unifican múltiples reportes
   - Eliminan duplicados
   - Clasifican vulnerabilidades
3. **Distribución**: 
   - Subida a SharePoint (automática)
   - Subida a Balbix/Valbix (opcional)
4. **Notificación**: Envío de correo (opcional)

## 📝 Ejemplos de Uso

### Generar todos los reportes con información completa
```bash
python3 get-reports-test.py
```

### Generar reporte de una tarea específica
```bash
python3 get-reports-unico.py "Scan_DMZ_Weekly"
```

### Subir reportes manualmente
```bash
python3 upload-reports.py /home/redteam/gvm/Reports/exports/vulns_host/2024_02_06_10_30.csv
```

## 🐛 Troubleshooting

- **Error de conexión a GVM**: Verificar que el socket `/run/gvmd/gvmd.sock` esté accesible
- **Error de PostgreSQL**: Verificar permisos del usuario postgres
- **Error de configuración**: Verificar que `config.json` exista y tenga el formato correcto
- **Archivos no generados**: Verificar que existan reportes en OpenVAS con vulnerabilidades

## 📄 Licencia

Este proyecto es parte del sistema de automatización de OpenVAS Docker.

