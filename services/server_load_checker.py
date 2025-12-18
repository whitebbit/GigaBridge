"""
Сервис для проверки загрузки серверов и отправки уведомлений админам
когда сервер почти заполнен
"""
from services.scheduler import add_job
from utils.db import get_all_servers, get_all_admins, count_active_subscriptions_by_server
from core.config import config
import logging
import html

logger = logging.getLogger(__name__)

# Порог загрузки для уведомления (в процентах)
LOAD_THRESHOLD_PERCENT = 80  # Уведомление при 80% загрузки

# Кэш для отслеживания уже отправленных уведомлений
# Формат: {server_id: last_notification_percent}
_notification_cache = {}


async def send_server_load_notification(server, current_users: int, max_users: int, load_percent: float):
    """Отправить уведомление админам о высокой загрузке сервера"""
    try:
        from core.loader import bot
        
        # Получаем всех админов
        admins = await get_all_admins()
        
        if not admins:
            logger.warning("Нет администраторов для отправки уведомлений о загрузке сервера")
            return
        
        # Формируем сообщение
        location_name = server.location.name if server.location else "Неизвестно"
        
        text = f"⚠️ <b>Высокая загрузка сервера!</b>\n\n"
        text += f"🖥️ <b>Сервер:</b> {html.escape(server.name)}\n"
        text += f"🌍 <b>Локация:</b> {html.escape(location_name)}\n"
        text += f"👥 <b>Текущих пользователей:</b> {current_users}\n"
        text += f"📊 <b>Максимум пользователей:</b> {max_users}\n"
        text += f"📈 <b>Загрузка:</b> {load_percent:.1f}%\n\n"
        
        # Определяем уровень критичности
        if load_percent >= 95:
            text += "🔴 <b>КРИТИЧЕСКАЯ ЗАГРУЗКА!</b> Сервер почти заполнен!\n"
            text += "⚠️ Рекомендуется срочно добавить новый сервер или увеличить лимит."
        elif load_percent >= 90:
            text += "🟠 <b>Очень высокая загрузка!</b> Сервер почти заполнен.\n"
            text += "💡 Рекомендуется подготовить новый сервер или увеличить лимит."
        else:
            text += "🟡 <b>Высокая загрузка.</b> Сервер приближается к максимуму.\n"
            text += "💡 Стоит подумать о добавлении нового сервера."
        
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
                logger.error(f"❌ Ошибка при отправке уведомления о загрузке админу {admin.tg_id}: {e}")
        
        logger.info(
            f"✅ Уведомления о загрузке сервера {server.name} отправлены: "
            f"успешно {sent_count}, ошибок {failed_count}"
        )
        
        # Сохраняем в кэш, что уведомление было отправлено для этого уровня загрузки
        _notification_cache[server.id] = load_percent
        
    except Exception as e:
        logger.error(f"❌ Критическая ошибка при отправке уведомлений о загрузке сервера: {e}")
        import traceback
        logger.error(traceback.format_exc())


async def check_server_load(server_id: int = None):
    """
    Проверить загрузку сервера(ов) и отправить уведомления админам при высокой загрузке
    
    Args:
        server_id: ID конкретного сервера для проверки (если None, проверяются все серверы)
    """
    try:
        # Получаем сервер(ы) для проверки
        if server_id:
            from utils.db import get_server_by_id
            server = await get_server_by_id(server_id)
            servers = [server] if server else []
        else:
            servers = await get_all_servers()
        
        if not servers:
            return
        
        notifications_sent = 0
        
        for server in servers:
            try:
                # Пропускаем неактивные серверы
                if not server.is_active:
                    continue
                
                # Пропускаем серверы без установленного лимита пользователей
                if server.max_users is None:
                    continue
                
                # Подсчитываем текущее количество активных подписок
                current_users = await count_active_subscriptions_by_server(server.id)
                
                # Вычисляем процент загрузки
                if server.max_users == 0:
                    continue
                
                load_percent = (current_users / server.max_users) * 100
                
                # Проверяем, достиг ли сервер порога загрузки
                if load_percent >= LOAD_THRESHOLD_PERCENT:
                    # Проверяем, не отправляли ли мы уже уведомление для этого уровня загрузки
                    last_notification_percent = _notification_cache.get(server.id, 0)
                    
                    # Отправляем уведомление, если:
                    # 1. Это первое уведомление для этого сервера
                    # 2. Загрузка увеличилась на 5% или более с момента последнего уведомления
                    # 3. Загрузка достигла критического уровня (95%+)
                    should_notify = (
                        last_notification_percent == 0 or  # Первое уведомление
                        load_percent >= last_notification_percent + 5 or  # Увеличилась на 5%
                        (load_percent >= 95 and last_notification_percent < 95)  # Достиг критического уровня
                    )
                    
                    if should_notify:
                        await send_server_load_notification(
                            server, 
                            current_users, 
                            server.max_users, 
                            load_percent
                        )
                        notifications_sent += 1
                else:
                    # Если загрузка упала ниже порога, сбрасываем кэш для этого сервера
                    if server.id in _notification_cache:
                        del _notification_cache[server.id]
                        
            except Exception as e:
                logger.error(f"Ошибка при проверке загрузки сервера {server.id}: {e}")
        
        if config.TEST_MODE and notifications_sent > 0:
            logger.info(f"Проверка загрузки серверов завершена: отправлено {notifications_sent} уведомлений")
            
    except Exception as e:
        logger.error(f"Критическая ошибка при проверке загрузки серверов: {e}")
        import traceback
        logger.error(traceback.format_exc())


async def check_all_servers_load_job():
    """
    Периодическая задача для проверки загрузки всех серверов
    """
    await check_server_load()


def start_server_load_checker():
    """Запустить планировщик для проверки загрузки серверов"""
    if config.TEST_MODE:
        # Тестовый режим: проверка каждые 30 секунд
        add_job(
            check_all_servers_load_job,
            trigger="interval",
            seconds=30,
            id="check_server_load_test"
        )
        logger.info("✅ Задача проверки загрузки серверов добавлена (тестовый режим: каждые 30 секунд)")
    else:
        # Обычный режим: проверка каждый час
        add_job(
            check_all_servers_load_job,
            trigger="interval",
            hours=1,
            id="check_server_load_hourly"
        )
        logger.info("✅ Задача проверки загрузки серверов добавлена (обычный режим: каждый час)")

