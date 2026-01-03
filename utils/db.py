from database.base import async_session
from database.models import User, Server, Payment, Subscription, Tariff, Location, PromoCode, PromoCodeUsage, SupportTicket, Platform, Tutorial, TutorialFile, AdminDocumentation, AdminDocumentationFile
from sqlalchemy import select, func, and_, or_
from sqlalchemy.orm import selectinload, joinedload
from typing import Optional, List
from datetime import datetime, timedelta, timezone
import re
from utils.cache import CacheService, CacheKeys


def get_timezone_offset_from_language(language_code: Optional[str] = None) -> int:
    """
    Определяет часовой пояс по языку пользователя
    
    Args:
        language_code: код языка пользователя (например, 'ru', 'en', 'de')
    
    Returns:
        смещение часового пояса в часах относительно UTC
    """
    if not language_code:
        return 3  # По умолчанию московское время (UTC+3)
    
    language_code = language_code.lower()
    
    # Основные часовые пояса по языкам (примерные значения)
    timezone_map = {
        'ru': 3,      # Россия - московское время (UTC+3)
        'uk': 2,      # Украина (UTC+2)
        'by': 3,      # Беларусь (UTC+3)
        'kz': 5,      # Казахстан (UTC+5)
        'en': 0,      # Англия (UTC+0)
        'de': 1,      # Германия (UTC+1)
        'fr': 1,      # Франция (UTC+1)
        'it': 1,      # Италия (UTC+1)
        'es': 1,      # Испания (UTC+1)
        'pl': 1,      # Польша (UTC+1)
        'tr': 3,      # Турция (UTC+3)
    }
    
    # Проверяем точное совпадение
    if language_code in timezone_map:
        return timezone_map[language_code]
    
    # Проверяем первые 2 символа (например, 'en-US' -> 'en')
    lang_prefix = language_code.split('-')[0] if '-' in language_code else language_code
    if lang_prefix in timezone_map:
        return timezone_map[lang_prefix]
    
    # По умолчанию московское время
    return 3


def utc_to_user_timezone(utc_datetime: datetime, timezone_offset: Optional[int] = None, user: Optional[User] = None, language_code: Optional[str] = None) -> datetime:
    """
    Конвертирует UTC время в локальное время пользователя
    
    Args:
        utc_datetime: datetime объект в UTC (без timezone info)
        timezone_offset: смещение часового пояса пользователя в часах относительно UTC (опционально)
        user: объект User для получения часового пояса из профиля (опционально)
        language_code: код языка пользователя для автоматического определения часового пояса (опционально)
    
    Returns:
        datetime объект с локальным временем пользователя (без timezone info)
    """
    # Определяем часовой пояс пользователя
    if timezone_offset is None:
        if user and hasattr(user, 'timezone_offset') and user.timezone_offset is not None:
            timezone_offset = user.timezone_offset
        elif language_code:
            # Пытаемся определить по языку пользователя
            timezone_offset = get_timezone_offset_from_language(language_code)
        else:
            # По умолчанию используем московское время (UTC+3)
            timezone_offset = 3
    
    # Если datetime уже с timezone info, конвертируем, иначе считаем что это UTC
    if utc_datetime.tzinfo is None:
        # Считаем что datetime в UTC
        utc_datetime = utc_datetime.replace(tzinfo=timezone.utc)
    
    # Локальное время пользователя
    user_tz = timezone(timedelta(hours=timezone_offset))
    local_time = utc_datetime.astimezone(user_tz)
    
    # Возвращаем naive datetime (без timezone info) с локальным временем
    return local_time.replace(tzinfo=None)


def utc_to_moscow(utc_datetime: datetime) -> datetime:
    """
    Конвертирует UTC время в московское время (UTC+3)
    Обратная совместимость - вызывает utc_to_user_timezone с offset=3
    
    Args:
        utc_datetime: datetime объект в UTC (без timezone info)
    
    Returns:
        datetime объект с московским временем (без timezone info)
    """
    return utc_to_user_timezone(utc_datetime, timezone_offset=3)


def generate_location_unique_name(location_name: str, subscription_id: int = None, seed: str = None) -> str:
    """
    Генерирует уникальное название локации в формате {location_slug}-{unique_id}
    Например: "moscow-a1b2c3" или "sankt-peterburg-x9y8z7"
    
    Args:
        location_name: Название локации (например, "Москва", "Санкт-Петербург")
        subscription_id: ID подписки для генерации уникального идентификатора (опционально)
        seed: Семя для детерминированной генерации (опционально, если не указано - генерируется случайно)
    
    Returns:
        Уникальное название локации в нижнем регистре с дефисами
    """
    import hashlib
    import unicodedata
    
    # Транслитерация кириллицы в латиницу
    translit_map = {
        'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e', 'ё': 'yo',
        'ж': 'zh', 'з': 'z', 'и': 'i', 'й': 'y', 'к': 'k', 'л': 'l', 'м': 'm',
        'н': 'n', 'о': 'o', 'п': 'p', 'р': 'r', 'с': 's', 'т': 't', 'у': 'u',
        'ф': 'f', 'х': 'h', 'ц': 'ts', 'ч': 'ch', 'ш': 'sh', 'щ': 'sch',
        'ъ': '', 'ы': 'y', 'ь': '', 'э': 'e', 'ю': 'yu', 'я': 'ya',
        'А': 'A', 'Б': 'B', 'В': 'V', 'Г': 'G', 'Д': 'D', 'Е': 'E', 'Ё': 'Yo',
        'Ж': 'Zh', 'З': 'Z', 'И': 'I', 'Й': 'Y', 'К': 'K', 'Л': 'L', 'М': 'M',
        'Н': 'N', 'О': 'O', 'П': 'P', 'Р': 'R', 'С': 'S', 'Т': 'T', 'У': 'U',
        'Ф': 'F', 'Х': 'H', 'Ц': 'Ts', 'Ч': 'Ch', 'Ш': 'Sh', 'Щ': 'Sch',
        'Ъ': '', 'Ы': 'Y', 'Ь': '', 'Э': 'E', 'Ю': 'Yu', 'Я': 'Ya'
    }
    
    # Нормализуем строку (убираем диакритические знаки)
    normalized = unicodedata.normalize('NFKD', location_name)
    
    # Транслитерируем
    transliterated = ''.join(translit_map.get(char, char) for char in normalized)
    
    # Убираем все кроме букв, цифр и пробелов, заменяем пробелы на дефисы
    slug = re.sub(r'[^a-zA-Z0-9\s-]', '', transliterated)
    slug = re.sub(r'\s+', '-', slug.strip())
    slug = re.sub(r'-+', '-', slug)  # Убираем множественные дефисы
    slug = slug.lower()
    
    # Если slug пустой, используем fallback
    if not slug:
        slug = f"loc{subscription_id}" if subscription_id else "location"
    
    # Генерируем детерминированный уникальный идентификатор
    # Используем seed если передан, иначе генерируем на основе location_name и subscription_id
    if seed:
        # Используем переданное seed для генерации
        hash_input = seed
    elif subscription_id is not None:
        # Детерминированная генерация на основе location_name и subscription_id
        hash_input = f"{location_name}-{subscription_id}"
    else:
        # Если нет ни seed, ни subscription_id, используем только location_name
        hash_input = location_name
    
    # Создаем хеш для детерминированной генерации
    hash_obj = hashlib.md5(hash_input.encode('utf-8'))
    unique_id = hash_obj.hexdigest()[:6]  # Первые 6 символов MD5 хеша
    
    return f"{slug}-{unique_id}"


