"""
Сервис для управления подписками (создание, удаление и т.д.)
"""
import logging
import asyncio
from typing import Optional, Tuple
from utils.db import (
    get_subscription_by_id,
    delete_subscription,
    get_server_by_id,
    delete_all_user_subscriptions,
    get_user_subscriptions,
    get_subscriptions_by_location
)
from services.x3ui_api import get_x3ui_client

logger = logging.getLogger(__name__)


async def delete_subscription_completely(subscription_id: int) -> Tuple[bool, str]:
    """
    Полностью удалить подписку: из базы данных и из 3x-ui API
    Всегда пытается удалить из БД, даже если API недоступен.
    
    Args:
        subscription_id: ID подписки для удаления
        
    Returns:
        Tuple[bool, str]: (успешно ли удалено, сообщение об ошибке или успехе)
    """
    api_deleted = False
    api_error_msg = None
    
    try:
        # Получаем подписку из БД
        subscription = await get_subscription_by_id(subscription_id)
        if not subscription:
            # Подписка уже удалена из БД - это не ошибка
            logger.info(f"ℹ️ Подписка #{subscription_id} не найдена в базе данных (уже удалена)")
            return True, "Подписка уже удалена из базы данных"
        
        # Сохраняем данные для удаления из БД, даже если API недоступен
        sub_id = subscription.sub_id
        server_id = subscription.server_id
        
        # Пытаемся удалить из 3x-ui API (но не критично, если не получится)
        if sub_id and server_id:
            try:
                server = await get_server_by_id(server_id)
                if server:
                    x3ui_client = get_x3ui_client(
                        server.api_url,
                        server.api_username,
                        server.api_password,
                        server.ssl_certificate
                    )
                    
                    # Удаляем всех клиентов с этим subID на всех инбаундах
                    result = await x3ui_client.delete_all_clients_by_sub_id(sub_id)
                    await x3ui_client.close()
                    
                    if result and result.get("error"):
                        error_msg = result.get("message", "Неизвестная ошибка")
                        error_type = result.get("error_type", "unknown")
                        deleted_count = len(result.get("deleted", []))
                        api_error_msg = f"API: {error_msg}"
                        
                        # Для ошибок аутентификации выводим более информативное сообщение
                        if error_type == "authentication_failed":
                            logger.warning(
                                f"⚠️ Ошибка подключения к серверу 3x-ui при удалении клиентов с subID {sub_id}: "
                                f"{error_msg}. Сервер может быть недоступен. Продолжаем удаление из БД."
                            )
                        elif error_type == "not_found":
                            logger.info(
                                f"ℹ️ Клиенты с subID {sub_id} не найдены в 3x-ui API "
                                f"(возможно, уже удалены). Продолжаем удаление из БД."
                            )
                        else:
                            logger.warning(
                                f"⚠️ Не удалось удалить всех клиентов с subID {sub_id} "
                                f"из 3x-ui API: {error_msg}. Удалено {deleted_count}. Продолжаем удаление из БД."
                            )
                    else:
                        deleted_count = len(result.get("deleted", [])) if result else 0
                        api_deleted = True
                        logger.info(
                            f"✅ Удалено {deleted_count} клиентов с subID {sub_id} из 3x-ui API"
                        )
            except Exception as api_error:
                api_error_msg = f"API исключение: {str(api_error)}"
                logger.error(
                    f"❌ Ошибка при удалении клиентов из 3x-ui API: {api_error}. "
                    f"Продолжаем удаление из БД."
                )
        
        # ВСЕГДА пытаемся удалить из БД, даже если API недоступен
        deleted = await delete_subscription(subscription_id)
        if deleted:
            if api_deleted:
                logger.info(f"✅ Подписка #{subscription_id} успешно удалена из базы данных и API")
                return True, "Подписка успешно удалена"
            elif api_error_msg:
                logger.info(f"✅ Подписка #{subscription_id} удалена из базы данных (API недоступен: {api_error_msg})")
                return True, f"Подписка удалена из БД (API: {api_error_msg})"
            else:
                logger.info(f"✅ Подписка #{subscription_id} успешно удалена из базы данных")
                return True, "Подписка успешно удалена"
        else:
            # Это может произойти, если подписка уже была удалена между получением и удалением
            logger.warning(f"⚠️ Подписка #{subscription_id} не найдена в БД при попытке удаления (возможно, уже удалена)")
            return True, "Подписка уже удалена из базы данных"
            
    except Exception as e:
        logger.error(f"❌ Критическая ошибка при удалении подписки #{subscription_id}: {e}")
        import traceback
        logger.error(traceback.format_exc())
        
        # Даже при критической ошибке пытаемся удалить из БД
        try:
            deleted = await delete_subscription(subscription_id)
            if deleted:
                logger.info(f"✅ Подписка #{subscription_id} удалена из БД после ошибки")
                return True, f"Подписка удалена из БД (была ошибка: {str(e)})"
        except:
            pass
        
        return False, f"Ошибка при удалении подписки: {str(e)}"


