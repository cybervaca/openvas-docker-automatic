# Export Target Script

Script para exportar todos los targets configurados en OpenVAS a un archivo CSV.

## export-target.py

Exporta todos los targets de OpenVAS al formato CSV compatible con `set-tt.py`.

### Funcionalidad

- ✅ Conecta a OpenVAS via TLS (puerto 9390)
- ✅ Exporta todos los targets sin límite de 1000 filas (usa paginación)
- ✅ Genera CSV con formato: `Titulo;Rango;Desc`
- ✅ Divide targets con múltiples rangos en filas separadas
- ✅ Compatible con Docker y entornos nativos

### Uso

```bash
cd /opt/gvm/Targets_Tasks

# Exportar con valores por defecto
python3 export-target.py

# Especificar archivo de salida
python3 export-target.py -o backup.csv

# Especificar config personalizado
python3 export-target.py -c /ruta/config.json -o targets_export.csv

# Ajustar tamaño de página (si tienes muchos targets)
python3 export-target.py --page-size 500
```

### Argumentos

| Argumento | Corto | Default | Descripción |
|-----------|-------|---------|-------------|
| `--config` | `-c` | `/opt/gvm/Config/config.json` | Ruta al archivo de configuración |
| `--output` | `-o` | `openvas.csv` | Archivo CSV de salida |
| `--page-size` | - | `1000` | Elementos por página (paginación) |

### Formato de Salida

El CSV generado tiene el formato:

```csv
Titulo;Rango;Desc
Red_Interna;192.168.1.0/24;Escaneo de red interna
Servidores_DMZ;10.0.1.10;Servidor web
Servidores_DMZ;10.0.1.11;Servidor DB
```

**Importante**: Si un target tiene múltiples rangos separados por comas, se genera una fila por cada rango.

### Casos de Uso

#### 1. Backup antes de Actualizar

```bash
# Crear backup antes de git pull
cd /opt/gvm/Targets_Tasks
python3 export-target.py -o openvas.csv.backup

# Actualizar repositorio
cd /opt/gvm
git pull origin main

# Si hay problemas, restaurar
cp openvas.csv.backup openvas.csv
```

#### 2. Migración entre Instancias

```bash
# En la instancia origen
python3 export-target.py -o targets_origen.csv

# Copiar a la instancia destino
scp targets_origen.csv user@destino:/opt/gvm/Targets_Tasks/openvas.csv

# En la instancia destino
cd /opt/gvm/Targets_Tasks
python3 set-tt.py
```

#### 3. Auditoría de Configuración

```bash
# Exportar y revisar targets actuales
python3 export-target.py -o audit_$(date +%Y%m%d).csv

# Ver contenido
cat audit_20260129.csv
```

#### 4. Integración con update-script.py

Este script es usado automáticamente por `update-script.py` para:
1. Hacer backup antes de `git pull`
2. Preservar configuración de targets
3. Restaurar después de la actualización

### Conexión

El script usa **TLSConnection** para conectar a OpenVAS:

```python
connection = TLSConnection(hostname="127.0.0.1", port=9390)
```

Esto garantiza compatibilidad con:
- ✅ Entornos Docker
- ✅ Instalaciones nativas
- ✅ Conexiones remotas (modificando hostname)

### Paginación

Para evitar el límite de 1000 filas de OpenVAS, el script:

1. Solicita targets en bloques (por defecto 1000)
2. Usa filtros `first=X rows=Y`
3. Itera hasta obtener todos los targets
4. Consolida en un único CSV

**Ejemplo de paginación:**
- Página 1: targets 1-1000
- Página 2: targets 1001-2000
- Página 3: targets 2001-...

### Configuración Requerida

El archivo `config.json` debe contener:

```json
{
  "user": "admin",
  "password": "contraseña_openvas",
  ...
}
```

### Ejemplo de Salida

```bash
$ python3 export-target.py -o export_test.csv
$ cat export_test.csv
Titulo;Rango;Desc
dc;192.168.1.10;Domain Controller
Servidores_Web;10.0.1.100;Servidor Apache
Servidores_Web;10.0.1.101;Servidor Nginx
Red_IoT;172.16.0.0/24;Dispositivos IoT
```

### Troubleshooting

#### Error: No se puede conectar a OpenVAS

```bash
# Verificar que OpenVAS esté corriendo
docker ps | grep openvas
# O en instalación nativa
sudo systemctl status gvmd

# Verificar puerto 9390
netstat -tuln | grep 9390
```

#### Error: Credenciales incorrectas

```bash
# Verificar config.json
cat /opt/gvm/Config/config.json | grep -E "user|password"

# Probar login manualmente
gvm-cli socket --socketpath /run/gvmd/gvmd.sock \
  --gmp-username admin --gmp-password PASSWORD
```

#### Error: CSV vacío

```bash
# Verificar que haya targets en OpenVAS
cd /opt/gvm/Targets_Tasks
python3 -c "
from gvm.connections import TLSConnection
from gvm.protocols.gmp import Gmp
import json

with open('/opt/gvm/Config/config.json') as f:
    config = json.load(f)

connection = TLSConnection(hostname='127.0.0.1', port=9390)
with Gmp(connection=connection) as gmp:
    gmp.authenticate(config['user'], config['password'])
    targets = gmp.get_targets()
    print(targets)
"
```

#### Error: Límite de paginación

Si tienes más de 10,000 targets, ajusta el page-size:

```bash
# Usar páginas más pequeñas
python3 export-target.py --page-size 500 -o large_export.csv
```

### Diferencias con Versiones Anteriores

| Característica | Versión Anterior | Esta Versión |
|---------------|------------------|--------------|
| Conexión | UnixSocketConnection | TLSConnection |
| Path socket | `/run/gvmd/gvmd.sock` | Puerto 9390 |
| Config path | Relativo `../Config/` | Absoluto `/opt/gvm/Config/` |
| Docker | ❌ No compatible | ✅ Compatible |
| Paginación | ✅ Sí | ✅ Sí |

### Integración con Flujo de Trabajo

```
┌─────────────────────┐
│ export-target.py    │──┐
│ (backup)            │  │
└─────────────────────┘  │
                         ▼
                    openvas.csv.export
                         │
                         │
┌─────────────────────┐  │
│ git pull origin     │◄─┘
│ (actualización)     │
└─────────────────────┘
         │
         ▼
┌─────────────────────┐
│ Restaurar CSV       │
│ desde backup        │
└─────────────────────┘
```

### Ver También

- `set-tt.py` - Script para importar targets desde CSV
- `run-task.py` - Script para ejecutar tasks
- `../Update/update-script.py` - Script de actualización que usa export-target.py

## Permisos

El script necesita:
- ✅ Lectura de `/opt/gvm/Config/config.json`
- ✅ Escritura en el directorio actual
- ✅ Conexión a OpenVAS (puerto 9390)

```bash
# Hacer ejecutable (opcional)
chmod +x export-target.py
```

## Dependencias

```bash
pip3 install python-gvm
```

Ya incluido en `requirements.txt` del proyecto.