def get_subscription_identifier(subscription: Subscription, location_name: str = None) -> str:
    """
    Генерирует уникальный идентификатор подписки в формате {LOCATION_UNIQUE_NAME}
    Использует сохраненное location_unique_name, если оно есть, иначе генерирует новое
    
    Args:
        subscription: Объект подписки
        location_name: Название локации (опционально, если не передано, будет получено из БД)
    
    Returns:
        Строка в формате "moscow-a1b2c3" или "sankt-peterburg-x9y8z7"
    """
    # Если у подписки уже есть сохраненное уникальное название, используем его
    if subscription.location_unique_name:
        return subscription.location_unique_name
    
    # Иначе генерируем новое (для старых подписок без сохраненного названия)
    if not location_name or location_name == "Неизвестно":
        location_name = f"LOC{subscription.id}"
    
    return generate_location_unique_name(location_name, subscription.id)


async def get_user_by_tg_id(tg_id: str, use_cache: bool = True) -> Optional[User]:
    """Получить пользователя по Telegram ID с кэшированием ID"""
    tg_id_str = str(tg_id)
    cache_key = CacheKeys.USER_BY_TG_ID.format(tg_id=tg_id_str)
    
    # Проверяем кэш - если есть ID, используем его для быстрого запроса
    cached_id = None
    if use_cache:
        cached = await CacheService.get(cache_key)
        if cached and isinstance(cached, dict) and 'id' in cached:
            cached_id = cached.get('id')
    
    async with async_session() as session:
        if cached_id:
            # Быстрый запрос по ID (есть индекс)
            result = await session.execute(select(User).where(User.id == cached_id))
            user = result.scalar_one_or_none()
            if user and user.tg_id == tg_id_str:
                return user
        
        # Обычный запрос по tg_id
        result = await session.execute(select(User).where(User.tg_id == tg_id_str))
        user = result.scalar_one_or_none()
        
        # Кэшируем только ID для быстрого доступа
        if user and use_cache:
            await CacheService.set(cache_key, {'id': user.id}, ttl=300)
        
        return user


async def is_admin(tg_id: str) -> bool:
    """Проверить, является ли пользователь администратором"""
    user = await get_user_by_tg_id(tg_id)
    return user.is_admin if user else False


async def get_all_admins() -> list[User]:
    """Получить всех администраторов"""
    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.is_admin == True)
        )
        return list(result.scalars().all())


async def get_all_servers() -> list[Server]:
    """Получить все серверы с загруженными локациями"""
    async with async_session() as session:
        result = await session.execute(
            select(Server)
            .options(joinedload(Server.location))
            .order_by(Server.id)
        )
        return list(result.unique().scalars().all())


def generate_subscription_link(server: Server, sub_id: str) -> str:
    """
    Генерирует ссылку на подписку на основе настроек сервера
    
    Args:
        server: Объект сервера
        sub_id: ID подписки (sub_id)
    
    Returns:
        Ссылка на подписку в формате {sub_url}/{sub_id} или http://{server_ip}:2096/sub/{sub_id}
    """
    if server.sub_url:
        # Используем кастомный sub_url из настроек сервера
        sub_url = server.sub_url.rstrip('/')
        return f"{sub_url}/{sub_id}"
    else:
        # Используем старый формат: извлекаем IP из api_url
        from urllib.parse import urlparse
        try:
            parsed_url = urlparse(server.api_url)
            server_ip = parsed_url.hostname or parsed_url.netloc.split(':')[0]
        except:
            server_ip = "vpn-x3.ru"  # Fallback
        return f"http://{server_ip}:2096/sub/{sub_id}"


async def get_server_by_id(server_id: int, use_cache: bool = True) -> Optional[Server]:
    """Получить сервер по ID с загруженной локацией"""
    # Кэширование не используется для объектов ORM - всегда загружаем из БД
    # но используем joinedload для оптимизации (один запрос вместо двух)
    async with async_session() as session:
        result = await session.execute(
            select(Server)
            .options(joinedload(Server.location))
            .where(Server.id == server_id)
        )
        return result.unique().scalar_one_or_none()


async def create_server(
    name: str,
    api_url: str,
    api_username: str,
    api_password: str,
    location_id: int,
    description: str = None,
    max_users: int = None,
    ssl_certificate: str = None,
    payment_days: int = None,
    sub_url: str = None
) -> Server:
    """
    Создать новый сервер
    
    Args:
        name: Название сервера
        api_url: Полный URL панели управления 3x-ui (например, http://89.169.7.60:30648/rolDT4Th57aiCxNzOi)
        api_username: Имя пользователя для входа в панель
        api_password: Пароль для входа в панель
        location_id: ID локации
        description: Описание сервера (опционально)
        max_users: Максимальное количество пользователей (опционально)
        ssl_certificate: SSL сертификат в формате PEM (опционально)
        payment_days: Количество дней, на которое куплен сервер (опционально)
        sub_url: URL шаблон для генерации ссылок подписки (формат: {sub_url}/{subID}, опционально)
    """
    from datetime import datetime, timedelta
    
    payment_expire_date = None
    if payment_days and payment_days > 0:
        payment_expire_date = datetime.utcnow() + timedelta(days=payment_days)
    
    async with async_session() as session:
        server = Server(
            name=name,
            api_url=api_url,
            api_username=api_username,
            api_password=api_password,
            location_id=location_id,
            description=description,
            max_users=max_users,
            ssl_certificate=ssl_certificate,
            payment_days=payment_days,
            payment_expire_date=payment_expire_date,
            sub_url=sub_url
        )
        session.add(server)
        await session.commit()
        await session.refresh(server)
        
        return server


async def update_server(server_id: int, **kwargs) -> Optional[Server]:
    """Обновить данные сервера
    
    Args:
        server_id: ID сервера
        **kwargs: Поля для обновления. Можно передать None для nullable полей (location, description, max_users).
    
    Returns:
        Обновленный сервер или None если не найден
    """
    async with async_session() as session:
        result = await session.execute(select(Server).where(Server.id == server_id))
        server = result.scalar_one_or_none()
        if not server:
            return None
        
        # Сохраняем старые значения критичных полей для отслеживания изменений
        old_location_id = server.location_id
        old_api_url = server.api_url
        old_api_username = server.api_username
        old_api_password = server.api_password
        
        # Список полей, которые можно установить в None
        nullable_fields = {'description', 'max_users', 'ssl_certificate', 'payment_days', 'payment_expire_date'}
        
        # Список критичных полей, изменение которых требует уведомления
        critical_fields = {'api_url', 'api_username', 'api_password', 'location_id'}
        changed_critical_fields = []
        
        for key, value in kwargs.items():
            if hasattr(server, key):
                # Проверяем, изменилось ли критичное поле
                if key in critical_fields:
                    old_value = getattr(server, key)
                    # Для location_id сравниваем с сохраненным значением
                    if key == 'location_id':
                        old_value = old_location_id
                    
                    # Проверяем, действительно ли значение изменилось
                    if old_value != value:
                        # Для nullable полей проверяем, что новое значение не None (или старое было не None)
                        if key in nullable_fields:
                            if old_value != value and (value is not None or old_value is not None):
                                changed_critical_fields.append(key)
                        else:
                            # Для не-nullable полей сравниваем значения
                            if old_value != value and value is not None:
                                changed_critical_fields.append(key)
                
                # Для nullable полей разрешаем устанавливать None
                if key in nullable_fields:
                    setattr(server, key, value)
                # Для не-nullable полей устанавливаем только если значение не None
                elif value is not None:
                    setattr(server, key, value)
        
        await session.commit()
        await session.refresh(server)
        
        # Если были изменены критичные поля, отправляем уведомления пользователям
        if changed_critical_fields:
            # Отправляем уведомления асинхронно (не блокируя ответ)
            try:
                from services.server_notifications import notify_users_about_server_changes
                import asyncio
                
                # Если изменилась локация, уведомляем пользователей обеих локаций
                if 'location_id' in changed_critical_fields:
                    # Уведомляем пользователей старой локации
                    asyncio.create_task(
                        notify_users_about_server_changes(
                            server_id=server_id,
                            location_id=old_location_id,
                            changed_fields=changed_critical_fields
                        )
                    )
                    # Уведомляем пользователей новой локации
                    asyncio.create_task(
                        notify_users_about_server_changes(
                            server_id=server_id,
                            location_id=server.location_id,
                            changed_fields=changed_critical_fields
                        )
                    )
                else:
                    # Используем текущую location_id
                    asyncio.create_task(
                        notify_users_about_server_changes(
                            server_id=server_id,
                            location_id=server.location_id,
                            changed_fields=changed_critical_fields
                        )
                    )
            except Exception as e:
                import logging
                logger = logging.getLogger(__name__)
                logger.error(f"❌ Ошибка при отправке уведомлений об изменениях сервера {server_id}: {e}")
        
        return server


