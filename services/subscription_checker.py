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

logger = logging.getLogger(__name__)


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
        text += f"📦 <b>Локация:</b> {location_name} ({subscription_id})\n"
        text += f"📅 Подписка закончилась. Для продолжения использования необходимо продлить подписку.\n\n"
        text += "Нажмите кнопку ниже, чтобы продлить подписку:"
        
        # Создаем клавиатуру с кнопкой продления
        kb = InlineKeyboardBuilder()
        kb.button(text="🔄 Продлить", callback_data=f"renew_subscription_{subscription.id}")
        kb.adjust(1)
        
        # Отправляем сообщение
        await bot.send_message(
            chat_id=int(user.tg_id),
            text=text,
            reply_markup=kb.as_markup(),
            parse_mode="HTML"
        )
        
        # Отправляем сообщение с кнопками главного меню, чтобы они всегда были доступны
        from utils.keyboards.main_kb import main_menu
        await bot.send_message(
            chat_id=int(user.tg_id),
            text=" ",  # Минимальный текст (пробел)
            reply_markup=main_menu()
        )
        
        logger.info(f"✅ Отправлено уведомление об истечении подписки пользователю {user.tg_id} (подписка {subscription.id})")
    except Exception as e:
        logger.error(f"❌ Ошибка при отправке уведомления об истечении подписки {subscription.id}: {e}")
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
        text += f"📦 <b>Локация:</b> {location_name} ({subscription_id})\n"
        text += f"🗑️ <b>Подписка будет удалена через:</b> {time_text}\n\n"
        text += f"⚠️ Если вы не продлите подписку, она будет удалена из панели и базы данных.\n\n"
        text += "Нажмите кнопку ниже, чтобы продлить подписку:"
        
        # Создаем клавиатуру с кнопкой продления
        kb = InlineKeyboardBuilder()
        kb.button(text="🔄 Продлить", callback_data=f"renew_subscription_{subscription.id}")
        kb.adjust(1)
        
        # Отправляем сообщение
        await bot.send_message(
            chat_id=int(user.tg_id),
            text=text,
            reply_markup=kb.as_markup(),
            parse_mode="HTML"
        )
        
        # Отправляем сообщение с кнопками главного меню
        await bot.send_message(
            chat_id=int(user.tg_id),
            text=" ",  # Минимальный текст (пробел)
            reply_markup=main_menu()
        )
        
        logger.info(f"✅ Отправлено предупреждение #{warning_number} о предстоящем удалении подписки пользователю {user.tg_id} (подписка {subscription.id})")
    except Exception as e:
        logger.error(f"❌ Ошибка при отправке предупреждения о предстоящем удалении подписки {subscription.id}: {e}")
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
        text += f"📦 <b>Локация:</b> {location_name} ({subscription_id})\n"
        text += f"⚠️ Ваша подписка была удалена из панели и базы данных, так как она не была продлена в течение установленного времени.\n\n"
        text += "Вы можете приобрести новую подписку, нажав кнопку ниже:"
        
        # Создаем клавиатуру с кнопкой покупки
        from aiogram.utils.keyboard import InlineKeyboardBuilder
        kb = InlineKeyboardBuilder()
        kb.button(text="🛒 Приобрести подписку", callback_data="profile_purchase")
        kb.adjust(1)
        
        # Отправляем сообщение
        await bot.send_message(
            chat_id=int(user.tg_id),
            text=text,
            reply_markup=kb.as_markup(),
            parse_mode="HTML"
        )
        
        # Отправляем сообщение с кнопками главного меню
        await bot.send_message(
            chat_id=int(user.tg_id),
            text=" ",  # Минимальный текст (пробел)
            reply_markup=main_menu()
        )
        
        logger.info(f"✅ Отправлено уведомление об удалении подписки пользователю {user.tg_id} (подписка {subscription.id})")
    except Exception as e:
        logger.error(f"❌ Ошибка при отправке уведомления об удалении подписки {subscription.id}: {e}")
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
        
        # Создаем клавиатуру с кнопкой продления
        kb = InlineKeyboardBuilder()
        kb.button(text="🔄 Продлить", callback_data=f"renew_subscription_{subscription.id}")
        kb.adjust(1)
        
        # Отправляем сообщение
        await bot.send_message(
            chat_id=int(user.tg_id),
            text=text,
            reply_markup=kb.as_markup(),
            parse_mode="HTML"
        )
        
        # Отправляем сообщение с кнопками главного меню
        await bot.send_message(
            chat_id=int(user.tg_id),
            text=" ",  # Минимальный текст (пробел)
            reply_markup=main_menu()
        )
        
        logger.info(f"✅ Отправлено уведомление о скором окончании подписки ({days_left} дней) пользователю {user.tg_id} (подписка {subscription.id})")
    except Exception as e:
        logger.error(f"❌ Ошибка при отправке уведомления о скором окончании подписки {subscription.id}: {e}")
        import traceback
        logger.error(traceback.format_exc())


