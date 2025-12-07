"""Модуль для отправки уведомлений пользователям об изменениях на серверах"""
import logging
from typing import List, Set
from utils.db import (
    get_users_with_active_subscriptions_by_location,
    get_user_subscriptions,
    get_server_by_id,
    get_location_by_id,
    get_subscription_identifier
)
from database.models import User, Subscription, Server

logger = logging.getLogger(__name__)


async def notify_users_about_server_changes(
    server_id: int,
    location_id: int,
    changed_fields: List[str]
):
    """
    Уведомить всех пользователей с активными подписками на сервера в локации 
    об изменениях на сервере
    
    Args:
        server_id: ID сервера, на котором произошли изменения
        location_id: ID локации сервера
        changed_fields: Список измененных полей (например, ['api_url', 'api_username'])
    """
    try:
        from core.loader import bot
        from utils.keyboards.main_kb import main_menu
        
        # Получаем информацию о сервере и локации
        server = await get_server_by_id(server_id)
        location = await get_location_by_id(location_id)
        
        if not server or not location:
            logger.error(f"❌ Сервер {server_id} или локация {location_id} не найдены для уведомлений")
            return
        
        # Получаем всех пользователей с активными подписками на сервера в этой локации
        users = await get_users_with_active_subscriptions_by_location(location_id)
        
        if not users:
            logger.info(f"ℹ️ Нет пользователей с активными подписками на локацию {location.name} для уведомлений")
            return
        
        # Формируем список измененных полей для сообщения
        field_names = {
            'api_url': 'API URL',
            'api_username': 'Имя пользователя API',
            'api_password': 'Пароль API',
            'location_id': 'Локация'
        }
        
        changed_fields_text = []
        for field in changed_fields:
            if field in field_names:
                changed_fields_text.append(field_names[field])
        
        changed_fields_str = ", ".join(changed_fields_text) if changed_fields_text else "параметры локации"
        
        # Отправляем уведомления каждому пользователю
        success_count = 0
        error_count = 0
        
        for user in users:
            try:
                # Получаем подписки пользователя на сервера в этой локации
                subscriptions = await get_user_subscriptions(user.id)
                # Получаем все активные подписки на сервера в этой локации
                location_subscriptions = []
                for sub in subscriptions:
                    if sub.status == "active":
                        sub_server = await get_server_by_id(sub.server_id)
                        if sub_server and sub_server.location_id == location_id:
                            location_subscriptions.append(sub)
                
                # Если у пользователя нет активных подписок на сервера в этой локации, пропускаем
                if not location_subscriptions:
                    continue
                
                # Проверяем, есть ли у пользователя подписка именно на измененный сервер
                has_subscription_on_changed_server = any(
                    sub.server_id == server_id for sub in location_subscriptions
                )
                
                # Формируем сообщение для пользователя
                text = "⚠️ <b>Важное уведомление</b>\n\n"
                text += f"На локации <b>{location.name}</b>, которую вы используете, были внесены изменения:\n"
                text += f"• {changed_fields_str}\n\n"
                text += "⚠️ <b>Внимание!</b> Ваш ключ доступа мог измениться.\n\n"
                text += "Рекомендуем:\n"
                text += "1. Проверить работоспособность подключения\n"
                text += "2. При необходимости обновить ключ в настройках\n"
                text += "3. Обратиться в поддержку, если возникнут проблемы\n\n"
                
                # Добавляем информацию о подписках в этой локации
                if location_subscriptions:
                    text += "📦 <b>Ваши подписки в этой локации:</b>\n"
                    for sub in location_subscriptions:
                        sub_id_display = get_subscription_identifier(sub, location.name)
                        status_emoji = "✅" if sub.status == "active" else "⏸️" if sub.status == "paused" else "❌"
                        text += f"{status_emoji} {sub_id_display}\n"
                
                # Отправляем сообщение
                await bot.send_message(
                    chat_id=int(user.tg_id),
                    text=text,
                    parse_mode="HTML"
                )
                
                success_count += 1
                
                # Небольшая задержка, чтобы не превышать лимиты Telegram API
                if success_count % 20 == 0:
                    import asyncio
                    await asyncio.sleep(1)
                    
            except Exception as e:
                error_count += 1
                logger.error(f"❌ Ошибка при отправке уведомления пользователю {user.tg_id}: {e}")
        
        logger.info(
            f"✅ Отправлено уведомлений об изменениях сервера {server.name}: "
            f"успешно {success_count}, ошибок {error_count}"
        )
        
    except Exception as e:
        logger.error(f"❌ Критическая ошибка при отправке уведомлений об изменениях сервера: {e}")
        import traceback
        logger.error(traceback.format_exc())

