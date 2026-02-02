# Sistema de Gestión de Tareas Interrumpidas

## Descripción

El script `run-task.py` ahora incluye un sistema automático para detectar y gestionar tareas interrumpidas en OpenVAS/GVM.

## Funcionalidades

### 1. Detección de Tareas Interrumpidas
El script detecta automáticamente tareas con los estados:
- `Stopped`
- `Interrupted`

### 2. Sistema de Contador de Interrupciones
- Cada vez que se detecta una tarea interrumpida, se incrementa un contador específico para esa tarea
- Los contadores se almacenan de forma persistente en `/opt/gvm/Config/task_interruptions.json`
- El límite predeterminado es **3 interrupciones** por tarea

### 3. Recuperación Automática
Cuando una tarea se interrumpe (y no ha alcanzado el límite):
1. Se elimina el reporte fallido de la tarea
2. La tarea vuelve al estado `New`
3. Será relanzada automáticamente en la siguiente ejecución del script

### 4. Omisión de Tareas Problemáticas
Si una tarea se interrumpe 3 veces:
- La tarea se **omite** y no se volverá a intentar
- El script continúa con la siguiente tarea disponible
- Se registra en el log la razón de la omisión

### 5. Reseteo Automático
Cuando una tarea finaliza correctamente (estado `Done`):
- Su contador de interrupciones se resetea automáticamente a 0
- La tarea puede volver a ejecutarse normalmente en el futuro

## Archivo de Contador

**Ubicación**: `/opt/gvm/Config/task_interruptions.json`

**Estructura**:
```json
{
  "task-uuid-1": {
    "name": "Nombre de la tarea",
    "interruptions": 2
  },
  "task-uuid-2": {
    "name": "Otra tarea",
    "interruptions": 1
  }
}
```

## Logs

Todas las acciones relacionadas con tareas interrumpidas se registran en `/opt/gvm/taskslog.txt`:

- Detección de tareas interrumpidas
- Número de interrupciones acumuladas
- Eliminación de reportes
- Omisión de tareas que superaron el límite
- Reseteo de contadores cuando las tareas finalizan correctamente

## Configuración

Para modificar el límite de interrupciones, edita la variable `MAX_INTERRUPCIONES` en la función `start_task()`:

```python
MAX_INTERRUPCIONES = 3  # Cambiar este valor según necesidades
```

## Flujo de Ejecución

1. **Verificar tareas interrumpidas**
   - Si encuentra una tarea interrumpida → Incrementa contador
   - Si contador < 3 → Elimina reporte y resetea a `New`
   - Si contador >= 3 → Omite la tarea

2. **Verificar tareas en ejecución**
   - Si hay tareas corriendo → Espera (no lanza nuevas)

3. **Iniciar nuevas tareas**
   - Busca tareas en estado `New`
   - Verifica que no estén en la lista de omitidas
   - Lanza la primera tarea válida

4. **Procesar tareas finalizadas**
   - Si una tarea tiene estado `Done` → Resetea su contador
   - Exporta reportes cuando todas finalizan

## Ejemplo de Uso

El sistema funciona automáticamente. Solo ejecuta:

```bash
python3 /opt/gvm/Targets_Tasks/run-task.py
```

El script:
- Detectará automáticamente tareas interrumpidas
- Las recuperará hasta 3 veces
- Omitirá las que fallen persistentemente
- Continuará con las siguientes tareas disponibles

