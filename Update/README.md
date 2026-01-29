# Update Scripts

Scripts para actualizar componentes de OpenVAS/GVM.

## Archivos

### update.py
Script simple para verificar y actualizar OpenVAS Scanner.

**Funcionalidad:**
- Lee versión actual de `version.txt`
- Obtiene última versión de GitHub (greenbone/openvas-scanner)
- Si hay nueva versión, ejecuta `update-scanner.sh`
- Envía notificación por email (comentado)

**Uso:**
```bash
cd /opt/gvm/Update
python3 update.py
```

### update-versiones.py
Script avanzado para actualizar múltiples componentes GVM.

**Componentes soportados:**
- GVM_LIBS_VERSION
- GVMD_VERSION
- PG_GVM_VERSION
- GSA_VERSION
- GSAD_VERSION
- OPENVAS_SMB_VERSION
- OPENVAS_SCANNER_VERSION
- OSPD_OPENVAS_VERSION
- NOTUS_VERSION
- REDIS_VERSION

**Funcionalidad:**
- Obtiene últimas versiones de todos los componentes desde GitHub
- Compara con versiones instaladas
- Actualiza si hay diferencias
- Genera log en `/opt/gvm/logupdates.txt`
- Guarda resultado en `/opt/gvm/resultado.json`
- Envía email con resumen (comentado)

**Uso:**
```bash
cd /opt/gvm/Update
python3 update-versiones.py
```

### update-script.py
Script con funcionalidad de actualización automática del repositorio.

**Funcionalidad:**
1. Descarga `export-target.py` desde GitHub
2. Ejecuta export de targets actuales a `openvas.csv.export`
3. Hace git pull forzado del repositorio
4. Restaura `openvas.csv` desde el backup

**Uso:**
```bash
cd /opt/gvm/Update
python3 update-script.py

# Forzar actualización
python3 update-script.py --force
```

**Argumentos:**
- `--force`: Forzar actualización aunque la versión sea la misma

### update-scanner.sh
Script bash para compilar e instalar OpenVAS Scanner.

**Funcionalidad:**
- Descarga el código fuente de una versión específica
- Verifica firma GPG
- Compila con cmake
- Instala en el sistema

**Uso:**
```bash
cd /opt/gvm/Update
./update-scanner.sh 23.0.1
```

**Parámetros:**
- `$1`: Versión de OpenVAS Scanner (ej: 23.0.1)

**Directorios usados:**
- Source: `/opt/gvm/source/`
- Build: `/opt/gvm/build/openvas-scanner/`
- Install: `/opt/gvm/install/`

### update-ospd.sh
Script bash para actualizar OSPD-OpenVAS (OpenVAS Protocol Daemon).

**Funcionalidad:**
- Descarga el código fuente de una versión específica
- Verifica firma GPG
- Instala con pip3

**Uso:**
```bash
cd /opt/gvm/Update
./update-ospd.sh 22.6.0
```

**Parámetros:**
- `$1`: Versión de OSPD-OpenVAS (ej: 22.6.0)

### version.txt
Archivo de texto simple que almacena la última versión conocida de OpenVAS Scanner.

**Formato:**
```
23.0.1
```

## Requisitos

### Dependencias Python
```bash
pip3 install requests beautifulsoup4
```

### Herramientas del sistema
- git
- gpg
- cmake
- make
- gcc/g++
- python3
- pip3

### Claves GPG de Greenbone
Para verificar firmas:
```bash
# Importar clave pública de Greenbone
gpg --keyserver keys.openpgp.org --recv-keys 8AE4BE429B60A59B311C2E739823FAA60ED1E580
```

## Consideraciones

### Entornos Docker
Estos scripts están diseñados para **instalaciones nativas** de OpenVAS. En entornos Docker:

- ❌ No usar estos scripts directamente en contenedores
- ✅ Actualizar la imagen Docker: `docker-compose pull && docker-compose up -d`
- ✅ Los scripts pueden ejecutarse en el host si OpenVAS está instalado nativamente

### Permisos
Los scripts de compilación requieren permisos sudo para instalar componentes del sistema.

### Tiempo de Ejecución
- `update.py`: 1-2 minutos
- `update-scanner.sh`: 5-15 minutos (compilación)
- `update-ospd.sh`: 1-3 minutos
- `update-versiones.py`: 2-5 minutos

### Logs
- `/opt/gvm/logupdates.txt`: Log de actualizaciones
- `/opt/gvm/resultado.json`: Últimas versiones obtenidas de GitHub

