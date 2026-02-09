#!/usr/bin/env python3
"""
Script para obtener el chat_id de canales y grupos de Telegram
"""

import sys
import requests
import json

def obtener_chat_id(bot_token):
    """Obtiene el chat_id de canales y grupos desde la API de Telegram"""
    url = f"https://api.telegram.org/bot{bot_token}/getUpdates"
    
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        if not data.get('ok'):
            print(f"Error de API: {data.get('description', 'Error desconocido')}")
            return None
        
        updates = data.get('result', [])
        
        if not updates:
            print("No se encontraron mensajes.")
            print("\nAsegúrate de:")
            print("1. Haber añadido el bot al grupo/canal como administrador")
            print("2. Haber enviado al menos un mensaje al grupo/canal")
            return None
        
        # Buscar todos los chats (canales, grupos, supergrupos)
        chats_encontrados = {}
        
        for update in updates:
            chat = None
            
            # Buscar en diferentes tipos de updates
            if 'channel_post' in update:
                chat = update['channel_post'].get('chat', {})
            elif 'message' in update:
                chat = update['message'].get('chat', {})
            elif 'edited_channel_post' in update:
                chat = update['edited_channel_post'].get('chat', {})
            elif 'edited_message' in update:
                chat = update['edited_message'].get('chat', {})
            
            if not chat:
                continue
            
            chat_id = chat.get('id')
            chat_type = chat.get('type')
            chat_title = chat.get('title', chat.get('first_name', chat.get('username', 'Sin nombre')))
            
            # Buscar canales, grupos y supergrupos
            if chat_type in ['channel', 'group', 'supergroup'] and chat_id:
                if chat_id not in chats_encontrados:
                    chats_encontrados[chat_id] = {
                        'id': chat_id,
                        'type': chat_type,
                        'title': chat_title,
                        'username': chat.get('username', 'N/A')
                    }
        
        if chats_encontrados:
            print("\n" + "="*60)
            print("CHATS ENCONTRADOS:")
            print("="*60)
            
            # Separar por tipo
            canales = {k: v for k, v in chats_encontrados.items() if v['type'] == 'channel'}
            grupos = {k: v for k, v in chats_encontrados.items() if v['type'] in ['group', 'supergroup']}
            
            if canales:
                print("\n📢 CANALES:")
                for chat_id, info in canales.items():
                    print(f"\n   Canal: {info['title']}")
                    print(f"   Chat ID: {chat_id}")
                    if info['username'] != 'N/A':
                        print(f"   Username: @{info['username']}")
            
            if grupos:
                print("\n👥 GRUPOS:")
                for chat_id, info in grupos.items():
                    tipo_str = "Supergrupo" if info['type'] == 'supergroup' else "Grupo"
                    print(f"\n   {tipo_str}: {info['title']}")
                    print(f"   Chat ID: {chat_id}")
                    if info['username'] != 'N/A':
                        print(f"   Username: @{info['username']}")
            
            print("\n" + "="*60)
            print("\n✅ Copia el Chat ID y úsalo en config.json")
            
            # Si solo hay uno, mostrarlo destacado
            if len(chats_encontrados) == 1:
                chat_id = list(chats_encontrados.keys())[0]
                chat_info = list(chats_encontrados.values())[0]
                print(f"\n💡 Tu chat_id es: {chat_id}")
                print(f"   Tipo: {chat_info['type']}")
                print(f"   Nombre: {chat_info['title']}")
            
            return list(chats_encontrados.keys())
        else:
            print("\n⚠️  No se encontraron canales ni grupos en los mensajes.")
            print("\nAsegúrate de:")
            print("1. Haber añadido el bot al grupo/canal como administrador")
            print("2. Haber enviado al menos un mensaje al grupo/canal")
            print("3. Que el bot tenga permisos para leer mensajes")
            print("\n💡 Tip: También puedes usar el bot @getidsbot:")
            print("   - Reenvía un mensaje del grupo a @getidsbot")
            print("   - Te mostrará el chat_id directamente")
            return None
            
    except requests.exceptions.RequestException as e:
        print(f"Error al conectar con la API de Telegram: {e}")
        return None
    except json.JSONDecodeError as e:
        print(f"Error al decodificar la respuesta JSON: {e}")
        return None
    except Exception as e:
        print(f"Error inesperado: {e}")
        return None

def main():
    print("="*60)
    print("Obtener Chat ID de Canales y Grupos de Telegram")
    print("="*60)
    
    if len(sys.argv) < 2:
        print("\nUso: python3 get_channel_id.py <BOT_TOKEN>")
        print("\nEjemplo:")
        print("  python3 get_channel_id.py 123456789:ABCdefGHIjklMNOpqrsTUVwxyz")
        print("\nNota: El bot debe estar añadido al grupo/canal como administrador")
        print("      y debe haber al menos un mensaje en el grupo/canal.")
        sys.exit(1)
    
    bot_token = sys.argv[1]
    
    print(f"\n🔍 Buscando canales y grupos...")
    print(f"   Bot Token: {bot_token[:10]}...{bot_token[-5:]}")
    
    chat_ids = obtener_chat_id(bot_token)
    
    if not chat_ids:
        sys.exit(1)

if __name__ == '__main__':
    main()