async def delete_server(server_id: int) -> bool:
    """
    Удалить сервер
    
    Перед удалением сервера:
    1. Устанавливает server_id = NULL для всех связанных payments
    2. Проверяет наличие активных subscriptions - если есть, возвращает False
    
    Args:
        server_id: ID сервера для удаления
        
    Returns:
        True если сервер успешно удален, False если есть активные подписки или сервер не найден
    """
    async with async_session() as session:
        result = await session.execute(select(Server).where(Server.id == server_id))
        server = result.scalar_one_or_none()
        if not server:
            return False
        
        # Проверяем наличие активных подписок
        subscriptions_result = await session.execute(
            select(Subscription).where(
                and_(
                    Subscription.server_id == server_id,
                    Subscription.status == "active"
                )
            )
        )
        active_subscriptions = subscriptions_result.scalars().all()
        
        if active_subscriptions:
            # Есть активные подписки - нельзя удалить сервер
            return False
        
        # Устанавливаем server_id = NULL для всех связанных payments
        from database.models import Payment
        from sqlalchemy import update
        await session.execute(
            update(Payment)
            .where(Payment.server_id == server_id)
            .values(server_id=None)
        )
        
        # Удаляем сервер
        await session.delete(server)
        await session.commit()
        return True


async def set_admin(tg_id: str, is_admin: bool = True) -> Optional[User]:
    """Установить статус администратора для пользователя"""
    async with async_session() as session:
        result = await session.execute(select(User).where(User.tg_id == str(tg_id)))
        user = result.scalar_one_or_none()
        if not user:
            return None
        
        user.is_admin = is_admin
        await session.commit()
        await session.refresh(user)
        return user


async def get_all_users() -> list[User]:
    """Получить всех пользователей"""
    async with async_session() as session:
        result = await session.execute(select(User).order_by(User.created_at.desc()))
        return list(result.scalars().all())


async def get_user_by_id(user_id: int) -> Optional[User]:
    """Получить пользователя по ID"""
    async with async_session() as session:
        result = await session.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()


async def update_user(user_id: int, **kwargs) -> Optional[User]:
    """Обновить данные пользователя"""
    async with async_session() as session:
        result = await session.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if not user:
            return None
        
        for key, value in kwargs.items():
            if hasattr(user, key) and value is not None:
                setattr(user, key, value)
        
        await session.commit()
        await session.refresh(user)
        return user


async def update_user_email(tg_id: str, email: str) -> Optional[User]:
    """Обновить email пользователя по tg_id"""
    async with async_session() as session:
        result = await session.execute(select(User).where(User.tg_id == str(tg_id)))
        user = result.scalar_one_or_none()
        if not user:
            return None
        
        user.email = email
        await session.commit()
        await session.refresh(user)
        return user


async def get_users_count() -> int:
    """Получить общее количество пользователей"""
    async with async_session() as session:
        result = await session.execute(select(func.count(User.id)))
        return result.scalar() or 0


async def get_active_users_count() -> int:
    """Получить количество активных пользователей"""
    async with async_session() as session:
        result = await session.execute(select(func.count(User.id)).where(User.status == "active"))
        return result.scalar() or 0


async def get_servers_count() -> int:
    """Получить общее количество серверов"""
    async with async_session() as session:
        result = await session.execute(select(func.count(Server.id)))
        return result.scalar() or 0


async def get_active_servers_count() -> int:
    """Получить количество активных серверов"""
    async with async_session() as session:
        result = await session.execute(select(func.count(Server.id)).where(Server.is_active == True))
        return result.scalar() or 0


async def get_payments_count() -> int:
    """Получить общее количество платежей"""
    async with async_session() as session:
        result = await session.execute(select(func.count(Payment.id)))
        return result.scalar() or 0


async def get_paid_payments_count() -> int:
    """Получить количество успешных платежей"""
    async with async_session() as session:
        result = await session.execute(select(func.count(Payment.id)).where(Payment.status == "paid"))
        return result.scalar() or 0


async def get_total_revenue() -> float:
    """Получить общую выручку (сумма всех успешных платежей)"""
    async with async_session() as session:
        result = await session.execute(
            select(func.sum(Payment.amount)).where(Payment.status == "paid")
        )
        total = result.scalar()
        return float(total) if total else 0.0


async def get_revenue_by_period(start_date: datetime, end_date: datetime = None) -> float:
    """Получить выручку за период"""
    if end_date is None:
        end_date = datetime.utcnow()
    async with async_session() as session:
        # Используем paid_at для точной даты оплаты, если NULL - используем created_at
        result = await session.execute(
            select(func.sum(Payment.amount)).where(
                and_(
                    Payment.status == "paid",
                    or_(
                        and_(Payment.paid_at.isnot(None), Payment.paid_at >= start_date, Payment.paid_at <= end_date),
                        and_(Payment.paid_at.is_(None), Payment.created_at >= start_date, Payment.created_at <= end_date)
                    )
                )
            )
        )
        total = result.scalar()
        return float(total) if total else 0.0


async def get_subscriptions_count_by_status(status: str) -> int:
    """Получить количество подписок по статусу"""
    async with async_session() as session:
        result = await session.execute(
            select(func.count(Subscription.id)).where(Subscription.status == status)
        )
        return result.scalar() or 0


async def get_users_with_active_subscriptions_count() -> int:
    """Получить количество уникальных пользователей с активными подписками"""
    async with async_session() as session:
        result = await session.execute(
            select(func.count(func.distinct(Subscription.user_id))).where(
                Subscription.status == "active"
            )
        )
        return result.scalar() or 0


async def get_paid_payments_count_by_period(start_date: datetime, end_date: datetime = None) -> int:
    """Получить количество успешных платежей за период"""
    if end_date is None:
        end_date = datetime.utcnow()
    async with async_session() as session:
        # Используем paid_at для точной даты оплаты, если NULL - используем created_at
        result = await session.execute(
            select(func.count(Payment.id)).where(
                and_(
                    Payment.status == "paid",
                    or_(
                        and_(Payment.paid_at.isnot(None), Payment.paid_at >= start_date, Payment.paid_at <= end_date),
                        and_(Payment.paid_at.is_(None), Payment.created_at >= start_date, Payment.created_at <= end_date)
                    )
                )
            )
        )
        return result.scalar() or 0


