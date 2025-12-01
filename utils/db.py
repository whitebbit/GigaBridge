from database.base import async_session
from database.models import User, Server, Payment, Subscription, Tariff, Location, PromoCode, PromoCodeUsage, SupportTicket
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


def get_subscription_identifier(subscription: Subscription, location_name: str = None) -> str:
    """
    Генерирует уникальный идентификатор подписки в формате {LOCATION_CODE}-{ID}
    
    Args:
        subscription: Объект подписки
        location_name: Название локации (опционально, если не передано, будет получено из БД)
    
    Returns:
        Строка в формате "MOS-123" или "SPB-456"
    """
    # Если название локации не передано, используем ID подписки как fallback
    if not location_name or location_name == "Неизвестно":
        location_name = f"LOC{subscription.id}"
    
    # Убираем пробелы и спецсимволы, оставляем только буквы
    clean_name = re.sub(r'[^a-zA-Zа-яА-ЯёЁ]', '', location_name)
    
    # Берем первые 3 буквы
    if len(clean_name) >= 3:
        location_code = clean_name[:3].upper()
    else:
        # Если меньше 3 символов, используем все что есть и дополняем
        location_code = clean_name.upper().ljust(3, 'X')
    
    # Если все еще пусто (только спецсимволы были), используем fallback
    if not location_code or location_code == 'XXX':
        location_code = f"LOC{subscription.id}"[:3].upper()
    
    return f"{location_code}-{subscription.id}"


async def get_user_by_tg_id(tg_id: str, use_cache: bool = True) -> Optional[User]:
    """Получить пользователя по Telegram ID с кэшированием"""
    tg_id_str = str(tg_id)
    cache_key = CacheKeys.USER_BY_TG_ID.format(tg_id=tg_id_str)
    
    # Проверяем кэш
    if use_cache:
        cached = await CacheService.get(cache_key)
        if cached:
            # Восстанавливаем объект User из словаря (упрощенная версия)
            user = User(**cached)
            return user
    
    async with async_session() as session:
        result = await session.execute(select(User).where(User.tg_id == tg_id_str))
        user = result.scalar_one_or_none()
        
        # Кэшируем результат на 5 минут
        if user and use_cache:
            user_dict = {
                'id': user.id,
                'tg_id': user.tg_id,
                'username': user.username,
                'x3ui_id': user.x3ui_id,
                'plan_id': user.plan_id,
                'expire_date': user.expire_date.isoformat() if user.expire_date else None,
                'status': user.status,
                'traffic_used': user.traffic_used,
                'traffic_limit': user.traffic_limit,
                'is_admin': user.is_admin,
                'used_first_purchase_discount': user.used_first_purchase_discount,
                'created_at': user.created_at.isoformat() if user.created_at else None,
            }
            await CacheService.set(cache_key, user_dict, ttl=300)
        
        return user


async def is_admin(tg_id: str) -> bool:
    """Проверить, является ли пользователь администратором"""
    user = await get_user_by_tg_id(tg_id)
    return user.is_admin if user else False


async def get_all_servers() -> list[Server]:
    """Получить все серверы с загруженными локациями"""
    async with async_session() as session:
        result = await session.execute(
            select(Server)
            .options(joinedload(Server.location))
            .order_by(Server.id)
        )
        return list(result.unique().scalars().all())


async def get_server_by_id(server_id: int, use_cache: bool = True) -> Optional[Server]:
    """Получить сервер по ID с загруженной локацией и кэшированием"""
    cache_key = CacheKeys.SERVER_BY_ID.format(id=server_id)
    
    # Проверяем кэш
    if use_cache:
        cached = await CacheService.get(cache_key)
        if cached:
            # Восстанавливаем объект Server из словаря
            server = Server(**cached)
            # Загружаем локацию отдельно если нужно
            if cached.get('location_id'):
                location = await get_location_by_id(cached['location_id'], use_cache=True)
                if location:
                    server.location = location
            return server
    
    async with async_session() as session:
        result = await session.execute(
            select(Server)
            .options(joinedload(Server.location))
            .where(Server.id == server_id)
        )
        server = result.unique().scalar_one_or_none()
        
        # Кэшируем результат на 10 минут
        if server and use_cache:
            server_dict = {
                'id': server.id,
                'name': server.name,
                'api_url': server.api_url,
                'api_username': server.api_username,
                'api_password': server.api_password,
                'pbk': server.pbk,
                'location_id': server.location_id,
                'description': server.description,
                'is_active': server.is_active,
                'max_users': server.max_users,
                'current_users': server.current_users,
                'created_at': server.created_at.isoformat() if server.created_at else None,
                'updated_at': server.updated_at.isoformat() if server.updated_at else None,
            }
            await CacheService.set(cache_key, server_dict, ttl=600)
        
        return server


