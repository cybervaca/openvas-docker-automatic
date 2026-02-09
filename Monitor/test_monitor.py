#!/usr/bin/env python3
"""
Script de prueba para el servicio de monitoreo
Ejecuta las verificaciones y muestra resultados detallados
"""

import sys
import json
import os

# Añadir el directorio Monitor al path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from monitor import (
    leer_configuracion,
    verificar_contenedor,
    verificar_docker_daemon,
    enviar_telegram,
    puede_enviar_alerta,
    ejecutar_verificaciones,
    enviar_alertas
)

def main():
    print("="*60)
    print("TEST DEL SERVICIO DE MONITOREO")
    print("="*60)
    
    # Leer configuración
    print("\n1. Leyendo configuración...")
    try:
        config = leer_configuracion()
        print("   ✓ Configuración leída correctamente")
    except Exception as e:
        print(f"   ✗ Error: {e}")
        sys.exit(1)
    
    # Verificar sección monitoring
    print("\n2. Verificando sección monitoring...")
    monitoring_config = config.get('monitoring', {})
    if not monitoring_config:
        print("   ✗ No se encontró la sección 'monitoring' en config.json")
        sys.exit(1)
    
    enabled = monitoring_config.get('enabled', False)
    print(f"   Monitoreo habilitado: {enabled}")
    
    if not enabled:
        print("   ⚠️  El monitoreo está deshabilitado. Habilítalo en config.json")
        sys.exit(1)
    
    # Verificar Telegram
    print("\n3. Verificando configuración de Telegram...")
    telegram_config = monitoring_config.get('telegram', {})
    bot_token = telegram_config.get('bot_token')
    chat_id = telegram_config.get('chat_id')
    
    if not bot_token:
        print("   ✗ bot_token no configurado")
        sys.exit(1)
    else:
        print(f"   ✓ bot_token: {bot_token[:10]}...{bot_token[-5:]}")
    
    if not chat_id:
        print("   ✗ chat_id no configurado")
        sys.exit(1)
    else:
        print(f"   ✓ chat_id: {chat_id} (tipo: {type(chat_id).__name__})")
        # Verificar que chat_id sea string
        if not isinstance(chat_id, str):
            print(f"   ⚠️  ADVERTENCIA: chat_id debe ser string, no {type(chat_id).__name__}")
            print(f"   En config.json debe estar entre comillas: \"chat_id\": \"{chat_id}\"")
        
        # Verificar que sea el chat_id del supergrupo (debe empezar con -100)
        if not str(chat_id).startswith('-100'):
            print(f"   ⚠️  ADVERTENCIA: El chat_id parece ser de un grupo normal, no del supergrupo")
            print(f"   El supergrupo 'RedTeam-Corp-Atento' tiene chat_id: -1003719877339")
            print(f"   Actualmente configurado: {chat_id}")
            print(f"   Considera actualizar config.json con el chat_id del supergrupo")
    
    # Test de envío de Telegram
    print("\n4. Probando envío a Telegram...")
    test_message = "🧪 <b>Test de Monitoreo OpenVAS</b>\n\nEste es un mensaje de prueba del servicio de monitoreo."
    try:
        if enviar_telegram(test_message, bot_token, str(chat_id)):
            print("   ✓ Mensaje de prueba enviado correctamente")
        else:
            print("   ✗ Error al enviar mensaje de prueba")
            print("   Verifica que:")
            print("   - El bot_token sea correcto")
            print("   - El chat_id sea correcto")
            print("   - El bot esté añadido al grupo/canal")
    except Exception as e:
        print(f"   ✗ Error de conexión: {e}")
        print("\n   ⚠️  PROBLEMA DE RED DETECTADO:")
        print("   - El servidor no puede conectarse a api.telegram.org")
        print("   - Posibles causas:")
        print("     * Firewall bloqueando salida HTTPS (puerto 443)")
        print("     * Proxy necesario (configurar variables HTTP_PROXY/HTTPS_PROXY)")
        print("     * Red no configurada correctamente")
        print("\n   Soluciones:")
        print("   1. Verificar conectividad: curl -I https://api.telegram.org")
        print("   2. Si hay proxy, configurar:")
        print("      export HTTPS_PROXY=http://proxy:puerto")
        print("   3. Verificar reglas de firewall")
    
    # Verificar contenedor
    print("\n5. Verificando contenedor Docker...")
    contenedor = verificar_contenedor()
    print(f"   Estado: {contenedor['status']}")
    print(f"   Mensaje: {contenedor['message']}")
    
    # Verificar Docker daemon
    print("\n6. Verificando Docker daemon...")
    docker = verificar_docker_daemon()
    print(f"   Estado: {docker['status']}")
    print(f"   Mensaje: {docker['message']}")
    
    # Verificar cooldown
    print("\n7. Verificando cooldown...")
    if puede_enviar_alerta('monitoring', config):
        print("   ✓ Puede enviar alerta de monitoreo (no hay cooldown activo)")
    else:
        print("   ⚠️  Cooldown activo para alerta de monitoreo")
        print("   (Se envió una alerta recientemente, espera el tiempo de cooldown)")
        print("   Para resetear el cooldown, elimina: /opt/gvm/logs/monitoring/alert_cooldown.json")
    
    # Ejecutar todas las verificaciones
    print("\n8. Ejecutando todas las verificaciones...")
    resultados = ejecutar_verificaciones(config)
    print(f"   Estado general: {resultados['status']}")
    print(f"   Checks:")
    for check, status in resultados['checks'].items():
        print(f"     - {check}: {status}")
    
    # Intentar enviar alertas
    print("\n9. Intentando enviar alertas...")
    enviar_alertas(resultados, config)
    if resultados['alerts_sent']:
        print(f"   ✓ Alertas enviadas: {', '.join(resultados['alerts_sent'])}")
    else:
        print("   ⚠️  No se enviaron alertas")
        print("   Razones posibles:")
        print("   - Todos los checks están OK")
        print("   - Cooldown activo")
        print("   - Alertas deshabilitadas en configuración")
    
    print("\n" + "="*60)
    print("TEST COMPLETADO")
    print("="*60)

if __name__ == '__main__':
    main()