async def get_new_users_count_by_period(start_date: datetime, end_date: datetime = None) -> int:
    """Получить количество новых пользователей за период"""
    if end_date is None:
        end_date = datetime.utcnow()
    async with async_session() as session:
        result = await session.execute(
            select(func.count(User.id)).where(
                and_(
                    User.created_at >= start_date,
                    User.created_at <= end_date
                )
            )
        )
        return result.scalar() or 0


async def has_user_made_purchase(user_id: int) -> bool:
    """Проверить, делал ли пользователь успешные покупки"""
    async with async_session() as session:
        # Используем EXISTS для оптимизации - не загружаем все подписки
        result = await session.execute(
            select(func.count(Subscription.id)).where(Subscription.user_id == user_id).limit(1)
        )
        count = result.scalar() or 0
        return count > 0


async def mark_user_used_discount(user_id: int) -> bool:
    """Отметить, что пользователь использовал скидку на первую покупку"""
    async with async_session() as session:
        result = await session.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if not user:
            return False
        
        user.used_first_purchase_discount = True
        await session.commit()
        await session.refresh(user)
        return True


async def get_all_active_subscriptions() -> List[Subscription]:
    """Получить все активные подписки с предзагрузкой связанных данных (оптимизация N+1)
    Включает приватные подписки, но они будут пропущены в checker"""
    async with async_session() as session:
        result = await session.execute(
            select(Subscription)
            .options(joinedload(Subscription.server).joinedload(Server.location))
            .where(Subscription.status == "active")
        )
        return list(result.unique().scalars().all())


async def get_all_expired_subscriptions() -> List[Subscription]:
    """Получить все истекшие подписки с предзагрузкой связанных данных (оптимизация N+1)
    Исключает приватные (бессрочные) подписки - они не должны истекать"""
    async with async_session() as session:
        result = await session.execute(
            select(Subscription)
            .options(joinedload(Subscription.server).joinedload(Server.location))
            .where(
                and_(
                    Subscription.status == "expired",
                    Subscription.is_private == False  # Исключаем бессрочные подписки
                )
            )
        )
        return list(result.unique().scalars().all())


async def check_and_block_expired_subscriptions() -> int:
    """Проверить и заблокировать истекшие подписки. Возвращает количество заблокированных.
    Бессрочные (приватные) подписки не проверяются и не блокируются."""
    from datetime import datetime
    blocked_count = 0
    
    async with async_session() as session:
        # Получаем все активные подписки, исключая бессрочные (приватные)
        result = await session.execute(
            select(Subscription).where(
                and_(
                    Subscription.status == "active",
                    Subscription.is_private == False  # Исключаем бессрочные подписки
                )
            )
        )
        subscriptions = result.scalars().all()
        
        current_time = datetime.utcnow()
        
        for subscription in subscriptions:
            # Проверяем только подписки с датой истечения
            if subscription.expire_date and subscription.expire_date < current_time:
                subscription.status = "expired"
                blocked_count += 1
        
        if blocked_count > 0:
            await session.commit()
    
    return blocked_count


# Функции для работы с подписками
async def create_subscription(
    user_id: int,
    server_id: int,
    tariff_id: int,
    x3ui_client_id: str = None,
    x3ui_client_email: str = None,
    sub_id: str = None,
    location_unique_name: str = None,
    status: str = "active",
    expire_date = None,
    traffic_limit: float = 0.0,
    is_private: bool = False
) -> Subscription:
    """Создать новую подписку"""
    async with async_session() as session:
        subscription = Subscription(
            user_id=user_id,
            server_id=server_id,
            tariff_id=tariff_id,
            x3ui_client_id=x3ui_client_id,
            x3ui_client_email=x3ui_client_email,
            sub_id=sub_id,
            location_unique_name=location_unique_name,
            status=status,
            expire_date=expire_date,
            traffic_limit=traffic_limit,
            is_private=is_private
        )
        session.add(subscription)
        await session.commit()
        await session.refresh(subscription)
        return subscription


async def get_user_subscriptions(user_id: int) -> List[Subscription]:
    """Получить все подписки пользователя с предзагрузкой связанных данных (оптимизация N+1)"""
    async with async_session() as session:
        result = await session.execute(
            select(Subscription)
            .options(joinedload(Subscription.server).joinedload(Server.location))
            .where(Subscription.user_id == user_id)
            .order_by(Subscription.created_at.desc())
        )
        return list(result.unique().scalars().all())


async def get_subscription_by_id(subscription_id: int) -> Optional[Subscription]:
    """Получить подписку по ID с предзагрузкой связанных данных (оптимизация N+1)"""
    async with async_session() as session:
        result = await session.execute(
            select(Subscription)
            .options(joinedload(Subscription.server).joinedload(Server.location))
            .where(Subscription.id == subscription_id)
        )
        return result.unique().scalar_one_or_none()


async def get_user_subscriptions_by_server(user_id: int, server_id: int) -> List[Subscription]:
    """Получить все подписки пользователя на конкретном сервере"""
    async with async_session() as session:
        result = await session.execute(
            select(Subscription)
            .where(Subscription.user_id == user_id)
            .where(Subscription.server_id == server_id)
            .order_by(Subscription.created_at.desc())
        )
        return list(result.scalars().all())


async def update_subscription(subscription_id: int, **kwargs) -> Optional[Subscription]:
    """Обновить данные подписки"""
    async with async_session() as session:
        result = await session.execute(
            select(Subscription).where(Subscription.id == subscription_id)
        )
        subscription = result.scalar_one_or_none()
        if not subscription:
            return None
        
        for key, value in kwargs.items():
            if hasattr(subscription, key):
                setattr(subscription, key, value)
        
        await session.commit()
        await session.refresh(subscription)
        return subscription


async def delete_subscription(subscription_id: int) -> bool:
    """Удалить подписку"""
    async with async_session() as session:
        result = await session.execute(
            select(Subscription).where(Subscription.id == subscription_id)
        )
        subscription = result.scalar_one_or_none()
        if not subscription:
            return False
        
        await session.delete(subscription)
        await session.commit()
        return True


async def delete_all_user_subscriptions(user_id: int) -> int:
    """
    Удалить все подписки пользователя из базы данных
    
    Args:
        user_id: ID пользователя
        
    Returns:
        Количество удаленных подписок
    """
    async with async_session() as session:
        result = await session.execute(
            select(Subscription).where(Subscription.user_id == user_id)
        )
        subscriptions = list(result.scalars().all())
        
        if not subscriptions:
            return 0
        
        for subscription in subscriptions:
            await session.delete(subscription)
        
        await session.commit()
        return len(subscriptions)


async def get_subscriptions_older_than_days(days: int) -> List[Subscription]:
    """
    Получить подписки, которые не продлевались более указанного количества дней
    
    Args:
        days: Количество дней
        
    Returns:
        Список подписок, у которых expire_date старше указанного количества дней
    """
    return await get_subscriptions_older_than(timedelta(days=days))


async def get_subscriptions_older_than(time_delta: timedelta) -> List[Subscription]:
    """
    Получить подписки, которые не продлевались более указанного времени
    
    Args:
        time_delta: Интервал времени (timedelta)
        
    Returns:
        Список подписок, у которых expire_date старше указанного времени
    """
    async with async_session() as session:
        cutoff_date = datetime.utcnow() - time_delta
        result = await session.execute(
            select(Subscription).where(
                and_(
                    Subscription.expire_date.isnot(None),
                    Subscription.expire_date < cutoff_date
                )
            )
        )
        return list(result.scalars().all())


