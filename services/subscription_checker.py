"""
Сервис для проверки и управления подписками через 3x-ui API
"""
from services.scheduler import scheduler, add_job
from utils.db import (
    get_all_active_subscriptions,
    get_all_expired_subscriptions,
    get_server_by_id,
    update_subscription,
    get_user_by_id,
    get_subscription_identifier,
    utc_to_user_timezone,
    get_subscriptions_older_than
)
from services.x3ui_api import get_x3ui_client
from services.subscription import delete_subscription_completely
from core.config import config
from datetime import datetime, timedelta
import logging
import asyncio
from aiogram.exceptions import TelegramNetworkError
from aiohttp.client_exceptions import ClientConnectorError

logger = logging.getLogger(__name__)


async def send_message_with_retry(bot, chat_id, text, reply_markup=None, parse_mode="HTML", max_retries=3, retry_delay=2):
    """
    Отправляет сообщение с повторными попытками при сетевых ошибках
    
    Args:
        bot: Экземпляр бота
        chat_id: ID чата
        text: Текст сообщения
        reply_markup: Клавиатура (опционально)
        parse_mode: Режим парсинга (по умолчанию HTML)
        max_retries: Максимальное количество попыток
        retry_delay: Начальная задержка между попытками (секунды)
    
    Returns:
        bool: True если сообщение отправлено успешно, False если не удалось после всех попыток
    """
    for attempt in range(max_retries):
        try:
            await bot.send_message(
                chat_id=int(chat_id),
                text=text,
                reply_markup=reply_markup,
                parse_mode=parse_mode
            )
            return True
        except (TelegramNetworkError, ClientConnectorError, ConnectionError, TimeoutError, asyncio.TimeoutError) as network_error:
            if attempt < max_retries - 1:
                logger.warning(
                    f"⚠️ Сетевая ошибка при отправке сообщения (попытка {attempt + 1}/{max_retries}): "
                    f"{type(network_error).__name__}: {network_error}. Повтор через {retry_delay} сек..."
                )
                await asyncio.sleep(retry_delay)
                retry_delay *= 2  # Экспоненциальная задержка
            else:
                logger.error(
                    f"❌ Не удалось отправить сообщение после {max_retries} попыток: "
                    f"{type(network_error).__name__}: {network_error}"
                )
                return False
        except Exception as e:
            # Для других ошибок не делаем retry
            logger.error(f"❌ Ошибка при отправке сообщения: {type(e).__name__}: {e}")
            return False
    return False


async def send_subscription_expired_notification(subscription):
    """Отправить уведомление пользователю об истечении подписки"""
    try:
        from core.loader import bot
        from utils.keyboards.main_kb import main_menu
        from aiogram.utils.keyboard import InlineKeyboardBuilder
        
        # Получаем пользователя
        user = await get_user_by_id(subscription.user_id)
        if not user:
            logger.warning(f"⚠️ Пользователь {subscription.user_id} не найден для подписки {subscription.id}")
            return
        
        # Получаем информацию о сервере и локации
        server = await get_server_by_id(subscription.server_id)
        location_name = "Неизвестно"
        if server and server.location:
            location_name = server.location.name
        
        # Генерируем идентификатор подписки
        subscription_id = get_subscription_identifier(subscription, location_name)
        
        # Формируем сообщение
        text = f"⏰ <b>Подписка истекла</b>\n\n"
        text += f"📦 <b>Локация:</b> {location_name or 'Неизвестно'} ({subscription_id or subscription.id})\n"
        text += f"📅 Подписка закончилась. Для продолжения использования необходимо продлить подписку.\n\n"
        text += "Нажмите кнопку ниже, чтобы продлить подписку:"
        
        # Проверяем, что текст не пустой
        if not text or not text.strip():
            logger.error(f"❌ Пустой текст уведомления об истечении для подписки {subscription.id}")
            text = f"⏰ <b>Подписка истекла</b>\n\n📦 <b>Локация:</b> {location_name or 'Неизвестно'}\n📅 Подписка закончилась. Для продолжения использования необходимо продлить подписку.\n\nНажмите кнопку ниже, чтобы продлить подписку:"
        
        # Создаем клавиатуру с кнопкой продления
        kb = InlineKeyboardBuilder()
        kb.button(text="🔄 Продлить", callback_data=f"renew_subscription_{subscription.id}")
        kb.adjust(1)
        
        # Отправляем сообщение с retry логикой
        success = await send_message_with_retry(
            bot=bot,
            chat_id=user.tg_id,
            text=text,
            reply_markup=kb.as_markup()
        )
        
        if success:
            # Отправляем сообщение с кнопками главного меню, чтобы они всегда были доступны
            from utils.keyboards.main_kb import main_menu
            await send_message_with_retry(
                bot=bot,
                chat_id=user.tg_id,
                text="📱 <b>Главное меню</b>",
                reply_markup=main_menu()
            )
            if config.TEST_MODE:
                logger.info(f"Expired notification sent to user {user.tg_id} (subscription {subscription.id})")
        else:
            logger.warning(f"Failed to send expired notification for subscription {subscription.id} to user {user.tg_id}")
    except Exception as e:
        logger.error(f"Error sending expired notification for subscription {subscription.id}: {e}")
        import traceback
        logger.error(traceback.format_exc())


