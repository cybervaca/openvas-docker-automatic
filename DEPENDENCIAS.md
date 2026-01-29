# Dependencias del Proyecto

## 📦 Archivos de Dependencias

- **`requirements.txt`** - Todas las dependencias con versiones específicas
- **`requirements-minimal.txt`** - Solo dependencias esenciales

## 🔍 Análisis de Dependencias por Módulo

### 🛡️ **GVM / OpenVAS** (CRÍTICO)
```
python-gvm==26.1.0        # Cliente GVM para Python
defusedxml==0.7.1         # XML seguro
```
**Usado en:**
- `set-tt.py` - Crear targets/tasks
- `run-task.py` - Ejecutar tasks
- `get-reports-test.py` - Exportar reportes
- `delete-files.py` - Limpiar BD

---

### 📊 **Procesamiento de Datos** (CRÍTICO)
```
pandas==2.1.1             # Manipulación de datos
numpy==1.26.3             # Operaciones numéricas (dependencia de pandas)
untangle==1.2.1           # Parser XML simple
```
**Usado en:**
- `set-tt.py` - Leer CSV de targets
- `get-reports-test.py` - Procesar y unificar reportes

---

### ☁️ **AWS / Balbix** (CRÍTICO para subida)
```
boto3==1.34.108           # SDK de AWS
botocore==1.34.108        # Core de boto3
awscli==1.32.108          # CLI de AWS
s3transfer==0.10.1        # Transferencias S3
```
**Usado en:**
- `upload-reports.py` - Subir reportes a S3/Balbix

---

### 📤 **Microsoft Graph / SharePoint** (CRÍTICO para subida)
```
msal                      # Microsoft Authentication Library
requests==2.32.4          # HTTP requests
```
**Usado en:**
- `subida_share.py` - Subir reportes a SharePoint

---

### 📑 **Excel / CSV** (CRÍTICO)
```
openpyxl==3.1.2           # Leer/escribir Excel
et-xmlfile==1.1.0         # Dependencia de openpyxl
```
**Usado en:**
- `get-reports-test.py` - Generar reportes Excel

---

### 🔐 **Criptografía / SSH** (IMPORTANTE)
```
cryptography==44.0.1      # Criptografía general
bcrypt==4.1.2             # Hashing de passwords
paramiko==3.4.0           # SSH (para warnings vistos)
PyNaCl==1.5.0             # Criptografía de libsodium
cffi==1.16.0              # FFI para cryptography
pycparser==2.21           # Parser C para cffi
```
**Usado en:**
- GVM usa TLS (cryptography)
- Paramiko genera warnings (no crítico)

---

### 🌐 **Web / HTTP** (IMPORTANTE)
```
requests==2.32.4          # Ya mencionado arriba
urllib3==2.5.0            # HTTP client
certifi==2024.7.4         # Certificados CA
idna==3.7                 # Dominios internacionales
charset-normalizer==3.3.1 # Detección charset
```
**Usado en:**
- `subida_share.py` - Comunicación con SharePoint
- Todas las conexiones HTTPS

---

### 🕐 **Fecha/Hora** (IMPORTANTE)
```
python-dateutil==2.8.2    # Manejo de fechas
pytz==2023.3.post1        # Zonas horarias
tzdata==2023.4            # Data de zonas horarias
```
**Usado en:**
- Todos los scripts que generan logs con timestamps

---

### 🧰 **Utilidades** (OPCIONAL)
```
beautifulsoup4==4.12.2    # Parser HTML
bs4==0.0.1                # Alias de beautifulsoup4
soupsieve==2.5            # Selectores CSS
lxml==5.1.0               # Parser XML/HTML
python-gnupg==0.5.2       # GPG wrapper
icalendar==5.0.11         # Calendarios
colorama==0.4.6           # Colores terminal
jmespath==1.0.1           # Query JSON
docutils==0.16            # Documentación
six==1.16.0               # Compatibilidad Python 2/3
```

---

## 🚀 Instalación

### Instalación Completa
```bash
cd /opt/gvm
python3 -m venv gvm
source gvm/bin/activate
pip3 install -r requirements.txt
```

### Instalación Mínima (Solo lo Esencial)
```bash
cd /opt/gvm
python3 -m venv gvm
source gvm/bin/activate
pip3 install -r requirements-minimal.txt
```

---

## 🔧 Verificar Dependencias Instaladas

```bash
# Ver todas las dependencias instaladas
pip3 list

# Ver dependencias de un paquete específico
pip3 show python-gvm

# Verificar imports críticos
python3 -c "import gvm; import pandas; import boto3; import msal; print('✅ Todas las dependencias críticas OK')"
```

---

## ⚠️ Warnings Conocidos

### CryptographyDeprecationWarning (TripleDES)
```
CryptographyDeprecationWarning: TripleDES has been moved to 
cryptography.hazmat.decrepit.ciphers.algorithms.TripleDES
```
**Causa:** Paramiko usa TripleDES que está deprecado  
**Impacto:** Solo warning, no afecta funcionalidad  
**Solución:** Actualizar paramiko cuando haya versión nueva

### GMP Version Warning
```
Remote manager daemon uses a newer GMP version then supported 
by python-gvm 26.1.0
```
**Causa:** GVM 22.7 vs python-gvm soporta hasta 22.6  
**Impacto:** Solo warning, sigue funcionando  
**Solución:** Actualizar python-gvm cuando soporte GMP 22.7

---

## 📊 Dependencias por Archivo

| Archivo | Dependencias Principales |
|---------|-------------------------|
| `set-tt.py` | python-gvm, pandas |
| `run-task.py` | python-gvm |
| `get-reports-test.py` | python-gvm, pandas, untangle, openpyxl |
| `delete-files.py` | python-gvm |
| `upload-reports.py` | boto3, awscli |
| `subida_share.py` | msal, requests |

---

## 🔄 Actualizar Dependencias

```bash
# Ver dependencias desactualizadas
pip3 list --outdated

# Actualizar todas (cuidado!)
pip3 install --upgrade -r requirements.txt

# Actualizar solo una
pip3 install --upgrade python-gvm
```

---

## 💾 Exportar Dependencias Actuales

```bash
# Exportar exactamente lo instalado
pip3 freeze > requirements-frozen.txt

# Exportar solo dependencias top-level
pip3 list --format=freeze | grep -E "^(python-gvm|pandas|boto3|msal|openpyxl)" > requirements-minimal-frozen.txt
```