# Функции для работы с платежами
async def create_payment(
    tg_id: str,
    amount: float,
    server_id: int,
    tariff_id: Optional[int] = None,
    yookassa_payment_id: Optional[str] = None,
    currency: str = "RUB"
) -> Payment:
    """Создать новый платеж"""
    async with async_session() as session:
        payment = Payment(
            tg_id=tg_id,
            amount=amount,
            currency=currency,
            server_id=server_id,
            tariff_id=tariff_id,
            yookassa_payment_id=yookassa_payment_id,
            status="pending"
        )
        session.add(payment)
        await session.commit()
        await session.refresh(payment)
        return payment


async def get_payment_by_yookassa_id(yookassa_payment_id: str) -> Optional[Payment]:
    """Получить платеж по ID YooKassa"""
    async with async_session() as session:
        result = await session.execute(
            select(Payment).where(Payment.yookassa_payment_id == yookassa_payment_id)
        )
        return result.scalar_one_or_none()


async def update_payment_status(
    payment_id: int,
    status: str,
    paid_at: Optional[datetime] = None
) -> Optional[Payment]:
    """Обновить статус платежа"""
    async with async_session() as session:
        result = await session.execute(
            select(Payment).where(Payment.id == payment_id)
        )
        payment = result.scalar_one_or_none()
        if not payment:
            return None
        
        payment.status = status
        if paid_at:
            payment.paid_at = paid_at
        elif status == "paid":
            payment.paid_at = datetime.utcnow()
        
        await session.commit()
        await session.refresh(payment)
        return payment


async def get_tariff_by_id(tariff_id: int, use_cache: bool = True) -> Optional[Tariff]:
    """Получить тариф по ID"""
    async with async_session() as session:
        result = await session.execute(
            select(Tariff).where(Tariff.id == tariff_id)
        )
        return result.scalar_one_or_none()


def generate_test_key() -> str:
    """Генерирует тестовый ключ для подписки"""
    import random
    import string
    # Генерируем случайный ключ в формате vless://...
    chars = string.ascii_letters + string.digits
    key_id = ''.join(random.choices(chars, k=16))
    return f"vless://test-{key_id}@test-server:443?encryption=none&security=none&type=tcp#test-key"


# Функции для работы с локациями
async def create_location(
    name: str,
    price: float,
    description: str = None
) -> Location:
    """Создать новую локацию"""
    async with async_session() as session:
        location = Location(
            name=name,
            price=price,
            description=description,
            is_active=True
        )
        session.add(location)
        await session.commit()
        await session.refresh(location)
        return location


async def get_all_locations() -> List[Location]:
    """Получить все локации"""
    async with async_session() as session:
        result = await session.execute(select(Location).order_by(Location.name))
        return list(result.scalars().all())


async def get_active_locations(use_cache: bool = True) -> List[Location]:
    """Получить только активные и не скрытые локации"""
    # Кэширование не используется для объектов ORM - всегда загружаем из БД
    # Локации меняются редко, но для консистентности всегда загружаем свежие данные
    async with async_session() as session:
        result = await session.execute(
            select(Location).where(
                and_(
                    Location.is_active == True,
                    Location.is_hidden == False
                )
            ).order_by(Location.name)
        )
        return list(result.scalars().all())


async def get_location_by_id(location_id: int, use_cache: bool = True) -> Optional[Location]:
    """Получить локацию по ID"""
    async with async_session() as session:
        result = await session.execute(select(Location).where(Location.id == location_id))
        return result.scalar_one_or_none()


async def get_location_by_name(name: str) -> Optional[Location]:
    """Получить локацию по названию"""
    async with async_session() as session:
        result = await session.execute(select(Location).where(Location.name == name))
        return result.scalar_one_or_none()


async def update_location(location_id: int, **kwargs) -> Optional[Location]:
    """Обновить данные локации"""
    async with async_session() as session:
        result = await session.execute(select(Location).where(Location.id == location_id))
        location = result.scalar_one_or_none()
        if not location:
            return None
        
        for key, value in kwargs.items():
            if hasattr(location, key) and value is not None:
                setattr(location, key, value)
        
        location.updated_at = datetime.utcnow()
        await session.commit()
        await session.refresh(location)
        return location


async def delete_location(location_id: int) -> bool:
    """Удалить локацию"""
    async with async_session() as session:
        result = await session.execute(select(Location).where(Location.id == location_id))
        location = result.scalar_one_or_none()
        if not location:
            return False
        
        # Проверяем, есть ли серверы, привязанные к этой локации
        servers_result = await session.execute(
            select(Server).where(Server.location_id == location_id)
        )
        servers = list(servers_result.scalars().all())
        if servers:
            # Не удаляем локацию, если к ней привязаны серверы
            return False
        
        await session.delete(location)
        await session.commit()
        return True


async def get_servers_by_location(location_id: int) -> List[Server]:
    """Получить все серверы для локации с загруженными локациями"""
    async with async_session() as session:
        result = await session.execute(
            select(Server)
            .options(joinedload(Server.location))
            .where(Server.location_id == location_id)
            .order_by(Server.id)
        )
        return list(result.unique().scalars().all())


async def get_active_servers_by_location(location_id: int, use_cache: bool = True) -> List[Server]:
    """Получить только активные серверы для локации с загруженными локациями"""
    # Используем joinedload для оптимизации - один запрос вместо N+1
    async with async_session() as session:
        result = await session.execute(
            select(Server)
            .options(joinedload(Server.location))
            .where(
                and_(Server.location_id == location_id, Server.is_active == True)
            )
            .order_by(Server.id)
        )
        return list(result.unique().scalars().all())


async def count_active_subscriptions_by_server(server_id: int) -> int:
    """Подсчитать количество активных подписок на сервере"""
    async with async_session() as session:
        result = await session.execute(
            select(func.count(Subscription.id)).where(
                and_(
                    Subscription.server_id == server_id,
                    Subscription.status == "active"
                )
            )
        )
        return result.scalar() or 0


async def has_available_server_for_location(location_id: int) -> bool:
    """
    Проверить, есть ли хотя бы один доступный сервер в локации.
    Сервер считается доступным, если он активен и не переполнен (current_users < max_users).
    Если max_users не установлен (None), сервер всегда доступен.
    
    Returns:
        True если есть хотя бы один доступный сервер, False иначе
    """
    servers = await get_active_servers_by_location(location_id)
    
    if not servers:
        return False
    
    for server in servers:
        active_count = await count_active_subscriptions_by_server(server.id)
        
        # Если max_users не установлен (None), считаем сервер доступным
        if server.max_users is None:
            return True
        elif active_count < server.max_users:
            return True
    
    return False


async def select_available_server_for_location(location_id: int) -> Optional[Server]:
    """
    Автоматически выбрать доступный сервер из локации.
    Выбирает сервер с наименьшей загрузкой (current_users < max_users).
    Если все серверы заполнены, возвращает None.
    """
    servers = await get_active_servers_by_location(location_id)
    
    if not servers:
        return None
    
    # Сортируем серверы по загрузке (сначала те, где больше свободных мест)
    available_servers = []
    for server in servers:
        active_count = await count_active_subscriptions_by_server(server.id)
        
        # Если max_users не установлен (None), считаем сервер доступным
        if server.max_users is None:
            available_servers.append((server, float('inf')))  # Бесконечная вместимость
        elif active_count < server.max_users:
            available_servers.append((server, server.max_users - active_count))
    
    if not available_servers:
        return None
    
    # Сортируем по количеству свободных мест (по убыванию)
    available_servers.sort(key=lambda x: x[1], reverse=True)
    
    # Возвращаем сервер с наибольшим количеством свободных мест
    return available_servers[0][0]


