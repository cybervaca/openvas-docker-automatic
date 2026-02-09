#!/usr/bin/env python3
"""
Script de diagnóstico para problemas de envío de alertas
"""

import sys
import os
import json
import datetime

# Añadir el directorio Monitor al path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from monitor import (
    leer_configuracion,
    leer_configuracion_monitor,
    ejecutar_verificaciones,
    enviar_alertas,
    cargar_cooldown,
    puede_enviar_alerta,
    ALERT_COOLDOWN_FILE
)

def main():
    print("="*60)
    print("DIAGNÓSTICO DE ALERTAS")
    print("="*60)
    
    # 1. Verificar configuración
    print("\n1. Verificando configuración...")
    try:
        config = leer_configuracion()
        print("   ✓ Configuración leída")
    except Exception as e:
        print(f"   ✗ Error: {e}")
        return
    
    monitoring_config = config.get('monitoring', {})
    if not monitoring_config.get('enabled', False):
        print("   ✗ Monitoreo deshabilitado")
        return
    
    # 2. Verificar cooldown
    print("\n2. Verificando cooldown...")
    cooldown_data = cargar_cooldown()
    print(f"   Archivo cooldown: {ALERT_COOLDOWN_FILE}")
    print(f"   Existe: {os.path.exists(ALERT_COOLDOWN_FILE)}")
    print(f"   Contenido: {cooldown_data}")
    
    puede = puede_enviar_alerta('monitoring', config)
    print(f"   Puede enviar: {puede}")
    
    if 'monitoring' in cooldown_data:
        ultimo_envio = datetime.datetime.fromisoformat(cooldown_data['monitoring'])
        tiempo_transcurrido = (datetime.datetime.now() - ultimo_envio).total_seconds()
        cooldown_seconds = monitoring_config.get('alert_cooldown', 3600)
        tiempo_restante = cooldown_seconds - tiempo_transcurrido
        print(f"   Último envío: {ultimo_envio}")
        print(f"   Tiempo transcurrido: {int(tiempo_transcurrido)}s")
        print(f"   Cooldown configurado: {cooldown_seconds}s")
        print(f"   Tiempo restante: {int(tiempo_restante)}s")
    
    # 3. Ejecutar verificaciones
    print("\n3. Ejecutando verificaciones...")
    resultados = ejecutar_verificaciones(config)
    print(f"   Estado: {resultados['status']}")
    print(f"   Checks: {resultados['checks']}")
    
    # 4. Verificar si hay problemas
    print("\n4. Verificando si hay problemas...")
    checks = resultados['checks']
    tiene_problemas = False
    
    if monitoring_config.get('alert_on_container_down', True) and checks.get('container') != 'ok':
        tiene_problemas = True
        print("   ✓ Problema detectado: container")
    
    if monitoring_config.get('alert_on_docker_down', True) and checks.get('docker') != 'ok':
        tiene_problemas = True
        print("   ✓ Problema detectado: docker")
    
    if monitoring_config.get('alert_on_gvm_down', True):
        if checks.get('gvmd') != 'ok' or checks.get('gvm_connection') != 'ok':
            tiene_problemas = True
            print("   ✓ Problema detectado: gvm")
    
    
    if not tiene_problemas:
        print("   ⚠️  No hay problemas detectados según configuración")
    
    # 5. Intentar enviar alertas
    print("\n5. Intentando enviar alertas...")
    print(f"   Tiene problemas: {tiene_problemas}")
    print(f"   Puede enviar (cooldown): {puede}")
    
    if tiene_problemas and puede:
        print("   → Enviando alerta...")
        enviar_alertas(resultados, config)
        if resultados.get('alerts_sent'):
            print(f"   ✓ Alertas enviadas: {resultados['alerts_sent']}")
        else:
            print("   ✗ No se enviaron alertas")
            print("   Revisa los logs para más detalles")
    elif tiene_problemas and not puede:
        print("   ⚠️  Hay problemas pero cooldown está activo")
        print("   Para forzar envío, elimina el archivo de cooldown:")
        print(f"   rm {ALERT_COOLDOWN_FILE}")
    else:
        print("   ⚠️  No hay problemas que reportar")
    
    print("\n" + "="*60)
    print("DIAGNÓSTICO COMPLETADO")
    print("="*60)

if __name__ == '__main__':
    main()



