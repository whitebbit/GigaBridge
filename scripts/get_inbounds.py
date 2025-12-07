#!/usr/bin/env python3
"""
Скрипт для получения списка inbounds через API 3x-ui с подробным логированием

Использование:
    python scripts/get_inbounds.py
    python scripts/get_inbounds.py <api_url> <username> <password>
    
Пример:
    python scripts/get_inbounds.py http://89.169.7.60:30648/rolDT4Th57aiCxNzOi admin password123
"""
import sys
import argparse
from pathlib import Path

# Добавляем корневую директорию проекта в PYTHONPATH
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import asyncio
import json
import logging
from typing import Optional

from services.x3ui_api import get_x3ui_client, X3UIAPI

# Настройка логирования
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


async def get_first_active_server():
    """Получить первый активный сервер из БД"""
    try:
        from database.base import async_session
        from database.models import Server
        from sqlalchemy import select
        
        async with async_session() as session:
            result = await session.execute(
                select(Server).where(Server.is_active == True).limit(1)
            )
            server = result.scalar_one_or_none()
            return server
    except Exception as e:
        logger.debug(f"Не удалось подключиться к БД: {e}")
        return None


async def main():
    """Основная функция для получения inbounds"""
    parser = argparse.ArgumentParser(
        description='Получить список inbounds через API 3x-ui',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Примеры использования:
  # Получить из БД (требует подключения к БД):
  python scripts/get_inbounds.py
  
  # Указать параметры сервера напрямую:
  python scripts/get_inbounds.py http://89.169.7.60:30648/rolDT4Th57aiCxNzOi admin password123
        """
    )
    parser.add_argument('api_url', nargs='?', help='URL API сервера 3x-ui')
    parser.add_argument('username', nargs='?', help='Имя пользователя для входа')
    parser.add_argument('password', nargs='?', help='Пароль для входа')
    
    args = parser.parse_args()
    
    logger.info("=" * 80)
    logger.info("🚀 НАЧАЛО ПОЛУЧЕНИЯ СПИСКА INBOUNDS")
    logger.info("=" * 80)
    
    # Определяем параметры сервера
    api_url = None
    username = None
    password = None
    server_name = "Указанный сервер"
    
    if args.api_url and args.username and args.password:
        # Используем параметры из командной строки
        api_url = args.api_url
        username = args.username
        password = args.password
        server_name = "Командная строка"
        logger.info(f"\n📡 Используются параметры из командной строки")
    else:
        # Пытаемся получить из БД
        logger.info("\n📡 Получение активного сервера из БД...")
        try:
            server = await get_first_active_server()
            
            if server:
                api_url = server.api_url
                username = server.api_username
                password = server.api_password
                server_name = server.name
                logger.info(f"✅ Найден сервер в БД: {server.name}")
                logger.info(f"   ID: {server.id}")
            else:
                logger.warning("⚠️ Не найден активный сервер в базе данных")
        except Exception as e:
            logger.warning(f"⚠️ Не удалось подключиться к БД: {e}")
            logger.warning("   Используйте параметры командной строки")
    
    # Проверяем, что у нас есть все необходимые параметры
    if not api_url or not username or not password:
        logger.error("❌ Не указаны параметры сервера!")
        logger.error("")
        logger.error("Использование:")
        logger.error("  python scripts/get_inbounds.py")
        logger.error("  python scripts/get_inbounds.py <api_url> <username> <password>")
        logger.error("")
        logger.error("Пример:")
        logger.error("  python scripts/get_inbounds.py http://89.169.7.60:30648/rolDT4Th57aiCxNzOi admin password123")
        return
    
    logger.info(f"\n✅ Используемый сервер: {server_name}")
    logger.info(f"   API URL: {api_url}")
    logger.info(f"   Username: {username}")
    
    # Создаем клиент API
    logger.info(f"\n🔧 Создание клиента X3UIAPI...")
    x3ui_client: X3UIAPI = get_x3ui_client(
        api_url,
        username,
        password
    )
    
    try:
        # Получаем список inbounds
        logger.info(f"\n📋 Получение списка inbounds через API...")
        logger.info(f"   URL: {api_url}")
        logger.info(f"   Endpoint: /panel/api/inbounds/list")
        
        inbounds = await x3ui_client.get_inbounds()
        
        if not inbounds:
            logger.error("❌ Не удалось получить список inbounds")
            logger.error("   Проверьте подключение к серверу и учетные данные")
            return
        
        logger.info(f"\n✅✅✅ СПИСОК INBOUNDS УСПЕШНО ПОЛУЧЕН! ✅✅✅")
        logger.info(f"   Всего inbounds: {len(inbounds)}")
        logger.info("=" * 80)
        
        # Выводим информацию о каждом inbound
        for idx, inbound in enumerate(inbounds, 1):
            inbound_id = inbound.get("id", "N/A")
            protocol = inbound.get("protocol", "N/A")
            port = inbound.get("port", "N/A")
            tag = inbound.get("tag", "N/A")
            remark = inbound.get("remark", "N/A")
            sniffing = inbound.get("sniffing", {})
            clients = []
            
            # Парсим settings для получения клиентов
            settings_str = inbound.get("settings", "{}")
            try:
                settings = json.loads(settings_str) if isinstance(settings_str, str) else settings_str
                clients = settings.get("clients", [])
            except Exception as e:
                logger.debug(f"   Ошибка парсинга settings для inbound {idx}: {e}")
            
            logger.info(f"\n   📦 Inbound #{idx}:")
            logger.info(f"      ID: {inbound_id}")
            logger.info(f"      Protocol: {protocol}")
            logger.info(f"      Port: {port}")
            logger.info(f"      Tag: {tag}")
            logger.info(f"      Remark: {remark}")
            logger.info(f"      Клиентов: {len(clients)}")
            
            # Выводим информацию о клиентах
            if clients:
                logger.info(f"      Список клиентов:")
                for client_idx, client in enumerate(clients, 1):
                    client_id = client.get("id", "N/A")
                    client_email = client.get("email", "N/A")
                    sub_id = client.get("subId") or client.get("sub_id") or "N/A"
                    
                    logger.info(f"         Клиент #{client_idx}:")
                    logger.info(f"            ID: {client_id}")
                    logger.info(f"            Email: {client_email}")
                    logger.info(f"            SubId: {sub_id}")
            
            # Выводим streamSettings
            stream_settings = inbound.get("streamSettings", "{}")
            if stream_settings and stream_settings != "{}":
                logger.info(f"      StreamSettings:")
                try:
                    stream_settings_parsed = json.loads(stream_settings) if isinstance(stream_settings, str) else stream_settings
                    network = stream_settings_parsed.get("network", "N/A")
                    security = stream_settings_parsed.get("security", "N/A")
                    logger.info(f"         Network: {network}")
                    logger.info(f"         Security: {security}")
                except Exception as e:
                    logger.debug(f"         Не удалось распарсить streamSettings: {e}")
        
        logger.info("\n" + "=" * 80)
        logger.info("✅ ПРОЦЕСС ЗАВЕРШЕН УСПЕШНО")
        logger.info("=" * 80)
        
        # Сохраняем полный JSON в файл на ПК
        from datetime import datetime
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        json_filename = f"inbounds_{timestamp}.json"
        
        # Формируем полный JSON
        json_str = json.dumps(inbounds, indent=2, ensure_ascii=False)
        
        # Сохраняем в файл (в корне проекта, чтобы был доступен на хосте через Docker volume)
        try:
            output_path = project_root / json_filename
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(json_str)
            
            file_size_bytes = len(json_str.encode('utf-8'))
            file_size_kb = file_size_bytes / 1024
            file_size_mb = file_size_kb / 1024
            
            logger.info(f"\n💾💾💾 JSON СОХРАНЕН НА ВАШ ПК! 💾💾💾")
            logger.info(f"   📁 Имя файла: {json_filename}")
            logger.info(f"   📍 Полный путь: {output_path.absolute()}")
            
            if file_size_mb >= 1:
                logger.info(f"   📊 Размер: {file_size_mb:.2f} МБ ({file_size_bytes:,} байт)")
            elif file_size_kb >= 1:
                logger.info(f"   📊 Размер: {file_size_kb:.2f} КБ ({file_size_bytes:,} байт)")
            else:
                logger.info(f"   📊 Размер: {file_size_bytes:,} байт")
            
            logger.info(f"\n   ✅ Файл сохранен в корне проекта и доступен для полного анализа!")
            logger.info(f"   ✅ При запуске через Docker файл доступен в директории проекта на хосте")
        except Exception as save_error:
            logger.error(f"❌ Ошибка при сохранении JSON в файл: {save_error}")
            import traceback
            logger.error(traceback.format_exc())
        
        # Также выводим первые строки JSON для быстрого просмотра в консоли
        logger.info("\n📄 Полный JSON ответ (первые 2000 символов для просмотра в консоли):")
        logger.info(json_str[:2000])
        if len(json_str) > 2000:
            logger.info(f"... (еще {len(json_str) - 2000} символов)")
            logger.info(f"   💡 Полный JSON доступен в файле: {json_filename}")
        
    except Exception as e:
        logger.error(f"❌ Ошибка при получении inbounds: {e}")
        import traceback
        logger.error(traceback.format_exc())
    finally:
        await x3ui_client.close()


if __name__ == "__main__":
    asyncio.run(main())