async def update_server_current_users(server_id: int):
    """Обновить счетчик текущих пользователей на сервере"""
    async with async_session() as session:
        result = await session.execute(select(Server).where(Server.id == server_id))
        server = result.scalar_one_or_none()
        if not server:
            return
        
        active_count = await count_active_subscriptions_by_server(server_id)
        server.current_users = active_count
        server.updated_at = datetime.utcnow()
        await session.commit()
    
    # Проверяем загрузку сервера и отправляем уведомления админам при необходимости
    try:
        from services.server_load_checker import check_server_load
        await check_server_load(server_id)
    except Exception as e:
        # Логируем ошибку, но не прерываем выполнение
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Ошибка при проверке загрузки сервера {server_id}: {e}")


async def get_users_with_active_subscriptions_by_location(location_id: int) -> List[User]:
    """Получить всех пользователей с активными подписками на сервера в указанной локации
    
    Args:
        location_id: ID локации
        
    Returns:
        Список уникальных пользователей с активными подписками на сервера в локации
    """
    async with async_session() as session:
        result = await session.execute(
            select(User)
            .join(Subscription, User.id == Subscription.user_id)
            .join(Server, Subscription.server_id == Server.id)
            .where(
                and_(
                    Server.location_id == location_id,
                    Subscription.status == "active"
                )
            )
            .distinct()
        )
        return list(result.scalars().all())


async def get_users_with_subscriptions_by_server(server_id: int) -> List[User]:
    """Получить всех пользователей с подписками на указанном сервере
    
    Args:
        server_id: ID сервера
        
    Returns:
        Список уникальных пользователей с подписками на сервере (любого статуса)
    """
    async with async_session() as session:
        result = await session.execute(
            select(User)
            .join(Subscription, User.id == Subscription.user_id)
            .where(Subscription.server_id == server_id)
            .distinct()
        )
        return list(result.scalars().all())


async def get_subscriptions_by_location(location_id: int) -> List[Subscription]:
    """Получить все подписки для локации (на всех серверах этой локации)
    
    Args:
        location_id: ID локации
        
    Returns:
        Список всех подписок на серверах в указанной локации (любого статуса)
    """
    async with async_session() as session:
        result = await session.execute(
            select(Subscription)
            .join(Server, Subscription.server_id == Server.id)
            .options(joinedload(Subscription.server).joinedload(Server.location))
            .where(Server.location_id == location_id)
            .order_by(Subscription.created_at.desc())
        )
        return list(result.unique().scalars().all())


async def get_subscriptions_by_server(server_id: int) -> List[Subscription]:
    """Получить все подписки на указанном сервере
    
    Args:
        server_id: ID сервера
        
    Returns:
        Список всех подписок на сервере (любого статуса)
    """
    async with async_session() as session:
        result = await session.execute(
            select(Subscription)
            .options(joinedload(Subscription.server).joinedload(Server.location))
            .options(joinedload(Subscription.user))
            .options(joinedload(Subscription.tariff))
            .where(Subscription.server_id == server_id)
            .order_by(Subscription.created_at.desc())
        )
        return list(result.unique().scalars().all())


# ==================== ПРОМОКОДЫ ====================

async def create_promo_code(code: str, discount_percent: float, max_uses: Optional[int] = None, allow_reuse_by_same_user: bool = False) -> PromoCode:
    """Создать промокод (max_uses=None для безлимитного промокода)"""
    async with async_session() as session:
        promo_code = PromoCode(
            code=code.upper().strip(),
            discount_percent=discount_percent,
            max_uses=max_uses,  # None = безлимитный
            current_uses=0,
            allow_reuse_by_same_user=allow_reuse_by_same_user,
            is_active=True
        )
        session.add(promo_code)
        await session.commit()
        await session.refresh(promo_code)
        return promo_code


async def get_promo_code_by_code(code: str) -> Optional[PromoCode]:
    """Получить промокод по коду"""
    async with async_session() as session:
        result = await session.execute(
            select(PromoCode).where(PromoCode.code == code.upper().strip())
        )
        return result.scalar_one_or_none()


async def get_promo_code_by_id(promo_code_id: int) -> Optional[PromoCode]:
    """Получить промокод по ID"""
    async with async_session() as session:
        result = await session.execute(
            select(PromoCode).where(PromoCode.id == promo_code_id)
        )
        return result.scalar_one_or_none()


async def get_all_promo_codes() -> List[PromoCode]:
    """Получить все промокоды"""
    async with async_session() as session:
        result = await session.execute(
            select(PromoCode).order_by(PromoCode.created_at.desc())
        )
        return list(result.scalars().all())


async def update_promo_code(promo_code_id: int, **kwargs) -> Optional[PromoCode]:
    """Обновить промокод"""
    async with async_session() as session:
        result = await session.execute(
            select(PromoCode).where(PromoCode.id == promo_code_id)
        )
        promo_code = result.scalar_one_or_none()
        if not promo_code:
            return None
        
        for key, value in kwargs.items():
            if hasattr(promo_code, key):
                setattr(promo_code, key, value)
        
        promo_code.updated_at = datetime.utcnow()
        await session.commit()
        await session.refresh(promo_code)
        return promo_code


async def delete_promo_code(promo_code_id: int) -> bool:
    """Удалить промокод"""
    async with async_session() as session:
        result = await session.execute(
            select(PromoCode).where(PromoCode.id == promo_code_id)
        )
        promo_code = result.scalar_one_or_none()
        if not promo_code:
            return False
        
        await session.delete(promo_code)
        await session.commit()
        return True


async def can_use_promo_code(promo_code: PromoCode, user_id: int) -> tuple[bool, str]:
    """
    Проверить, может ли пользователь использовать промокод
    Возвращает (может_использовать, сообщение_об_ошибке)
    """
    if not promo_code.is_active:
        return False, "Промокод неактивен"
    
    # Проверяем лимит только если промокод не безлимитный
    if promo_code.max_uses is not None and promo_code.current_uses >= promo_code.max_uses:
        return False, "Промокод исчерпан"
    
    # Проверяем, использовал ли пользователь уже этот промокод (только если не разрешено повторное использование)
    if not promo_code.allow_reuse_by_same_user:
        async with async_session() as session:
            result = await session.execute(
                select(PromoCodeUsage).where(
                    and_(
                        PromoCodeUsage.promo_code_id == promo_code.id,
                        PromoCodeUsage.user_id == user_id
                    )
                )
            )
            usage = result.scalar_one_or_none()
            if usage:
                return False, "Вы уже использовали этот промокод"
    
    return True, ""


async def use_promo_code(promo_code_id: int, user_id: int, payment_id: int = None) -> Optional[PromoCodeUsage]:
    """Использовать промокод (увеличить счетчик использований и создать запись)"""
    async with async_session() as session:
        # Получаем промокод
        result = await session.execute(
            select(PromoCode).where(PromoCode.id == promo_code_id)
        )
        promo_code = result.scalar_one_or_none()
        if not promo_code:
            return None
        
        # Увеличиваем счетчик использований
        promo_code.current_uses += 1
        promo_code.updated_at = datetime.utcnow()
        
        # Создаем запись об использовании
        usage = PromoCodeUsage(
            promo_code_id=promo_code_id,
            user_id=user_id,
            payment_id=payment_id
        )
        session.add(usage)
        
        await session.commit()
        await session.refresh(usage)
        return usage