async def check_subscriptions_job():
    """
    Периодическая задача для проверки и управления подписками:
    - Отключает клиентов на сервере, если подписка истекла
    - Включает клиентов на сервере, если подписка активна
    - Отправляет уведомления о скором окончании подписки (за 3 дня и за 1 день)
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
        
        # Получаем все активные подписки
        active_subscriptions = await get_all_active_subscriptions()
        logger.info(f"🔍 Проверка {len(active_subscriptions)} активных подписок...")
        
        enabled_count = 0
        disabled_count = 0
        error_count = 0
        notifications_sent = 0
        
        # Проверяем каждую активную подписку
        for subscription in active_subscriptions:
            try:
                # Если подписка истекла - отключаем клиента на сервере
                # Проверяем только активные подписки, чтобы не отправлять уведомление повторно
                if subscription.expire_date and subscription.expire_date < current_time and subscription.status == "active":
                    # Сначала пытаемся отключить клиента на сервере (если есть)
                    client_disabled = False
                    if subscription.x3ui_client_email and subscription.server_id:
                        try:
                            server = await get_server_by_id(subscription.server_id)
                            if server:
                                x3ui_client = get_x3ui_client(
                                    server.api_url,
                                    server.api_username,
                                    server.api_password
                                )
                                
                                result = await x3ui_client.disable_client(subscription.x3ui_client_email)
                                await x3ui_client.close()
                                
                                if result and not result.get("error"):
                                    client_disabled = True
                                    disabled_count += 1
                                    logger.info(f"❌ Отключен клиент {subscription.x3ui_client_email} (подписка истекла)")
                                else:
                                    error_count += 1
                                    logger.error(f"⚠️ Не удалось отключить клиента {subscription.x3ui_client_email}")
                        except Exception as e:
                            error_count += 1
                            logger.error(f"⚠️ Ошибка при отключении клиента {subscription.x3ui_client_email}: {e}")
                    
                    # ВСЕГДА обновляем статус подписки в БД и отправляем уведомление,
                    # даже если не удалось отключить клиента на сервере
                    await update_subscription(
                        subscription_id=subscription.id,
                        status="expired"
                    )
                    if not client_disabled:
                        disabled_count += 1
                    
                    # Отправляем уведомление пользователю (только один раз при смене статуса)
                    await send_subscription_expired_notification(subscription)
                    logger.info(f"✅ Подписка {subscription.id} помечена как истекшая, уведомление отправлено")
                else:
                    # Подписка активна - проверяем уведомления о скором окончании
                    if subscription.expire_date and subscription.expire_date > current_time:
                        # Проверяем, нужно ли отправить уведомление за 3 дня
                        time_until_expiry = subscription.expire_date - current_time
                        
                        # Уведомление за 3 дня (или за 30 секунд в тестовом режиме)
                        if (time_until_expiry <= notification_3_days_interval and 
                            time_until_expiry > notification_1_day_interval and
                            not subscription.notification_3_days_sent):
                            
                            days_left = 3 if not config.TEST_MODE else int(time_until_expiry.total_seconds())
                            await send_subscription_expiring_soon_notification(subscription, days_left)
                            await update_subscription(
                                subscription_id=subscription.id,
                                notification_3_days_sent=True
                            )
                            notifications_sent += 1
                            logger.info(f"📧 Отправлено уведомление за 3 дня для подписки {subscription.id}")
                        
                        # Уведомление за 1 день (или за 10 секунд в тестовом режиме)
                        elif (time_until_expiry <= notification_1_day_interval and
                              not subscription.notification_1_day_sent):
                            
                            days_left = 1 if not config.TEST_MODE else int(time_until_expiry.total_seconds())
                            await send_subscription_expiring_soon_notification(subscription, days_left)
                            await update_subscription(
                                subscription_id=subscription.id,
                                notification_1_day_sent=True
                            )
                            notifications_sent += 1
                            logger.info(f"📧 Отправлено уведомление за 1 день для подписки {subscription.id}")
                    
                    # Убеждаемся, что клиент включен на сервере
                    if subscription.x3ui_client_email and subscription.server_id:
                        server = await get_server_by_id(subscription.server_id)
                        if server:
                            x3ui_client = get_x3ui_client(
                                server.api_url,
                                server.api_username,
                                server.api_password
                            )
                            
                            result = await x3ui_client.enable_client(subscription.x3ui_client_email)
                            await x3ui_client.close()
                            
                            if result and not result.get("error"):
                                enabled_count += 1
                                logger.debug(f"✅ Клиент {subscription.x3ui_client_email} активен")
                            else:
                                error_count += 1
                                logger.warning(f"⚠️ Не удалось включить клиента {subscription.x3ui_client_email}")
            except Exception as e:
                error_count += 1
                logger.error(f"❌ Ошибка при обработке подписки {subscription.id}: {e}")
        
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
        
        for subscription in expired_subscriptions:
            # Убеждаемся, что клиент отключен на сервере
            if subscription.x3ui_client_email and subscription.server_id:
                try:
                    server = await get_server_by_id(subscription.server_id)
                    if server:
                        x3ui_client = get_x3ui_client(
                            server.api_url,
                            server.api_username,
                            server.api_password
                        )
                        
                        result = await x3ui_client.disable_client(subscription.x3ui_client_email)
                        await x3ui_client.close()
                        
                        if result and not result.get("error"):
                            logger.debug(f"❌ Истекшая подписка {subscription.id} отключена на сервере")
                except Exception as e:
                    logger.error(f"❌ Ошибка при отключении истекшей подписки {subscription.id}: {e}")
            
            # Проверяем и отправляем предупреждения о предстоящем удалении
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
                    logger.info(f"📧 Отправлено первое предупреждение о предстоящем удалении для подписки {subscription.id}")
                
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
                    logger.info(f"📧 Отправлено второе предупреждение о предстоящем удалении для подписки {subscription.id}")
        
        if enabled_count > 0 or disabled_count > 0 or notifications_sent > 0:
            logger.info(f"📊 Управление подписками: включено {enabled_count}, отключено {disabled_count}, уведомлений {notifications_sent}, ошибок {error_count}")
        elif error_count > 0:
            logger.warning(f"⚠️ Обнаружено {error_count} ошибок при управлении подписками")
        else:
            logger.debug("✅ Все подписки в актуальном состоянии")
            
    except Exception as e:
        logger.error(f"❌ Критическая ошибка при проверке подписок: {e}")
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
        
        logger.info(f"🗑️ Запуск задачи удаления старых подписок (старше {interval_text})")
        
        # Получаем только истекшие подписки для оптимизации
        expired_subscriptions = await get_all_expired_subscriptions()
        
        if not expired_subscriptions:
            logger.info(f"✅ Истекших подписок не найдено")
            return
        
        # Фильтруем подписки, которые истекли более указанного времени назад
        old_subscriptions = []
        for subscription in expired_subscriptions:
            if subscription.expire_date:
                time_since_expiry = current_time - subscription.expire_date
                if time_since_expiry >= delete_interval:
                    old_subscriptions.append(subscription)
        
        if not old_subscriptions:
            logger.info(f"✅ Старых подписок для удаления не найдено (старше {interval_text})")
            return
        
        logger.info(f"🔍 Найдено {len(old_subscriptions)} подписок для удаления (старше {interval_text})")
        
        deleted_count = 0
        error_count = 0
        
        for subscription in old_subscriptions:
            try:
                # Отправляем уведомление об удалении перед удалением подписки
                await send_subscription_deleted_notification(subscription)
                
                success, message = await delete_subscription_completely(subscription.id)
                if success:
                    deleted_count += 1
                    logger.info(f"✅ Удалена подписка #{subscription.id} (истекла {current_time - subscription.expire_date} назад)")
                else:
                    error_count += 1
                    logger.error(f"❌ Ошибка при удалении подписки #{subscription.id}: {message}")
            except Exception as e:
                error_count += 1
                logger.error(f"❌ Исключение при удалении подписки #{subscription.id}: {e}")
        
        logger.info(
            f"📊 Удаление старых подписок завершено: "
            f"успешно удалено {deleted_count}, ошибок {error_count}"
        )
        
    except Exception as e:
        logger.error(f"❌ Критическая ошибка при удалении старых подписок: {e}")
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