async def create_server(
    name: str,
    api_url: str,
    api_username: str,
    api_password: str,
    location_id: int,
    description: str = None,
    max_users: int = None
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
    """
    async with async_session() as session:
        server = Server(
            name=name,
            api_url=api_url,
            api_username=api_username,
            api_password=api_password,
            location_id=location_id,
            description=description,
            max_users=max_users
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
        
        # Список полей, которые можно установить в None
        nullable_fields = {'description', 'max_users', 'pbk'}
        
        for key, value in kwargs.items():
            if hasattr(server, key):
                # Для nullable полей разрешаем устанавливать None
                if key in nullable_fields:
                    setattr(server, key, value)
                # Для не-nullable полей устанавливаем только если значение не None
                elif value is not None:
                    setattr(server, key, value)
        
        await session.commit()
        await session.refresh(server)
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
    """Получить все активные подписки"""
    async with async_session() as session:
        result = await session.execute(
            select(Subscription).where(Subscription.status == "active")
        )
        return list(result.scalars().all())


async def get_all_expired_subscriptions() -> List[Subscription]:
    """Получить все истекшие подписки"""
    async with async_session() as session:
        result = await session.execute(
            select(Subscription).where(Subscription.status == "expired")
        )
        return list(result.scalars().all())


async def check_and_block_expired_subscriptions() -> int:
    """Проверить и заблокировать истекшие подписки. Возвращает количество заблокированных."""
    from datetime import datetime
    blocked_count = 0
    
    async with async_session() as session:
        # Получаем все активные подписки
        result = await session.execute(
            select(Subscription).where(Subscription.status == "active")
        )
        subscriptions = result.scalars().all()
        
        current_time = datetime.utcnow()
        
        for subscription in subscriptions:
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
    status: str = "active",
    expire_date = None,
    traffic_limit: float = 0.0
) -> Subscription:
    """Создать новую подписку"""
    async with async_session() as session:
        subscription = Subscription(
            user_id=user_id,
            server_id=server_id,
            tariff_id=tariff_id,
            x3ui_client_id=x3ui_client_id,
            x3ui_client_email=x3ui_client_email,
            status=status,
            expire_date=expire_date,
            traffic_limit=traffic_limit
        )
        session.add(subscription)
        await session.commit()
        await session.refresh(subscription)
        return subscription


async def get_user_subscriptions(user_id: int) -> List[Subscription]:
    """Получить все подписки пользователя"""
    async with async_session() as session:
        result = await session.execute(
            select(Subscription)
            .where(Subscription.user_id == user_id)
            .order_by(Subscription.created_at.desc())
        )
        return list(result.scalars().all())


async def get_subscription_by_id(subscription_id: int) -> Optional[Subscription]:
    """Получить подписку по ID"""
    async with async_session() as session:
        result = await session.execute(
            select(Subscription).where(Subscription.id == subscription_id)
        )
        return result.scalar_one_or_none()


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
    """Получить тариф по ID с кэшированием"""
    cache_key = CacheKeys.TARIFF_BY_ID.format(id=tariff_id)
    
    # Проверяем кэш
    if use_cache:
        cached = await CacheService.get(cache_key)
        if cached:
            return Tariff(**cached)
    
    async with async_session() as session:
        result = await session.execute(
            select(Tariff).where(Tariff.id == tariff_id)
        )
        tariff = result.scalar_one_or_none()
        
        # Кэшируем результат на 10 минут
        if tariff and use_cache:
            tariff_dict = {
                'id': tariff.id,
                'name': tariff.name,
                'price': tariff.price,
                'duration_days': tariff.duration_days,
                'traffic_limit': tariff.traffic_limit,
            }
            await CacheService.set(cache_key, tariff_dict, ttl=600)
        
        return tariff


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
    """Получить только активные локации с кэшированием"""
    cache_key = CacheKeys.ACTIVE_LOCATIONS
    
    # Проверяем кэш
    if use_cache:
        cached = await CacheService.get(cache_key)
        if cached:
            return [Location(**loc) for loc in cached]
    
    async with async_session() as session:
        result = await session.execute(
            select(Location).where(Location.is_active == True).order_by(Location.name)
        )
        locations = list(result.scalars().all())
        
        # Кэшируем результат на 10 минут
        if locations and use_cache:
            locations_dict = [
                {
                    'id': loc.id,
                    'name': loc.name,
                    'description': loc.description,
                    'price': loc.price,
                    'is_active': loc.is_active,
                    'created_at': loc.created_at.isoformat() if loc.created_at else None,
                    'updated_at': loc.updated_at.isoformat() if loc.updated_at else None,
                }
                for loc in locations
            ]
            await CacheService.set(cache_key, locations_dict, ttl=600)
        
        return locations


async def get_location_by_id(location_id: int, use_cache: bool = True) -> Optional[Location]:
    """Получить локацию по ID с кэшированием"""
    cache_key = CacheKeys.LOCATION_BY_ID.format(id=location_id)
    
    # Проверяем кэш
    if use_cache:
        cached = await CacheService.get(cache_key)
        if cached:
            return Location(**cached)
    
    async with async_session() as session:
        result = await session.execute(select(Location).where(Location.id == location_id))
        location = result.scalar_one_or_none()
        
        # Кэшируем результат на 10 минут
        if location and use_cache:
            location_dict = {
                'id': location.id,
                'name': location.name,
                'description': location.description,
                'price': location.price,
                'is_active': location.is_active,
                'created_at': location.created_at.isoformat() if location.created_at else None,
                'updated_at': location.updated_at.isoformat() if location.updated_at else None,
            }
            await CacheService.set(cache_key, location_dict, ttl=600)
        
        return location


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
    """Получить только активные серверы для локации с загруженными локациями и кэшированием"""
    cache_key = CacheKeys.SERVERS_BY_LOCATION.format(location_id=location_id)
    
    # Проверяем кэш
    if use_cache:
        cached = await CacheService.get(cache_key)
        if cached:
            servers = []
            for srv_dict in cached:
                server = Server(**srv_dict)
                # Загружаем локацию отдельно
                if srv_dict.get('location_id'):
                    location = await get_location_by_id(srv_dict['location_id'], use_cache=True)
                    if location:
                        server.location = location
                servers.append(server)
            return servers
    
    async with async_session() as session:
        result = await session.execute(
            select(Server)
            .options(joinedload(Server.location))
            .where(
                and_(Server.location_id == location_id, Server.is_active == True)
            )
            .order_by(Server.id)
        )
        servers = list(result.unique().scalars().all())
        
        # Кэшируем результат на 10 минут
        if servers and use_cache:
            servers_dict = [
                {
                    'id': srv.id,
                    'name': srv.name,
                    'api_url': srv.api_url,
                    'api_username': srv.api_username,
                    'api_password': srv.api_password,
                    'pbk': srv.pbk,
                    'location_id': srv.location_id,
                    'description': srv.description,
                    'is_active': srv.is_active,
                    'max_users': srv.max_users,
                    'current_users': srv.current_users,
                    'created_at': srv.created_at.isoformat() if srv.created_at else None,
                    'updated_at': srv.updated_at.isoformat() if srv.updated_at else None,
                }
                for srv in servers
            ]
            await CacheService.set(cache_key, servers_dict, ttl=600)
        
        return servers


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


# ==================== ПРОМОКОДЫ ====================

async def create_promo_code(code: str, discount_percent: float, max_uses: Optional[int] = None) -> PromoCode:
    """Создать промокод (max_uses=None для безлимитного промокода)"""
    async with async_session() as session:
        promo_code = PromoCode(
            code=code.upper().strip(),
            discount_percent=discount_percent,
            max_uses=max_uses,  # None = безлимитный
            current_uses=0,
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
    
    # Проверяем, использовал ли пользователь уже этот промокод
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

async def create_support_ticket(user_id: int, message: str) -> SupportTicket:
    """Создать новый тикет поддержки"""
    async with async_session() as session:
        ticket = SupportTicket(
            user_id=user_id,
            message=message,
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