async def has_user_used_promo_code(user_id: int, promo_code_id: int) -> bool:
    """Проверить, использовал ли пользователь промокод"""
    async with async_session() as session:
        result = await session.execute(
            select(PromoCodeUsage).where(
                and_(
                    PromoCodeUsage.user_id == user_id,
                    PromoCodeUsage.promo_code_id == promo_code_id
                )
            )
        )
        return result.scalar_one_or_none() is not None


# ==================== ПОДДЕРЖКА ====================

# Константы для ограничений
MAX_MESSAGE_LENGTH = 4000  # Максимальная длина сообщения (символов)
MAX_PHOTO_SIZE_MB = 10  # Максимальный размер изображения (МБ)

async def create_support_ticket(user_id: int, message: str, photo_file_id: str = None) -> SupportTicket:
    """Создать новый тикет поддержки
    
    Args:
        user_id: ID пользователя
        message: Текст сообщения
        photo_file_id: file_id изображения в Telegram (опционально)
    """
    async with async_session() as session:
        ticket = SupportTicket(
            user_id=user_id,
            message=message,
            photo_file_id=photo_file_id,
            status="open"
        )
        session.add(ticket)
        await session.commit()
        await session.refresh(ticket)
        return ticket


async def get_support_ticket_by_id(ticket_id: int) -> Optional[SupportTicket]:
    """Получить тикет по ID"""
    async with async_session() as session:
        result = await session.execute(
            select(SupportTicket)
            .options(joinedload(SupportTicket.user))
            .where(SupportTicket.id == ticket_id)
        )
        return result.unique().scalar_one_or_none()


async def get_user_support_tickets(user_id: int) -> List[SupportTicket]:
    """Получить все тикеты пользователя"""
    async with async_session() as session:
        result = await session.execute(
            select(SupportTicket)
            .where(SupportTicket.user_id == user_id)
            .order_by(SupportTicket.created_at.desc())
        )
        return list(result.scalars().all())


async def get_all_support_tickets() -> List[SupportTicket]:
    """Получить все тикеты (для админов)"""
    async with async_session() as session:
        result = await session.execute(
            select(SupportTicket)
            .options(joinedload(SupportTicket.user))
            .order_by(SupportTicket.created_at.desc())
        )
        return list(result.unique().scalars().all())


async def get_open_support_tickets() -> List[SupportTicket]:
    """Получить все открытые тикеты (для админов)"""
    async with async_session() as session:
        result = await session.execute(
            select(SupportTicket)
            .options(joinedload(SupportTicket.user))
            .where(SupportTicket.status == "open")
            .order_by(SupportTicket.created_at.desc())
        )
        return list(result.unique().scalars().all())


async def update_support_ticket(ticket_id: int, **kwargs) -> Optional[SupportTicket]:
    """Обновить данные тикета"""
    async with async_session() as session:
        result = await session.execute(
            select(SupportTicket).where(SupportTicket.id == ticket_id)
        )
        ticket = result.scalar_one_or_none()
        if not ticket:
            return None
        
        for key, value in kwargs.items():
            if hasattr(ticket, key) and value is not None:
                setattr(ticket, key, value)
        
        ticket.updated_at = datetime.utcnow()
        await session.commit()
        await session.refresh(ticket)
        return ticket


async def answer_support_ticket(ticket_id: int, admin_response: str) -> Optional[SupportTicket]:
    """Получить данные тикета перед удалением (для отправки уведомления)"""
    async with async_session() as session:
        result = await session.execute(
            select(SupportTicket)
            .options(joinedload(SupportTicket.user))
            .where(SupportTicket.id == ticket_id)
        )
        ticket = result.unique().scalar_one_or_none()
        if not ticket:
            return None
        
        # Возвращаем объект для использования в уведомлении
        # Тикет будет удален сразу после этого, поэтому не сохраняем изменения
        return ticket


async def delete_support_ticket(ticket_id: int) -> bool:
    """Удалить тикет поддержки из базы данных"""
    async with async_session() as session:
        result = await session.execute(
            select(SupportTicket).where(SupportTicket.id == ticket_id)
        )
        ticket = result.scalar_one_or_none()
        if not ticket:
            return False
        
        await session.delete(ticket)
        await session.commit()
        return True


# ========== Функции для работы с платформами и туториалами ==========

async def get_all_platforms() -> List[Platform]:
    """Получить все платформы"""
    async with async_session() as session:
        result = await session.execute(
            select(Platform)
            .order_by(Platform.order, Platform.id)
        )
        return list(result.scalars().all())


async def get_active_platforms() -> List[Platform]:
    """Получить все активные платформы"""
    async with async_session() as session:
        result = await session.execute(
            select(Platform)
            .where(Platform.is_active == True)
            .order_by(Platform.order, Platform.id)
        )
        return list(result.scalars().all())


async def get_platform_by_id(platform_id: int) -> Optional[Platform]:
    """Получить платформу по ID"""
    async with async_session() as session:
        result = await session.execute(
            select(Platform).where(Platform.id == platform_id)
        )
        return result.scalar_one_or_none()


async def get_platform_by_name(name: str) -> Optional[Platform]:
    """Получить платформу по имени"""
    async with async_session() as session:
        result = await session.execute(
            select(Platform).where(Platform.name == name)
        )
        return result.scalar_one_or_none()


async def create_platform(name: str, display_name: str, description: str = None, is_active: bool = True, order: int = 0) -> Platform:
    """Создать новую платформу"""
    async with async_session() as session:
        platform = Platform(
            name=name,
            display_name=display_name,
            description=description,
            is_active=is_active,
            order=order
        )
        session.add(platform)
        await session.commit()
        await session.refresh(platform)
        return platform


async def update_platform(platform_id: int, **kwargs) -> Optional[Platform]:
    """Обновить данные платформы"""
    async with async_session() as session:
        result = await session.execute(
            select(Platform).where(Platform.id == platform_id)
        )
        platform = result.scalar_one_or_none()
        if not platform:
            return None
        
        for key, value in kwargs.items():
            if hasattr(platform, key) and value is not None:
                setattr(platform, key, value)
        
        platform.updated_at = datetime.utcnow()
        await session.commit()
        await session.refresh(platform)
        return platform


async def delete_platform(platform_id: int) -> bool:
    """Удалить платформу (каскадно удалит все туториалы и файлы)"""
    async with async_session() as session:
        result = await session.execute(
            select(Platform).where(Platform.id == platform_id)
        )
        platform = result.scalar_one_or_none()
        if not platform:
            return False
        
        await session.delete(platform)
        await session.commit()
        return True


async def get_tutorials_by_platform(platform_id: int, is_basic: bool = None, is_active: bool = True) -> List[Tutorial]:
    """Получить туториалы для платформы"""
    async with async_session() as session:
        query = select(Tutorial).where(Tutorial.platform_id == platform_id)
        
        if is_basic is not None:
            query = query.where(Tutorial.is_basic == is_basic)
        
        if is_active is not None:
            query = query.where(Tutorial.is_active == is_active)
        
        query = query.order_by(Tutorial.order, Tutorial.id)
        
        result = await session.execute(query)
        return list(result.scalars().all())


async def get_tutorial_by_id(tutorial_id: int) -> Optional[Tutorial]:
    """Получить туториал по ID с загруженными файлами"""
    async with async_session() as session:
        result = await session.execute(
            select(Tutorial)
            .options(selectinload(Tutorial.files))
            .where(Tutorial.id == tutorial_id)
        )
        return result.unique().scalar_one_or_none()


