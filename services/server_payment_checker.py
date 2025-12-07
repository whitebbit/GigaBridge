"""
Сервис для проверки и отправки уведомлений админам об оплате серверов
"""
from services.scheduler import add_job
from utils.db import get_all_servers, get_all_admins
from core.config import config
from datetime import datetime, timedelta
import logging
import html

logger = logging.getLogger(__name__)


async def send_server_payment_notification(server, days_left: int = None, is_expired: bool = False):
    """Отправить уведомление админам об оплате сервера"""
    try:
        from core.loader import bot
        
        # Получаем всех админов
        admins = await get_all_admins()
        
        if not admins:
            logger.warning("Нет администраторов для отправки уведомлений об оплате сервера")
            return
        
        # Формируем сообщение
        location_name = server.location.name if server.location else "Неизвестно"
        
        if is_expired:
            text = f"❌ <b>Сервер требует оплаты!</b>\n\n"
            text += f"🖥️ <b>Сервер:</b> {html.escape(server.name)}\n"
            text += f"🌍 <b>Локация:</b> {html.escape(location_name)}\n"
            if server.payment_expire_date:
                expire_date_str = server.payment_expire_date.strftime("%d.%m.%Y")
                days_passed = (datetime.utcnow() - server.payment_expire_date).days
                text += f"📅 <b>Оплата истекла:</b> {expire_date_str} ({days_passed} дн. назад)\n\n"
            text += "⚠️ <b>Необходимо срочно продлить оплату сервера!</b>"
        else:
            text = f"⏰ <b>Напоминание об оплате сервера</b>\n\n"
            text += f"🖥️ <b>Сервер:</b> {html.escape(server.name)}\n"
            text += f"🌍 <b>Локация:</b> {html.escape(location_name)}\n"
            if server.payment_expire_date:
                expire_date_str = server.payment_expire_date.strftime("%d.%m.%Y")
                text += f"📅 <b>Оплата до:</b> {expire_date_str}\n"
            if days_left is not None:
                days_text = "день" if days_left == 1 else ("дня" if days_left in [2, 3, 4] else "дней")
                text += f"⏳ <b>Осталось:</b> {days_left} {days_text}\n\n"
            text += "💡 Не забудьте продлить оплату сервера!"
        
        # Отправляем уведомления всем админам
        sent_count = 0
        failed_count = 0
        
        for admin in admins:
            try:
                await bot.send_message(
                    chat_id=int(admin.tg_id),
                    text=text,
                    parse_mode="HTML"
                )
                sent_count += 1
            except Exception as e:
                failed_count += 1
                logger.error(f"❌ Ошибка при отправке уведомления админу {admin.tg_id}: {e}")
        
        logger.info(
            f"✅ Уведомления об оплате сервера {server.name} отправлены: "
            f"успешно {sent_count}, ошибок {failed_count}"
        )
        
    except Exception as e:
        logger.error(f"❌ Критическая ошибка при отправке уведомлений об оплате сервера: {e}")
        import traceback
        logger.error(traceback.format_exc())


async def check_server_payments_job():
    """
    Периодическая задача для проверки оплаты серверов и отправки уведомлений админам:
    - Уведомление за 7 дней до окончания
    - Уведомление за 3 дня до окончания
    - Уведомление за 1 день до окончания
    - Уведомление в день окончания
    - Уведомление после истечения (ежедневно, пока не обновлен период)
    """
    try:
        current_time = datetime.utcnow()
        
        # Определяем интервалы для уведомлений в зависимости от режима
        if config.TEST_MODE:
            # В тестовом режиме: уведомления за 30 секунд, 10 секунд, 5 секунд и при истечении
            notification_7_days_interval = timedelta(seconds=30)
            notification_3_days_interval = timedelta(seconds=10)
            notification_1_day_interval = timedelta(seconds=5)
            expired_check_interval = timedelta(seconds=1)
        else:
            # В обычном режиме: уведомления за 7 дней, 3 дня, 1 день и при истечении
            notification_7_days_interval = timedelta(days=7)
            notification_3_days_interval = timedelta(days=3)
            notification_1_day_interval = timedelta(days=1)
            expired_check_interval = timedelta(days=0)  # В день истечения
        
        # Получаем все серверы
        try:
            servers = await get_all_servers()
        except Exception as db_error:
            logger.error(f"Failed to get servers: {db_error}")
            return
        
        if not servers:
            if config.TEST_MODE:
                logger.debug("No servers found for payment check")
            return
        
        notifications_sent = 0
        
        for server in servers:
            try:
                # Пропускаем серверы без информации об оплате
                if not server.payment_expire_date:
                    continue
                
                time_until_expiry = server.payment_expire_date - current_time
                days_left = time_until_expiry.days
                
                # Проверяем, истекла ли оплата
                if time_until_expiry.total_seconds() < 0:
                    # Оплата истекла - отправляем уведомление (но не каждый раз, чтобы не спамить)
                    # Отправляем только если прошло больше суток с момента истечения
                    # или если это первая проверка после истечения
                    if abs(days_left) == 0 or abs(days_left) % 1 == 0:  # Каждый день после истечения
                        await send_server_payment_notification(server, days_left=abs(days_left), is_expired=True)
                        notifications_sent += 1
                else:
                    # Оплата еще не истекла - проверяем интервалы для уведомлений
                    # Уведомление за 7 дней
                    if (time_until_expiry <= notification_7_days_interval and 
                        time_until_expiry > notification_3_days_interval):
                        await send_server_payment_notification(server, days_left=days_left)
                        notifications_sent += 1
                    
                    # Уведомление за 3 дня
                    elif (time_until_expiry <= notification_3_days_interval and 
                          time_until_expiry > notification_1_day_interval):
                        await send_server_payment_notification(server, days_left=days_left)
                        notifications_sent += 1
                    
                    # Уведомление за 1 день
                    elif (time_until_expiry <= notification_1_day_interval and 
                          time_until_expiry.total_seconds() > 0):
                        await send_server_payment_notification(server, days_left=days_left)
                        notifications_sent += 1
                    
                    # Уведомление в день истечения (если осталось менее суток)
                    elif time_until_expiry <= expired_check_interval and time_until_expiry.total_seconds() >= 0:
                        await send_server_payment_notification(server, days_left=0)
                        notifications_sent += 1
                        
            except Exception as e:
                logger.error(f"Error checking payment for server {server.id}: {e}")
        
        if config.TEST_MODE and notifications_sent > 0:
            logger.info(f"Server payment check completed: {notifications_sent} notifications sent")
            
    except Exception as e:
        logger.error(f"Critical error checking server payments: {e}")
        import traceback
        logger.error(traceback.format_exc())


def start_server_payment_checker():
    """Запустить планировщик для проверки оплаты серверов"""
    if config.TEST_MODE:
        # Тестовый режим: проверка каждые 10 секунд
        add_job(
            check_server_payments_job,
            trigger="interval",
            seconds=10,
            id="check_server_payments_test"
        )
        logger.info("✅ Задача проверки оплаты серверов добавлена (тестовый режим: каждые 10 секунд)")
    else:
        # Обычный режим: проверка каждый день в 09:00 UTC
        add_job(
            check_server_payments_job,
            trigger="cron",
            hour=9,
            minute=0,
            id="check_server_payments_daily"
        )
        # Также проверяем каждые 6 часов для более оперативных уведомлений
        add_job(
            check_server_payments_job,
            trigger="cron",
            hour="*/6",
            minute=0,
            id="check_server_payments_hourly"
        )
        logger.info("✅ Задачи проверки оплаты серверов добавлены в планировщик (обычный режим: каждые 6 часов)")