## Flujo de Actualización Recomendado

### Actualización Manual de OpenVAS Scanner

```bash
# 1. Verificar versión actual
openvas -V

# 2. Obtener última versión
cd /opt/gvm/Update
python3 update.py

# 3. O manualmente especificar versión
./update-scanner.sh 23.0.1

# 4. Verificar instalación
openvas -V

# 5. Reiniciar servicios
sudo systemctl restart ospd-openvas
sudo systemctl restart gvmd
```

### Actualización de Múltiples Componentes

```bash
# 1. Hacer backup de configuración
cd /opt/gvm
tar czf backup-$(date +%Y%m%d).tar.gz Config/ Targets_Tasks/openvas.csv

# 2. Ejecutar update-versiones.py
cd Update
python3 update-versiones.py

# 3. Revisar logs
cat /opt/gvm/logupdates.txt
cat /opt/gvm/resultado.json

# 4. Reiniciar todos los servicios
sudo systemctl restart gvmd
sudo systemctl restart ospd-openvas
sudo systemctl restart gsad
sudo systemctl restart notus-scanner
```

### Actualización del Repositorio de Scripts

```bash
# 1. Ejecutar update-script.py (hace backup automático)
cd /opt/gvm/Update
python3 update-script.py

# 2. O manualmente
cd /opt/gvm
git pull origin main

# 3. Actualizar dependencias si es necesario
source gvm/bin/activate
pip3 install -r requirements.txt --upgrade
```

## Automatización con Cron

### Actualización semanal de OpenVAS Scanner
```bash
crontab -e
```

Agregar:
```cron
# Verificar actualizaciones de OpenVAS Scanner cada domingo a las 3:00 AM
0 3 * * 0 /usr/bin/python3 /opt/gvm/Update/update.py >> /opt/gvm/logs/update.log 2>&1
```

### Actualización mensual de componentes
```cron
# Verificar actualizaciones de todos los componentes el primer día del mes
0 4 1 * * /usr/bin/python3 /opt/gvm/Update/update-versiones.py >> /opt/gvm/logs/update-versiones.log 2>&1
```

## Troubleshooting

### Error: No se puede descargar desde GitHub
```bash
# Verificar conectividad
curl -I https://github.com

# Verificar proxy si es necesario
export HTTP_PROXY=http://proxy:8080
export HTTPS_PROXY=http://proxy:8080
```

### Error: Falla verificación GPG
```bash
# Importar clave de Greenbone
gpg --keyserver keys.openpgp.org --recv-keys 8AE4BE429B60A59B311C2E739823FAA60ED1E580

# O descargar manualmente
wget https://www.greenbone.net/GBCommunitySigningKey.asc
gpg --import GBCommunitySigningKey.asc
```

### Error: Falla compilación
```bash
# Verificar dependencias
sudo apt-get install -y \
  build-essential cmake pkg-config \
  libglib2.0-dev libgpgme-dev libgnutls28-dev uuid-dev \
  libssh-gcrypt-dev libhiredis-dev libxml2-dev libpcap-dev \
  libnet1-dev libpaho-mqtt-dev libbsd-dev libgcrypt20-dev

# Limpiar directorios de build
rm -rf /opt/gvm/build/*
rm -rf /opt/gvm/source/*
```

### Error: Falta espacio en disco
```bash
# Verificar espacio
df -h

# Limpiar archivos temporales
rm -rf /opt/gvm/build/*
rm -rf /opt/gvm/source/*
rm -rf /opt/gvm/install/*
```

## Notas Importantes

1. **Backup**: Siempre hacer backup antes de actualizar componentes críticos
2. **Feeds**: Después de actualizar, ejecutar sincronización de feeds:
   ```bash
   sudo greenbone-feed-sync --type GVMD_DATA
   sudo greenbone-feed-sync --type SCAP
   sudo greenbone-feed-sync --type CERT
   ```
3. **Servicios**: Reiniciar servicios después de cada actualización
4. **Testing**: Verificar funcionalidad después de actualizar (crear target de prueba y ejecutar scan)
5. **Docker**: Si usas Docker, es preferible actualizar la imagen del contenedor en lugar de compilar manualmente

## Referencias

- [Greenbone GitHub](https://github.com/greenbone)
- [OpenVAS Scanner Releases](https://github.com/greenbone/openvas-scanner/releases)
- [GVM Building Guide](https://greenbone.github.io/docs/latest/building.html)
- [Documentación GVM](https://docs.greenbone.net/)