async def create_tutorial(
    platform_id: int,
    title: str,
    text: str = None,
    video_file_id: str = None,
    video_note_id: str = None,
    is_basic: bool = True,
    order: int = 0,
    is_active: bool = True
) -> Tutorial:
    """Создать новый туториал"""
    async with async_session() as session:
        tutorial = Tutorial(
            platform_id=platform_id,
            title=title,
            text=text,
            video_file_id=video_file_id,
            video_note_id=video_note_id,
            is_basic=is_basic,
            order=order,
            is_active=is_active
        )
        session.add(tutorial)
        await session.commit()
        await session.refresh(tutorial)
        return tutorial


async def update_tutorial(tutorial_id: int, **kwargs) -> Optional[Tutorial]:
    """Обновить данные туториала"""
    async with async_session() as session:
        result = await session.execute(
            select(Tutorial).where(Tutorial.id == tutorial_id)
        )
        tutorial = result.scalar_one_or_none()
        if not tutorial:
            return None
        
        for key, value in kwargs.items():
            if hasattr(tutorial, key):
                # Разрешаем установку None для очистки полей
                setattr(tutorial, key, value)
        
        tutorial.updated_at = datetime.utcnow()
        await session.commit()
        await session.refresh(tutorial)
        return tutorial


async def delete_tutorial(tutorial_id: int) -> bool:
    """Удалить туториал (каскадно удалит все файлы)"""
    async with async_session() as session:
        result = await session.execute(
            select(Tutorial).where(Tutorial.id == tutorial_id)
        )
        tutorial = result.scalar_one_or_none()
        if not tutorial:
            return False
        
        await session.delete(tutorial)
        await session.commit()
        return True


async def get_tutorial_files(tutorial_id: int) -> List[TutorialFile]:
    """Получить все файлы туториала"""
    async with async_session() as session:
        result = await session.execute(
            select(TutorialFile)
            .where(TutorialFile.tutorial_id == tutorial_id)
            .order_by(TutorialFile.order, TutorialFile.id)
        )
        return list(result.scalars().all())


async def add_tutorial_file(
    tutorial_id: int,
    file_id: str,
    file_name: str = None,
    file_type: str = None,
    description: str = None,
    order: int = 0
) -> TutorialFile:
    """Добавить файл к туториалу"""
    async with async_session() as session:
        tutorial_file = TutorialFile(
            tutorial_id=tutorial_id,
            file_id=file_id,
            file_name=file_name,
            file_type=file_type,
            description=description,
            order=order
        )
        session.add(tutorial_file)
        await session.commit()
        await session.refresh(tutorial_file)
        return tutorial_file


async def delete_tutorial_file(file_id: int) -> bool:
    """Удалить файл туториала"""
    async with async_session() as session:
        result = await session.execute(
            select(TutorialFile).where(TutorialFile.id == file_id)
        )
        tutorial_file = result.scalar_one_or_none()
        if not tutorial_file:
            return False
        
        await session.delete(tutorial_file)
        await session.commit()
        return True


async def get_basic_tutorial_for_platform(platform_id: int) -> Optional[Tutorial]:
    """Получить базовый туториал для платформы"""
    async with async_session() as session:
        result = await session.execute(
            select(Tutorial)
            .options(selectinload(Tutorial.files))
            .where(
                and_(
                    Tutorial.platform_id == platform_id,
                    Tutorial.is_basic == True,
                    Tutorial.is_active == True
                )
            )
            .order_by(Tutorial.order, Tutorial.id)
            .limit(1)
        )
        return result.unique().scalar_one_or_none()


async def get_additional_tutorials_for_platform(platform_id: int) -> List[Tutorial]:
    """Получить дополнительные туториалы для платформы"""
    async with async_session() as session:
        result = await session.execute(
            select(Tutorial)
            .options(selectinload(Tutorial.files))
            .where(
                and_(
                    Tutorial.platform_id == platform_id,
                    Tutorial.is_basic == False,
                    Tutorial.is_active == True
                )
            )
            .order_by(Tutorial.order, Tutorial.id)
        )
        return list(result.unique().scalars().all())


# ========== Функции для работы с документацией админов ==========

async def get_all_documentations() -> List[AdminDocumentation]:
    """Получить все документации"""
    async with async_session() as session:
        result = await session.execute(
            select(AdminDocumentation)
            .order_by(AdminDocumentation.created_at.desc())
        )
        return list(result.scalars().all())


async def get_documentation_by_id(doc_id: int) -> Optional[AdminDocumentation]:
    """Получить документацию по ID с загруженными файлами"""
    async with async_session() as session:
        result = await session.execute(
            select(AdminDocumentation)
            .options(selectinload(AdminDocumentation.files))
            .where(AdminDocumentation.id == doc_id)
        )
        return result.unique().scalar_one_or_none()


async def create_documentation(
    title: str,
    content: str = None,
    created_by: int = None
) -> AdminDocumentation:
    """Создать новую документацию"""
    async with async_session() as session:
        doc = AdminDocumentation(
            title=title,
            content=content,
            created_by=created_by
        )
        session.add(doc)
        await session.commit()
        await session.refresh(doc)
        return doc


async def update_documentation(doc_id: int, **kwargs) -> Optional[AdminDocumentation]:
    """Обновить данные документации"""
    async with async_session() as session:
        result = await session.execute(
            select(AdminDocumentation).where(AdminDocumentation.id == doc_id)
        )
        doc = result.scalar_one_or_none()
        if not doc:
            return None
        
        for key, value in kwargs.items():
            if hasattr(doc, key):
                # Разрешаем установку None для очистки полей
                setattr(doc, key, value)
        
        doc.updated_at = datetime.utcnow()
        await session.commit()
        await session.refresh(doc)
        return doc


async def delete_documentation(doc_id: int) -> bool:
    """Удалить документацию (каскадно удалит все файлы)"""
    async with async_session() as session:
        result = await session.execute(
            select(AdminDocumentation).where(AdminDocumentation.id == doc_id)
        )
        doc = result.scalar_one_or_none()
        if not doc:
            return False
        
        await session.delete(doc)
        await session.commit()
        return True


async def get_documentation_files(doc_id: int) -> List[AdminDocumentationFile]:
    """Получить все файлы документации"""
    async with async_session() as session:
        result = await session.execute(
            select(AdminDocumentationFile)
            .where(AdminDocumentationFile.documentation_id == doc_id)
            .order_by(AdminDocumentationFile.order, AdminDocumentationFile.id)
        )
        return list(result.scalars().all())


async def add_documentation_file(
    documentation_id: int,
    file_id: str,
    file_name: str = None,
    file_type: str = None,
    description: str = None,
    order: int = 0
) -> AdminDocumentationFile:
    """Добавить файл к документации"""
    async with async_session() as session:
        doc_file = AdminDocumentationFile(
            documentation_id=documentation_id,
            file_id=file_id,
            file_name=file_name,
            file_type=file_type,
            description=description,
            order=order
        )
        session.add(doc_file)
        await session.commit()
        await session.refresh(doc_file)
        return doc_file


async def delete_documentation_file(file_id: int) -> bool:
    """Удалить файл документации"""
    async with async_session() as session:
        result = await session.execute(
            select(AdminDocumentationFile).where(AdminDocumentationFile.id == file_id)
        )
        doc_file = result.scalar_one_or_none()
        if not doc_file:
            return False
        
        await session.delete(doc_file)
        await session.commit()
        return True

