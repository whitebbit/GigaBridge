"""
Сервис для управления подписками (создание, удаление и т.д.)
"""
import logging
from typing import Optional, Tuple
from utils.db import (
    get_subscription_by_id,
    delete_subscription,
    get_server_by_id,
    delete_all_user_subscriptions,
    get_user_subscriptions
)
from services.x3ui_api import get_x3ui_client

logger = logging.getLogger(__name__)


async def delete_subscription_completely(subscription_id: int) -> Tuple[bool, str]:
    """
    Полностью удалить подписку: из базы данных и из 3x-ui API
    
    Args:
        subscription_id: ID подписки для удаления
        
    Returns:
        Tuple[bool, str]: (успешно ли удалено, сообщение об ошибке или успехе)
    """
    try:
        # Получаем подписку из БД
        subscription = await get_subscription_by_id(subscription_id)
        if not subscription:
            return False, "Подписка не найдена в базе данных"
        
        # Удаляем клиента из 3x-ui API, если есть email
        if subscription.x3ui_client_email and subscription.server_id:
            try:
                server = await get_server_by_id(subscription.server_id)
                if server:
                    x3ui_client = get_x3ui_client(
                        server.api_url,
                        server.api_username,
                        server.api_password
                    )
                    
                    result = await x3ui_client.delete_client(subscription.x3ui_client_email)
                    await x3ui_client.close()
                    
                    if result and result.get("error"):
                        error_msg = result.get("message", "Неизвестная ошибка")
                        logger.warning(
                            f"⚠️ Не удалось удалить клиента {subscription.x3ui_client_email} "
                            f"из 3x-ui API: {error_msg}. Продолжаем удаление из БД."
                        )
                        # Продолжаем удаление из БД даже если не удалось удалить из API
                    else:
                        logger.info(
                            f"✅ Клиент {subscription.x3ui_client_email} успешно удален из 3x-ui API"
                        )
            except Exception as api_error:
                logger.error(
                    f"❌ Ошибка при удалении клиента из 3x-ui API: {api_error}. "
                    f"Продолжаем удаление из БД."
                )
                # Продолжаем удаление из БД даже если не удалось удалить из API
        
        # Удаляем подписку из БД
        deleted = await delete_subscription(subscription_id)
        if deleted:
            logger.info(f"✅ Подписка #{subscription_id} успешно удалена из базы данных")
            return True, "Подписка успешно удалена"
        else:
            return False, "Не удалось удалить подписку из базы данных"
            
    except Exception as e:
        logger.error(f"❌ Ошибка при полном удалении подписки #{subscription_id}: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False, f"Ошибка при удалении подписки: {str(e)}"


async def delete_all_user_subscriptions_completely(user_id: int) -> Tuple[int, int, list[str]]:
    """
    Полностью удалить все подписки пользователя: из базы данных и из 3x-ui API
    
    Args:
        user_id: ID пользователя
        
    Returns:
        Tuple[int, int, list[str]]: (количество успешно удаленных, количество ошибок, список ошибок)
    """
    try:
        # Получаем все подписки пользователя
        subscriptions = await get_user_subscriptions(user_id)
        
        if not subscriptions:
            return 0, 0, []
        
        success_count = 0
        error_count = 0
        errors = []
        
        # Удаляем каждую подписку
        for subscription in subscriptions:
            success, message = await delete_subscription_completely(subscription.id)
            if success:
                success_count += 1
            else:
                error_count += 1
                errors.append(f"Подписка #{subscription.id}: {message}")
        
        logger.info(
            f"✅ Удаление всех подписок пользователя #{user_id}: "
            f"успешно {success_count}, ошибок {error_count}"
        )
        
        return success_count, error_count, errors
        
    except Exception as e:
        logger.error(f"❌ Ошибка при удалении всех подписок пользователя #{user_id}: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return 0, len(subscriptions) if 'subscriptions' in locals() else 0, [str(e)]