async def send_subscription_deletion_warning_notification(subscription, time_until_deletion: timedelta, warning_number: int):
    """Отправить уведомление пользователю о предстоящем удалении подписки"""
    try:
        from core.loader import bot
        from utils.keyboards.main_kb import main_menu
        from aiogram.utils.keyboard import InlineKeyboardBuilder
        
        # Получаем пользователя
        user = await get_user_by_id(subscription.user_id)
        if not user:
            logger.warning(f"⚠️ Пользователь {subscription.user_id} не найден для подписки {subscription.id}")
            return
        
        # Получаем информацию о сервере и локации
        server = await get_server_by_id(subscription.server_id)
        location_name = "Неизвестно"
        if server and server.location:
            location_name = server.location.name
        
        # Генерируем идентификатор подписки
        subscription_id = get_subscription_identifier(subscription, location_name)
        
        # Формируем текст времени до удаления
        if config.TEST_MODE:
            # В тестовом режиме показываем минуты/секунды
            total_seconds = int(time_until_deletion.total_seconds())
            minutes_left = total_seconds // 60
            seconds_left = total_seconds % 60
            if minutes_left > 0:
                time_text = f"{minutes_left} мин. {seconds_left} сек."
            else:
                time_text = f"{seconds_left} сек."
        else:
            # В обычном режиме показываем дни/часы
            days_left = time_until_deletion.days
            hours_left = int((time_until_deletion.total_seconds() % 86400) // 3600)
            if days_left > 0:
                time_text = f"{days_left} дн. {hours_left} ч."
            elif hours_left > 0:
                time_text = f"{hours_left} ч."
            else:
                time_text = "менее часа"
        
        # Формируем сообщение
        text = f"⚠️ <b>Предупреждение о предстоящем удалении подписки</b>\n\n"
        text += f"📦 <b>Локация:</b> {location_name or 'Неизвестно'} ({subscription_id or subscription.id})\n"
        text += f"🗑️ <b>Подписка будет удалена через:</b> {time_text}\n\n"
        text += f"⚠️ Если вы не продлите подписку, она будет удалена.\n\n"
        text += "Нажмите кнопку ниже, чтобы продлить подписку:"
        
        # Проверяем, что текст не пустой
        if not text or not text.strip():
            logger.error(f"❌ Пустой текст предупреждения об удалении для подписки {subscription.id}")
            text = f"⚠️ <b>Предупреждение о предстоящем удалении подписки</b>\n\n📦 <b>Локация:</b> {location_name or 'Неизвестно'}\n🗑️ <b>Подписка будет удалена через:</b> {time_text}\n\n⚠️ Если вы не продлите подписку, она будет удалена.\n\nНажмите кнопку ниже, чтобы продлить подписку:"
        
        # Создаем клавиатуру с кнопкой продления
        kb = InlineKeyboardBuilder()
        kb.button(text="🔄 Продлить", callback_data=f"renew_subscription_{subscription.id}")
        kb.adjust(1)
        
        # Отправляем сообщение с retry логикой
        success = await send_message_with_retry(
            bot=bot,
            chat_id=user.tg_id,
            text=text,
            reply_markup=kb.as_markup()
        )
        
        if success:
            # Отправляем сообщение с кнопками главного меню
            await send_message_with_retry(
                bot=bot,
                chat_id=user.tg_id,
                text="📱 <b>Главное меню</b>",
                reply_markup=main_menu()
            )
            if config.TEST_MODE:
                logger.info(f"Deletion warning #{warning_number} sent to user {user.tg_id} (subscription {subscription.id})")
        else:
            logger.warning(f"Failed to send deletion warning #{warning_number} for subscription {subscription.id} to user {user.tg_id}")
    except Exception as e:
        logger.error(f"Error sending deletion warning for subscription {subscription.id}: {e}")
        import traceback
        logger.error(traceback.format_exc())


async def send_subscription_deleted_notification(subscription):
    """Отправить уведомление пользователю об удалении подписки"""
    try:
        from core.loader import bot
        from utils.keyboards.main_kb import main_menu
        
        # Получаем пользователя
        user = await get_user_by_id(subscription.user_id)
        if not user:
            logger.warning(f"⚠️ Пользователь {subscription.user_id} не найден для подписки {subscription.id}")
            return
        
        # Получаем информацию о сервере и локации
        server = await get_server_by_id(subscription.server_id)
        location_name = "Неизвестно"
        if server and server.location:
            location_name = server.location.name
        
        # Генерируем идентификатор подписки
        subscription_id = get_subscription_identifier(subscription, location_name)
        
        # Формируем сообщение
        text = f"🗑️ <b>Подписка удалена</b>\n\n"
        text += f"📦 <b>Локация:</b> {location_name or 'Неизвестно'} ({subscription_id or subscription.id})\n"
        text += f"⚠️ Ваша подписка была удалена, так как она не была продлена в течение установленного времени.\n\n"
        text += "Вы можете приобрести новую подписку, нажав кнопку ниже:"
        
        # Проверяем, что текст не пустой
        if not text or not text.strip():
            logger.error(f"❌ Пустой текст уведомления об удалении для подписки {subscription.id}")
            text = f"🗑️ <b>Подписка удалена</b>\n\n📦 <b>Локация:</b> {location_name or 'Неизвестно'}\n⚠️ Ваша подписка была удалена, так как она не была продлена в течение установленного времени.\n\nВы можете приобрести новую подписку, нажав кнопку ниже:"
        
        # Создаем клавиатуру с кнопкой покупки
        from aiogram.utils.keyboard import InlineKeyboardBuilder
        kb = InlineKeyboardBuilder()
        kb.button(text="🛒 Приобрести подписку", callback_data="profile_purchase")
        kb.adjust(1)
        
        # Отправляем сообщение с retry логикой
        success = await send_message_with_retry(
            bot=bot,
            chat_id=user.tg_id,
            text=text,
            reply_markup=kb.as_markup()
        )
        
        if success:
            # Отправляем сообщение с кнопками главного меню
            await send_message_with_retry(
                bot=bot,
                chat_id=user.tg_id,
                text="📱 <b>Главное меню</b>",
                reply_markup=main_menu()
            )
            if config.TEST_MODE:
                logger.info(f"Deleted notification sent to user {user.tg_id} (subscription {subscription.id})")
        else:
            logger.warning(f"Failed to send deleted notification for subscription {subscription.id} to user {user.tg_id}")
    except Exception as e:
        logger.error(f"Error sending deleted notification for subscription {subscription.id}: {e}")
        import traceback
        logger.error(traceback.format_exc())


async def send_subscription_expiring_soon_notification(subscription, days_left: int):
    """Отправить уведомление пользователю о скором окончании подписки"""
    try:
        from core.loader import bot
        from utils.keyboards.main_kb import main_menu
        from aiogram.utils.keyboard import InlineKeyboardBuilder
        
        # Получаем пользователя
        user = await get_user_by_id(subscription.user_id)
        if not user:
            logger.warning(f"⚠️ Пользователь {subscription.user_id} не найден для подписки {subscription.id}")
            return
        
        # Получаем информацию о сервере и локации
        server = await get_server_by_id(subscription.server_id)
        location_name = "Неизвестно"
        if server and server.location:
            location_name = server.location.name
        
        # Генерируем идентификатор подписки
        subscription_id = get_subscription_identifier(subscription, location_name)
        
        # Формируем сообщение
        # В тестовом режиме days_left может быть в секундах
        if config.TEST_MODE and days_left < 60:
            time_text = f"{days_left} секунд"
        elif config.TEST_MODE and days_left < 3600:
            minutes = days_left // 60
            time_text = f"{minutes} минут"
        else:
            days_text = "день" if days_left == 1 else ("дня" if days_left in [2, 3, 4] else "дней")
            time_text = f"{days_left} {days_text}"
        
        text = f"⏰ <b>Подписка скоро закончится</b>\n\n"
        text += f"📦 <b>Локация:</b> {location_name} ({subscription_id})\n"
        text += f"📅 До окончания подписки осталось <b>{time_text}</b>\n\n"
        
        if subscription.expire_date:
            # Преобразуем время в часовой пояс пользователя
            expire_time = utc_to_user_timezone(
                subscription.expire_date,
                user=user,
                language_code=user.language_code if hasattr(user, 'language_code') and user.language_code else None
            )
            expire_time_str = expire_time.strftime("%d.%m.%Y в %H:%M")
            text += f"⏳ Подписка закончится: <b>{expire_time_str}</b>\n\n"
        
        text += "Не забудьте продлить подписку, чтобы продолжить использование!"
        
        # Проверяем, что текст не пустой
        if not text or not text.strip():
            logger.error(f"❌ Пустой текст уведомления для подписки {subscription.id}")
            text = f"⏰ <b>Подписка скоро закончится</b>\n\n📦 <b>Локация:</b> {location_name}\n📅 До окончания подписки осталось <b>{time_text}</b>\n\nНе забудьте продлить подписку!"
        
        # Создаем клавиатуру с кнопкой продления
        kb = InlineKeyboardBuilder()
        kb.button(text="🔄 Продлить", callback_data=f"renew_subscription_{subscription.id}")
        kb.adjust(1)
        
        # Отправляем сообщение с retry логикой
        success = await send_message_with_retry(
            bot=bot,
            chat_id=user.tg_id,
            text=text,
            reply_markup=kb.as_markup()
        )
        
        if success:
            if config.TEST_MODE:
                logger.info(f"Expiring soon notification ({days_left} days) sent to user {user.tg_id} (subscription {subscription.id})")
        else:
            logger.warning(f"Failed to send expiring soon notification for subscription {subscription.id} to user {user.tg_id}")
    except Exception as e:
        logger.error(f"Error sending expiring soon notification for subscription {subscription.id}: {e}")
        import traceback
        logger.error(traceback.format_exc())


async def check_subscriptions_job():
    """
    Периодическая задача для проверки и управления подписками:
    - Отключает клиентов на сервере, если подписка истекла
    - Включает клиентов на сервере, если подписка активна
    - Отправляет уведомления о скором окончании подписки (за 3 дня и за 1 день)
    
    Оптимизировано: группировка подписок по серверам для батчинга API вызовов
    """
    try:
        current_time = datetime.utcnow()
        
        # Определяем интервалы для уведомлений в зависимости от режима
        if config.TEST_MODE:
            # В тестовом режиме: уведомления за 30 секунд и за 10 секунд до окончания
            notification_3_days_interval = timedelta(seconds=30)
            notification_1_day_interval = timedelta(seconds=10)
        else:
            # В обычном режиме: уведомления за 3 дня и за 1 день до окончания
            notification_3_days_interval = timedelta(days=3)
            notification_1_day_interval = timedelta(days=1)
        
        # Получаем все активные подписки с загруженными серверами (оптимизация N+1)
        try:
            active_subscriptions = await get_all_active_subscriptions()
        except Exception as db_error:
            logger.error(f"Failed to get active subscriptions: {db_error}")
            return
        
        if config.TEST_MODE:
            logger.info(f"Checking {len(active_subscriptions)} active subscriptions...")
        
        # Группируем подписки по серверам для батчинга API вызовов
        subscriptions_by_server = {}
        subscriptions_to_disable = []  # Подписки для отключения
        subscriptions_to_enable = []  # Подписки для включения
        subscriptions_to_notify = []  # Подписки для уведомлений
        
        enabled_count = 0
        disabled_count = 0
        error_count = 0
        notifications_sent = 0
        
        # Предварительная обработка: группируем подписки по серверам для оптимизации
        server_clients = {}  # Кэш клиентов API по server_id
        
        for subscription in active_subscriptions:
            try:
                # Пропускаем приватные подписки - они бессрочные и не проверяются
                if subscription.is_private:
                    continue
                
                # Если подписка истекла - отключаем клиента на сервере
                if subscription.expire_date and subscription.expire_date < current_time and subscription.status == "active":
                    subscriptions_to_disable.append(subscription)
                else:
                    # Подписка активна - проверяем уведомления о скором окончании
                    if subscription.expire_date and subscription.expire_date > current_time:
                        time_until_expiry = subscription.expire_date - current_time
                        
                        # Уведомление за 3 дня
                        if (time_until_expiry <= notification_3_days_interval and 
                            time_until_expiry > notification_1_day_interval and
                            not subscription.notification_3_days_sent):
                            subscriptions_to_notify.append((subscription, 3))
                        
                        # Уведомление за 1 день
                        elif (time_until_expiry <= notification_1_day_interval and
                              not subscription.notification_1_day_sent):
                            subscriptions_to_notify.append((subscription, 1))
                    
                    # Добавляем в список для включения
                    if subscription.x3ui_client_email and subscription.server_id:
                        subscriptions_to_enable.append(subscription)
            except Exception as e:
                error_count += 1
                logger.error(f"Error preprocessing subscription {subscription.id}: {e}")
        
        # Обрабатываем истекшие подписки (батчинг по серверам)
        for subscription in subscriptions_to_disable:
            try:
                if subscription.sub_id and subscription.server_id:
                    # Получаем или создаем клиент API для сервера
                    if subscription.server_id not in server_clients:
                        server = await get_server_by_id(subscription.server_id)
                        if server:
                            server_clients[subscription.server_id] = get_x3ui_client(
                                server.api_url,
                                server.api_username,
                                server.api_password,
                                server.ssl_certificate
                            )
                    
                    if subscription.server_id in server_clients:
                        x3ui_client = server_clients[subscription.server_id]
                        # Отключаем всех клиентов с этим subID на всех инбаундах
                        result = await x3ui_client.disable_all_clients_by_sub_id(subscription.sub_id)
                        
                        if result and not result.get("error"):
                            disabled_count += 1
                            disabled_clients = result.get("disabled", [])
                            if config.TEST_MODE:
                                logger.info(f"Disabled {len(disabled_clients)} clients with subID {subscription.sub_id} (subscription expired)")
                        else:
                            error_count += 1
                            error_msg = result.get("message", "Unknown error") if result else "Disable error"
                            logger.warning(f"Failed to disable clients with subID {subscription.sub_id}: {error_msg}")
                
                # Обновляем статус подписки в БД
                try:
                    await update_subscription(subscription_id=subscription.id, status="expired")
                    disabled_count += 1
                except Exception as db_error:
                    error_count += 1
                    logger.error(f"Failed to update subscription {subscription.id} status: {db_error}")
                    continue
                
                # Отправляем уведомление
                try:
                    await send_subscription_expired_notification(subscription)
                except Exception as notify_error:
                    logger.warning(f"Failed to send expired notification for subscription {subscription.id}: {notify_error}")
                
                if config.TEST_MODE:
                    logger.info(f"Subscription {subscription.id} marked as expired")
            except Exception as e:
                error_count += 1
                logger.error(f"Error processing expired subscription {subscription.id}: {e}")
        
        # Обрабатываем уведомления
        for subscription, days in subscriptions_to_notify:
            try:
                time_until_expiry = subscription.expire_date - current_time
                days_left = days if not config.TEST_MODE else int(time_until_expiry.total_seconds())
                await send_subscription_expiring_soon_notification(subscription, days_left)
                
                # Обновляем флаги уведомлений
                update_data = {}
                if days == 3:
                    update_data['notification_3_days_sent'] = True
                elif days == 1:
                    update_data['notification_1_day_sent'] = True
                
                try:
                    await update_subscription(subscription_id=subscription.id, **update_data)
                    notifications_sent += 1
                    if config.TEST_MODE:
                        logger.info(f"Notification sent ({days} days) for subscription {subscription.id}")
                except Exception as db_error:
                    error_count += 1
                    logger.error(f"Failed to update subscription {subscription.id} notification flags: {db_error}")
            except Exception as e:
                error_count += 1
                logger.error(f"Error sending notification for subscription {subscription.id}: {e}")
        
        # Обрабатываем активные подписки (батчинг по серверам)
        for subscription in subscriptions_to_enable:
            try:
                if subscription.sub_id and subscription.server_id:
                    # Получаем или создаем клиент API для сервера
                    if subscription.server_id not in server_clients:
                        server = await get_server_by_id(subscription.server_id)
                        if server:
                            server_clients[subscription.server_id] = get_x3ui_client(
                                server.api_url,
                                server.api_username,
                                server.api_password,
                                server.ssl_certificate
                            )
                    
                    if subscription.server_id in server_clients:
                        x3ui_client = server_clients[subscription.server_id]
                        # Включаем всех клиентов с этим subID на всех инбаундах
                        result = await x3ui_client.enable_all_clients_by_sub_id(subscription.sub_id)
                        
                        if result and not result.get("error"):
                            enabled_count += 1
                            if config.TEST_MODE:
                                enabled_clients = result.get("updated", [])
                                logger.debug(f"Enabled {len(enabled_clients)} clients with subID {subscription.sub_id}")
                        else:
                            error_count += 1
                            error_msg = result.get("message", "Unknown error") if result else "Enable error"
                            logger.warning(f"Failed to enable clients with subID {subscription.sub_id}: {error_msg}")
            except Exception as e:
                error_count += 1
                logger.error(f"Error enabling clients for subscription {subscription.id}: {e}")
        
        # Закрываем все клиенты API
        for client in server_clients.values():
            try:
                await client.close()
            except Exception as close_error:
                logger.debug(f"Error closing API client: {close_error}")
        
        # Также проверяем истекшие подписки - убеждаемся, что они отключены и отправляем предупреждения о предстоящем удалении
        expired_subscriptions = await get_all_expired_subscriptions()
        
        # Определяем интервал удаления в зависимости от режима
        if config.TEST_MODE:
            delete_interval = timedelta(minutes=5)
            # В тестовом режиме: первое предупреждение за 3 минуты, второе за 1 минуту до удаления
            warning_1_interval = timedelta(minutes=3)
            warning_2_interval = timedelta(minutes=1)
        else:
            delete_interval = timedelta(days=30)
            # В обычном режиме: первое предупреждение за 7 дней, второе за 3 дня до удаления
            warning_1_interval = timedelta(days=7)
            warning_2_interval = timedelta(days=3)
        
        # Обрабатываем истекшие подписки с переиспользованием клиентов
        expired_server_clients = {}
        for subscription in expired_subscriptions:
            # Пропускаем приватные подписки - они не должны быть в списке истекших
            if subscription.is_private:
                continue
            
            # Убеждаемся, что все клиенты с этим subID отключены на сервере
            if subscription.sub_id and subscription.server_id:
                try:
                    # Получаем или создаем клиент API для сервера
                    if subscription.server_id not in expired_server_clients:
                        server = await get_server_by_id(subscription.server_id)
                        if server:
                            expired_server_clients[subscription.server_id] = get_x3ui_client(
                                server.api_url,
                                server.api_username,
                                server.api_password,
                                server.ssl_certificate
                            )
                    
                    if subscription.server_id in expired_server_clients:
                        x3ui_client = expired_server_clients[subscription.server_id]
                        # Отключаем всех клиентов с этим subID на всех инбаундах
                        result = await x3ui_client.disable_all_clients_by_sub_id(subscription.sub_id)
                        
                        if result and not result.get("error"):
                            if config.TEST_MODE:
                                disabled_clients = result.get("disabled", [])
                                logger.debug(f"Expired subscription {subscription.id} disabled: {len(disabled_clients)} clients with subID {subscription.sub_id}")
                except Exception as e:
                    logger.error(f"Error disabling expired subscription {subscription.id}: {e}")
        
        # Закрываем клиенты для истекших подписок
        for client in expired_server_clients.values():
            try:
                await client.close()
            except Exception as close_error:
                logger.debug(f"Error closing expired API client: {close_error}")
        
        # Проверяем и отправляем предупреждения о предстоящем удалении для всех истекших подписок
        for subscription in expired_subscriptions:
            # Пропускаем приватные подписки
            if subscription.is_private:
                continue
            
            if subscription.expire_date:
                time_since_expiry = current_time - subscription.expire_date
                time_until_deletion = delete_interval - time_since_expiry
                
                # Отправляем первое предупреждение
                if (time_until_deletion <= warning_1_interval and 
                    time_until_deletion > warning_2_interval and
                    not subscription.notification_deletion_warning_1_sent):
                    
                    await send_subscription_deletion_warning_notification(subscription, time_until_deletion, 1)
                    await update_subscription(
                        subscription_id=subscription.id,
                        notification_deletion_warning_1_sent=True
                    )
                    notifications_sent += 1
                    if config.TEST_MODE:
                        logger.info(f"First deletion warning sent for subscription {subscription.id}")
                
                # Отправляем второе предупреждение
                elif (time_until_deletion <= warning_2_interval and
                      time_until_deletion.total_seconds() > 0 and
                      not subscription.notification_deletion_warning_2_sent):
                    
                    await send_subscription_deletion_warning_notification(subscription, time_until_deletion, 2)
                    await update_subscription(
                        subscription_id=subscription.id,
                        notification_deletion_warning_2_sent=True
                    )
                    notifications_sent += 1
                    if config.TEST_MODE:
                        logger.info(f"Second deletion warning sent for subscription {subscription.id}")
        
        if config.TEST_MODE:
            if enabled_count > 0 or disabled_count > 0 or notifications_sent > 0:
                logger.info(f"Subscriptions: enabled={enabled_count}, disabled={disabled_count}, notifications={notifications_sent}, errors={error_count}")
            elif error_count > 0:
                logger.warning(f"Found {error_count} errors managing subscriptions")
            
    except Exception as e:
        logger.error(f"Critical error checking subscriptions: {e}")
        import traceback
        logger.error(traceback.format_exc())


async def delete_old_subscriptions_job():
    """
    Периодическая задача для удаления подписок, которые не продлевались более определенного времени:
    - В TEST_MODE: более 5 минут
    - В обычном режиме: более 30 дней
    Проверяет только истекшие подписки для оптимизации.
    """
    try:
        current_time = datetime.utcnow()
        
        # Определяем интервал удаления в зависимости от режима
        if config.TEST_MODE:
            delete_interval = timedelta(minutes=5)
            interval_text = "5 минут"
        else:
            delete_interval = timedelta(days=30)
            interval_text = "30 дней"
        
        if config.TEST_MODE:
            logger.info(f"Starting deletion of old subscriptions (older than {interval_text})")
        
        # Получаем только истекшие подписки для оптимизации
        try:
            expired_subscriptions = await get_all_expired_subscriptions()
        except Exception as db_error:
            logger.error(f"Failed to get expired subscriptions: {db_error}")
            return
        
        if not expired_subscriptions:
            if config.TEST_MODE:
                logger.info(f"No expired subscriptions found")
            return
        
        # Фильтруем подписки, которые истекли более указанного времени назад
        # Пропускаем приватные подписки - они не удаляются
        old_subscriptions = []
        for subscription in expired_subscriptions:
            # Пропускаем приватные подписки
            if subscription.is_private:
                continue
            
            if subscription.expire_date:
                time_since_expiry = current_time - subscription.expire_date
                if time_since_expiry >= delete_interval:
                    old_subscriptions.append(subscription)
        
        if not old_subscriptions:
            if config.TEST_MODE:
                logger.info(f"No old subscriptions to delete (older than {interval_text})")
            return
        
        if config.TEST_MODE:
            logger.info(f"Found {len(old_subscriptions)} subscriptions to delete (older than {interval_text})")
        
        deleted_count = 0
        error_count = 0
        
        for subscription in old_subscriptions:
            try:
                # Отправляем уведомление об удалении перед удалением подписки
                await send_subscription_deleted_notification(subscription)
                
                success, message = await delete_subscription_completely(subscription.id)
                if success:
                    deleted_count += 1
                    if config.TEST_MODE:
                        logger.info(f"Deleted subscription #{subscription.id} (expired {current_time - subscription.expire_date} ago)")
                else:
                    error_count += 1
                    logger.error(f"Failed to delete subscription #{subscription.id}: {message}")
            except Exception as e:
                error_count += 1
                logger.error(f"Exception deleting subscription #{subscription.id}: {e}")
        
        if config.TEST_MODE:
            logger.info(f"Deletion completed: deleted={deleted_count}, errors={error_count}")
        
    except Exception as e:
        logger.error(f"Critical error deleting old subscriptions: {e}")
        import traceback
        logger.error(traceback.format_exc())


def start_subscription_checker():
    """Запустить планировщик для проверки подписок"""
    if config.TEST_MODE:
        # Тестовый режим: проверка каждые 10 секунд для быстрого обнаружения истекших подписок
        add_job(
            check_subscriptions_job,
            trigger="interval",
            seconds=10,
            id="check_expired_subscriptions_test"
        )
        # В тестовом режиме проверка удаления подписок каждые 5 минут
        add_job(
            delete_old_subscriptions_job,
            trigger="interval",
            minutes=5,
            id="delete_old_subscriptions_test"
        )
        logger.info("✅ Задачи проверки подписок добавлены (тестовый режим: каждые 10 секунд)")
        logger.info("✅ Задача удаления старых подписок добавлена (каждые 5 минут)")
    else:
        # Обычный режим: проверка каждый день в 00:00 UTC и каждые 6 часов
        add_job(
            check_subscriptions_job,
            trigger="cron",
            hour=0,
            minute=0,
            id="check_expired_subscriptions_daily"
        )
        add_job(
            check_subscriptions_job,
            trigger="cron",
            hour="*/6",
            minute=0,
            id="check_expired_subscriptions_hourly"
        )
        # Удаление старых подписок: каждые 6 часов
        add_job(
            delete_old_subscriptions_job,
            trigger="cron",
            hour="*/6",
            minute=0,
            id="delete_old_subscriptions_hourly"
        )
        logger.info("✅ Задачи проверки подписок добавлены в планировщик (обычный режим: каждые 6 часов)")
        logger.info("✅ Задача удаления старых подписок добавлена (каждые 6 часов)")

