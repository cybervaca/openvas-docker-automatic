#!/usr/bin/env python3
"""
Script para verificar conectividad de red con Telegram API
"""

import requests
import sys
import os

def check_telegram_api():
    """Verifica conectividad con la API de Telegram"""
    print("="*60)
    print("VERIFICACIÓN DE CONECTIVIDAD CON TELEGRAM API")
    print("="*60)
    
    # Verificar variables de proxy
    print("\n1. Verificando configuración de proxy...")
    http_proxy = os.environ.get('HTTP_PROXY') or os.environ.get('http_proxy')
    https_proxy = os.environ.get('HTTPS_PROXY') or os.environ.get('https_proxy')
    
    if http_proxy:
        print(f"   HTTP_PROXY: {http_proxy}")
    else:
        print("   HTTP_PROXY: No configurado")
    
    if https_proxy:
        print(f"   HTTPS_PROXY: {https_proxy}")
    else:
        print("   HTTPS_PROXY: No configurado")
    
    if not http_proxy and not https_proxy:
        print("   ⚠️  Si necesitas proxy, configura:")
        print("      export HTTPS_PROXY=http://proxy:puerto")
    
    # Test de conectividad básica
    print("\n2. Verificando conectividad básica...")
    try:
        response = requests.get('https://api.telegram.org', timeout=10)
        print(f"   ✓ Conectividad OK (Status: {response.status_code})")
    except requests.exceptions.ConnectionError as e:
        print(f"   ✗ Error de conexión: {e}")
        print("\n   Posibles soluciones:")
        print("   1. Verificar firewall (puerto 443 debe estar abierto)")
        print("   2. Verificar DNS: nslookup api.telegram.org")
        print("   3. Verificar ruta: traceroute api.telegram.org")
        print("   4. Si hay proxy corporativo, configurar HTTPS_PROXY")
        return False
    except Exception as e:
        print(f"   ✗ Error: {e}")
        return False
    
    # Test de endpoint específico
    print("\n3. Verificando endpoint de Telegram...")
    try:
        # Endpoint que no requiere autenticación
        response = requests.get('https://api.telegram.org/bot123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11/getMe', timeout=10)
        # Esperamos un 401 (Unauthorized) pero significa que el endpoint responde
        if response.status_code in [401, 400]:
            print(f"   ✓ Endpoint responde (Status: {response.status_code})")
            print("   ✓ La API de Telegram es accesible")
            return True
        else:
            print(f"   ⚠️  Status inesperado: {response.status_code}")
            return True
    except requests.exceptions.ConnectionError as e:
        print(f"   ✗ No se puede conectar a api.telegram.org")
        print(f"   Error: {e}")
        return False
    except Exception as e:
        print(f"   ✗ Error: {e}")
        return False

def main():
    if check_telegram_api():
        print("\n" + "="*60)
        print("✓ CONECTIVIDAD OK - El servicio debería funcionar")
        print("="*60)
        sys.exit(0)
    else:
        print("\n" + "="*60)
        print("✗ PROBLEMA DE CONECTIVIDAD DETECTADO")
        print("="*60)
        print("\nEl servicio de monitoreo NO podrá enviar alertas por Telegram")
        print("hasta que se resuelva el problema de red.")
        sys.exit(1)

if __name__ == '__main__':
    main()







