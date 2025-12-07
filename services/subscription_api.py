"""
Сервис для получения подписок пользователя через API 3x-ui
"""
import logging
from typing import Optional, Dict, Any, List
from utils.db import get_user_by_tg_id, get_user_subscriptions, get_server_by_id, get_user_by_id
from services.x3ui_api import get_x3ui_client

logger = logging.getLogger(__name__)


async def get_user_subscription_by_sub_id(
    sub_id: str,
    server_id: Optional[int] = None
) -> Optional[str]:
    """
    Получает подписку пользователя по его subId через API 3x-ui.
    
    Args:
        sub_id: SubId пользователя
        server_id: ID сервера (опционально, если не указан - используется первый доступный)
        
    Returns:
        Строка с подпиской (vless:// ссылки) или None
    """
    if not sub_id:
        logger.warning("⚠️ SubId не указан")
        return None
    
    logger.info(f"🔍 Получение подписки по subId: {sub_id}")
    
    # Если server_id не указан, находим первый доступный сервер
    if not server_id:
        # Пытаемся найти пользователя по subId через БД
        # Ищем пользователя с таким sub_id
        from database.base import async_session
        from database.models import User
        from sqlalchemy import select
        
        async with async_session() as session:
            result = await session.execute(
                select(User).where(User.sub_id == sub_id)
            )
            user = result.scalar_one_or_none()
            
            if user:
                # Получаем подписки пользователя
                subscriptions = await get_user_subscriptions(user.id)
                if subscriptions:
                    # Используем первый доступный сервер
                    server_id = subscriptions[0].server_id
                    logger.info(f"   Найден пользователь, используется сервер #{server_id}")
    
    if not server_id:
        logger.warning("⚠️ Не удалось определить сервер для получения подписки")
        return None
    
    # Получаем сервер
    server = await get_server_by_id(server_id)
    if not server:
        logger.error(f"❌ Сервер #{server_id} не найден")
        return None
    
    logger.info(f"   Сервер: {server.name} ({server.api_url})")
    
    try:
        # Создаем клиент 3x-ui API
        x3ui_client = get_x3ui_client(
            server.api_url,
            server.api_username,
            server.api_password,
            server.ssl_certificate
        )
        
        # Получаем ключи для всех клиентов в подписке через шаблон
        client_keys = await x3ui_client.get_client_keys_from_subscription(
            sub_id
        )
        
        await x3ui_client.close()
        
        if client_keys:
            # Формируем строку подписки из всех ключей
            subscription_lines = []
            for key_info in client_keys:
                vless_link = key_info.get("vless_link")
                if vless_link:
                    subscription_lines.append(vless_link)
            
            if subscription_lines:
                subscription = "\n".join(subscription_lines)
                logger.info(f"✅ Подписка сгенерирована успешно ({len(subscription_lines)} ключей)")
                return subscription
            else:
                logger.warning(f"⚠️ Не удалось сгенерировать ключи для подписки с subId {sub_id}")
                return None
        else:
            logger.warning(f"⚠️ Подписка не найдена по subId {sub_id} на сервере #{server_id}")
            return None
            
    except Exception as e:
        logger.error(f"❌ Ошибка при получении подписки: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return None


async def get_user_subscription_by_tg_id(
    tg_id: str,
    server_id: Optional[int] = None
) -> Optional[str]:
    """
    Получает подписку пользователя по его Telegram ID через API 3x-ui.
    
    Args:
        tg_id: Telegram ID пользователя
        server_id: ID сервера (опционально, если не указан - используется первый доступный)
        
    Returns:
        Строка с подпиской (vless:// ссылки) или None
    """
    if not tg_id:
        logger.warning("⚠️ Telegram ID не указан")
        return None
    
    logger.info(f"🔍 Получение подписки по Telegram ID: {tg_id}")
    
    # Получаем пользователя из БД
    user = await get_user_by_tg_id(tg_id)
    if not user:
        logger.warning(f"⚠️ Пользователь с Telegram ID {tg_id} не найден")
        return None
    
    if not user.sub_id:
        logger.warning(f"⚠️ У пользователя нет subId")
        return None
    
    # Используем subId для получения подписки
    if not server_id:
        subscriptions = await get_user_subscriptions(user.id)
        if subscriptions:
            server_id = subscriptions[0].server_id
    
    return await get_user_subscription_by_sub_id(user.sub_id, server_id)


async def get_user_subscription_details(
    sub_id: str,
    server_id: Optional[int] = None
) -> Optional[Dict[str, Any]]:
    """
    Получает детальную информацию о подписке пользователя по его subId.
    
    Args:
        sub_id: SubId пользователя
        server_id: ID сервера (опционально)
        
    Returns:
        Словарь с детальной информацией о подписке или None
    """
    if not sub_id:
        logger.warning("⚠️ SubId не указан")
        return None
    
    logger.info(f"🔍 Получение детальной информации о подписке по subId: {sub_id}")
    
    # Находим сервер
    if not server_id:
        from database.base import async_session
        from database.models import User
        from sqlalchemy import select
        
        async with async_session() as session:
            result = await session.execute(
                select(User).where(User.sub_id == sub_id)
            )
            user = result.scalar_one_or_none()
            
            if user:
                subscriptions = await get_user_subscriptions(user.id)
                if subscriptions:
                    server_id = subscriptions[0].server_id
    
    if not server_id:
        logger.warning("⚠️ Не удалось определить сервер")
        return None
    
    server = await get_server_by_id(server_id)
    if not server:
        logger.error(f"❌ Сервер #{server_id} не найден")
        return None
    
    try:
        x3ui_client = get_x3ui_client(
            server.api_url,
            server.api_username,
            server.api_password,
            server.ssl_certificate
        )
        
        # Получаем детальную информацию о клиентах
        subscription_clients = await x3ui_client.get_subscription_by_sub_id(sub_id)
        
        # Получаем ключи через шаблон
        client_keys = await x3ui_client.get_client_keys_from_subscription(
            sub_id
        )
        
        # Формируем subscription_link из всех ключей
        subscription_link = None
        if client_keys:
            subscription_lines = []
            for key_info in client_keys:
                vless_link = key_info.get("vless_link")
                if vless_link:
                    subscription_lines.append(vless_link)
            if subscription_lines:
                subscription_link = "\n".join(subscription_lines)
        
        await x3ui_client.close()
        
        return {
            "sub_id": sub_id,
            "server_id": server_id,
            "server_name": server.name,
            "subscription_link": subscription_link,
            "clients": subscription_clients,
            "client_keys": client_keys
        }
        
    except Exception as e:
        logger.error(f"❌ Ошибка при получении детальной информации: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return None

