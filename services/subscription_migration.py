"""
Сервис для переноса подписок с одного сервера на другой
"""
import logging
from typing import List, Tuple, Dict, Any, Optional
from datetime import datetime, timedelta
from utils.db import (
    get_subscriptions_by_server,
    get_server_by_id,
    get_user_by_id,
    update_subscription,
    get_location_by_id,
    update_server_current_users,
    generate_location_unique_name
)
from services.x3ui_api import get_x3ui_client

logger = logging.getLogger(__name__)


async def migrate_subscriptions_from_server(
    source_server_id: int,
    target_server_id: int
) -> Tuple[int, int, List[str]]:
    """
    Переносит все подписки с исходного сервера на целевой сервер.
    
    Для каждой подписки:
    1. Получает данные клиентов через API исходного сервера
    2. Создает клиентов на новом сервере с теми же параметрами (sub_id, expire_date, etc.)
    3. Обновляет подписку в БД, изменив server_id на новый
    
    Args:
        source_server_id: ID исходного сервера
        target_server_id: ID целевого сервера
        
    Returns:
        Tuple[int, int, List[str]]: (успешно перенесено, ошибок, список ошибок)
    """
    # Получаем серверы
    source_server = await get_server_by_id(source_server_id)
    target_server = await get_server_by_id(target_server_id)
    
    if not source_server:
        return 0, 0, [f"Исходный сервер #{source_server_id} не найден"]
    
    if not target_server:
        return 0, 0, [f"Целевой сервер #{target_server_id} не найден"]
    
    # Получаем все подписки на исходном сервере
    subscriptions = await get_subscriptions_by_server(source_server_id)
    
    if not subscriptions:
        logger.info(f"ℹ️ На исходном сервере #{source_server_id} нет подписок для переноса")
        return 0, 0, []
    
    logger.info(f"🔄 Начинаем перенос {len(subscriptions)} подписок с сервера #{source_server_id} на сервер #{target_server_id}")
    
    success_count = 0
    error_count = 0
    errors = []
    
    # Создаем клиенты API для исходного и целевого серверов
    source_x3ui_client = get_x3ui_client(
        source_server.api_url,
        source_server.api_username,
        source_server.api_password,
        source_server.ssl_certificate
    )
    
    target_x3ui_client = get_x3ui_client(
        target_server.api_url,
        target_server.api_username,
        target_server.api_password,
        target_server.ssl_certificate
    )
    
    try:
        # Аутентифицируемся на обоих серверах
        source_login = await source_x3ui_client.login()
        if not source_login:
            error_msg = f"Не удалось подключиться к исходному серверу #{source_server_id}"
            logger.error(f"❌ {error_msg}")
            return 0, len(subscriptions), [error_msg] * len(subscriptions)
        
        target_login = await target_x3ui_client.login()
        if not target_login:
            error_msg = f"Не удалось подключиться к целевому серверу #{target_server_id}"
            logger.error(f"❌ {error_msg}")
            return 0, len(subscriptions), [error_msg] * len(subscriptions)
        
        # Переносим каждую подписку
        for subscription in subscriptions:
            try:
                # Пропускаем подписки без sub_id
                if not subscription.sub_id:
                    error_msg = f"Подписка #{subscription.id}: отсутствует sub_id"
                    logger.warning(f"⚠️ {error_msg}")
                    errors.append(error_msg)
                    error_count += 1
                    continue
                
                # Получаем данные клиентов с исходного сервера
                source_clients = await source_x3ui_client.get_subscription_by_sub_id(subscription.sub_id)
                
                if not source_clients:
                    error_msg = f"Подписка #{subscription.id}: клиенты с sub_id {subscription.sub_id} не найдены на исходном сервере"
                    logger.warning(f"⚠️ {error_msg}")
                    errors.append(error_msg)
                    error_count += 1
                    continue
                
                # Получаем пользователя для создания подписки
                user = await get_user_by_id(subscription.user_id)
                if not user:
                    error_msg = f"Подписка #{subscription.id}: пользователь #{subscription.user_id} не найден"
                    logger.error(f"❌ {error_msg}")
                    errors.append(error_msg)
                    error_count += 1
                    continue
                
                # Получаем локацию целевого сервера
                target_location = await get_location_by_id(target_server.location_id)
                if not target_location:
                    error_msg = f"Подписка #{subscription.id}: локация целевого сервера не найдена"
                    logger.error(f"❌ {error_msg}")
                    errors.append(error_msg)
                    error_count += 1
                    continue
                
                # Определяем параметры для создания клиентов на новом сервере
                # Получаем username из пользователя
                username = user.username or f"user_{user.tg_id}"
                
                # Получаем unique_code из location_unique_name подписки, если есть
                if subscription.location_unique_name:
                    # Извлекаем unique_code из location_unique_name (формат: location_slug-unique_code)
                    unique_code = subscription.location_unique_name.split('-')[-1] if '-' in subscription.location_unique_name else subscription.location_unique_name
                else:
                    # Fallback: используем последние 6 символов sub_id
                    unique_code = subscription.sub_id[-6:] if len(subscription.sub_id) >= 6 else subscription.sub_id
                
                # Генерируем location_unique_name для новой локации
                new_location_unique_name = generate_location_unique_name(target_location.name, seed=subscription.sub_id)
                
                # Нормализуем название локации для email (как при создании подписки)
                import re
                import unicodedata
                translit_map = {
                    'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e', 'ё': 'yo',
                    'ж': 'zh', 'з': 'z', 'и': 'i', 'й': 'y', 'к': 'k', 'л': 'l', 'м': 'm',
                    'н': 'n', 'о': 'o', 'п': 'p', 'р': 'r', 'с': 's', 'т': 't', 'у': 'u',
                    'ф': 'f', 'х': 'h', 'ц': 'ts', 'ч': 'ch', 'ш': 'sh', 'щ': 'sch',
                    'ъ': '', 'ы': 'y', 'ь': '', 'э': 'e', 'ю': 'yu', 'я': 'ya'
                }
                normalized = unicodedata.normalize('NFKD', target_location.name)
                location_slug = ''.join(translit_map.get(char.lower(), char.lower()) for char in normalized)
                location_slug = re.sub(r'[^a-z0-9]', '', location_slug)
                
                # Вычисляем дни для API из expire_date
                api_days = 0  # По умолчанию без ограничения
                if subscription.expire_date and not subscription.is_private:
                    now = datetime.utcnow()
                    delta = subscription.expire_date - now
                    if delta.total_seconds() > 0:
                        api_days = max(1, delta.days)  # Минимум 1 день
                    else:
                        api_days = 0  # Истекшая подписка
                
                # Создаем клиентов на целевом сервере с тем же sub_id
                create_result = await target_x3ui_client.add_client_to_all_inbounds(
                    location_name=location_slug,
                    username=username,
                    unique_code=unique_code,
                    days=api_days,
                    tg_id=str(user.tg_id),
                    limit_ip=3,
                    sub_id=subscription.sub_id  # Используем тот же sub_id
                )
                
                # Проверяем результат создания
                if not create_result or (isinstance(create_result, dict) and create_result.get("error") and len(create_result.get("created", [])) == 0):
                    error_msg = f"Подписка #{subscription.id}: не удалось создать клиентов на целевом сервере"
                    if isinstance(create_result, dict):
                        error_msg += f" - {create_result.get('message', 'Неизвестная ошибка')}"
                    logger.error(f"❌ {error_msg}")
                    errors.append(error_msg)
                    error_count += 1
                    continue
                
                created_clients = create_result.get("created", [])
                if not created_clients:
                    error_msg = f"Подписка #{subscription.id}: клиенты не были созданы на целевом сервере"
                    logger.error(f"❌ {error_msg}")
                    errors.append(error_msg)
                    error_count += 1
                    continue
                
                # Получаем email первого созданного клиента
                vless_client = next((c for c in created_clients if c.get("protocol") == "vless"), None)
                if vless_client:
                    new_client_email = vless_client.get("email")
                else:
                    new_client_email = created_clients[0].get("email")
                
                # Получаем ключи подписки с нового сервера
                import json
                client_keys_list = await target_x3ui_client.get_client_keys_from_subscription(subscription.sub_id)
                
                # Преобразуем список ключей в JSON строку
                if client_keys_list:
                    x3ui_subscription_link = json.dumps(client_keys_list, ensure_ascii=False)
                else:
                    # Пробуем получить ключ напрямую
                    vless_link = await target_x3ui_client.get_client_vless_link(
                        client_email=new_client_email,
                        client_username=new_client_email,
                    )
                    if vless_link:
                        x3ui_subscription_link = json.dumps([{"vless_link": vless_link, "client_email": new_client_email}], ensure_ascii=False)
                    else:
                        x3ui_subscription_link = None
                
                # Обновляем подписку в БД: меняем server_id и обновляем данные клиента
                updated_subscription = await update_subscription(
                    subscription.id,
                    server_id=target_server_id,
                    x3ui_client_id=x3ui_subscription_link,
                    x3ui_client_email=new_client_email,
                    location_unique_name=new_location_unique_name  # Обновляем location_unique_name для новой локации
                )
                
                if updated_subscription:
                    logger.info(f"✅ Подписка #{subscription.id} успешно перенесена на сервер #{target_server_id}")
                    success_count += 1
                else:
                    error_msg = f"Подписка #{subscription.id}: не удалось обновить подписку в БД"
                    logger.error(f"❌ {error_msg}")
                    errors.append(error_msg)
                    error_count += 1
                    
                    # Пытаемся откатить - удалить созданных клиентов
                    try:
                        await target_x3ui_client.delete_all_clients_by_sub_id(subscription.sub_id)
                    except:
                        pass
                
            except Exception as e:
                error_msg = f"Подписка #{subscription.id}: ошибка при переносе - {str(e)}"
                logger.error(f"❌ {error_msg}")
                import traceback
                logger.error(traceback.format_exc())
                errors.append(error_msg)
                error_count += 1
        
    finally:
        # Закрываем соединения
        try:
            await source_x3ui_client.close()
        except:
            pass
        try:
            await target_x3ui_client.close()
        except:
            pass
    
    # Обновляем счетчики пользователей на обоих серверах
    try:
        await update_server_current_users(source_server_id)
        await update_server_current_users(target_server_id)
    except Exception as e:
        logger.error(f"⚠️ Ошибка при обновлении счетчиков пользователей: {e}")
    
    logger.info(f"✅ Перенос подписок завершен: успешно {success_count}, ошибок {error_count}")
    return success_count, error_count, errors