async def delete_all_user_subscriptions_completely(user_id: int) -> Tuple[int, int, list[str]]:
    """
    Полностью удалить все подписки пользователя: из базы данных и из 3x-ui API
    Оптимизировано: группировка по серверам и параллельное удаление
    
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
        
        # Группируем подписки по серверам для оптимизации
        subscriptions_by_server = {}
        subscriptions_without_server = []
        
        for subscription in subscriptions:
            if subscription.server_id and subscription.sub_id:
                if subscription.server_id not in subscriptions_by_server:
                    subscriptions_by_server[subscription.server_id] = []
                subscriptions_by_server[subscription.server_id].append(subscription)
            else:
                subscriptions_without_server.append(subscription)
        
        success_count = 0
        error_count = 0
        errors = []
        
        # Удаляем подписки параллельно по серверам
        async def delete_subscriptions_batch(subscriptions_batch: list):
            """Удаляет батч подписок параллельно"""
            tasks = [delete_subscription_completely(sub.id) for sub in subscriptions_batch]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            batch_success = 0
            batch_errors = []
            
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    error_count += 1
                    batch_errors.append(f"Подписка #{subscriptions_batch[i].id}: {str(result)}")
                else:
                    success, message = result
                    if success:
                        batch_success += 1
                    else:
                        error_count += 1
                        batch_errors.append(f"Подписка #{subscriptions_batch[i].id}: {message}")
            
            return batch_success, batch_errors
        
        # Удаляем подписки по серверам параллельно
        server_tasks = []
        for server_id, server_subscriptions in subscriptions_by_server.items():
            server_tasks.append(delete_subscriptions_batch(server_subscriptions))
        
        # Также обрабатываем подписки без сервера
        if subscriptions_without_server:
            server_tasks.append(delete_subscriptions_batch(subscriptions_without_server))
        
        # Выполняем все задачи параллельно
        if server_tasks:
            batch_results = await asyncio.gather(*server_tasks, return_exceptions=True)
            for result in batch_results:
                if isinstance(result, Exception):
                    error_count += 1
                    errors.append(f"Ошибка батча: {str(result)}")
                else:
                    batch_success, batch_errors = result
                    success_count += batch_success
                    errors.extend(batch_errors)
        
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


async def delete_all_location_subscriptions_completely(location_id: int) -> Tuple[int, int, list[str]]:
    """
    Полностью удалить все подписки для локации: из базы данных и из 3x-ui API
    Всегда удаляет из БД, даже если API недоступен.
    Оптимизировано: группировка по серверам и параллельное удаление
    
    Args:
        location_id: ID локации
        
    Returns:
        Tuple[int, int, list[str]]: (количество успешно удаленных из БД, количество ошибок API, список ошибок API)
    """
    try:
        # Получаем все подписки для локации
        subscriptions = await get_subscriptions_by_location(location_id)
        
        if not subscriptions:
            logger.info(f"ℹ️ На локации #{location_id} нет подписок для удаления")
            return 0, 0, []
        
        logger.info(f"🔄 Начинаем удаление {len(subscriptions)} подписок для локации #{location_id}")
        
        # Группируем подписки по серверам для оптимизации
        subscriptions_by_server = {}
        subscriptions_without_server = []
        
        for subscription in subscriptions:
            if subscription.server_id and subscription.sub_id:
                if subscription.server_id not in subscriptions_by_server:
                    subscriptions_by_server[subscription.server_id] = []
                subscriptions_by_server[subscription.server_id].append(subscription)
            else:
                subscriptions_without_server.append(subscription)
        
        success_count = 0
        api_error_count = 0
        api_errors = []
        
        # Удаляем подписки параллельно по серверам
        async def delete_subscriptions_batch(subscriptions_batch: list):
            """Удаляет батч подписок параллельно"""
            tasks = [delete_subscription_completely(sub.id) for sub in subscriptions_batch]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            batch_success = 0
            batch_api_errors = []
            
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    api_error_count += 1
                    batch_api_errors.append(f"Подписка #{subscriptions_batch[i].id}: {str(result)}")
                else:
                    success, message = result
                    if success:
                        batch_success += 1
                        # Если в сообщении есть упоминание об ошибке API, считаем это как ошибку API (но не критичную)
                        if "API" in message and ("недоступен" in message.lower() or "ошибка" in message.lower() or "исключение" in message.lower()):
                            api_error_count += 1
                            batch_api_errors.append(f"Подписка #{subscriptions_batch[i].id}: {message}")
                    else:
                        # Это критическая ошибка - не удалось удалить из БД
                        api_error_count += 1
                        batch_api_errors.append(f"Подписка #{subscriptions_batch[i].id}: {message}")
                        logger.error(f"❌ Не удалось удалить подписку #{subscriptions_batch[i].id} из БД: {message}")
            
            return batch_success, batch_api_errors
        
        # Удаляем подписки по серверам параллельно
        server_tasks = []
        for server_id, server_subscriptions in subscriptions_by_server.items():
            server_tasks.append(delete_subscriptions_batch(server_subscriptions))
        
        # Также обрабатываем подписки без сервера
        if subscriptions_without_server:
            server_tasks.append(delete_subscriptions_batch(subscriptions_without_server))
        
        # Выполняем все задачи параллельно
        if server_tasks:
            batch_results = await asyncio.gather(*server_tasks, return_exceptions=True)
            for result in batch_results:
                if isinstance(result, Exception):
                    api_error_count += 1
                    api_errors.append(f"Ошибка батча: {str(result)}")
                else:
                    batch_success, batch_api_errors = result
                    success_count += batch_success
                    api_errors.extend(batch_api_errors)
        
        logger.info(
            f"✅ Удаление всех подписок локации #{location_id} завершено: "
            f"удалено из БД {success_count}/{len(subscriptions)}, ошибок API {api_error_count}"
        )
        
        return success_count, api_error_count, api_errors
        
    except Exception as e:
        logger.error(f"❌ Критическая ошибка при удалении всех подписок локации #{location_id}: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return 0, len(subscriptions) if 'subscriptions' in locals() else 0, [f"Критическая ошибка: {str(e)}"]

