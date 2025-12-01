"""
Скрипт для добавления тестовой подписки пользователю
Использование: 
    python scripts/add_test_subscription.py <telegram_user_id>
    python scripts/add_test_subscription.py <username>
"""
import asyncio
import sys
from pathlib import Path
from datetime import datetime, timedelta

# Добавляем корневую директорию проекта в PYTHONPATH
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from database.base import async_session
from database.models import User, Server, Tariff, Subscription
from sqlalchemy import select
from utils.db import generate_test_key


async def add_test_subscription_by_id(tg_id: str):
    """Добавить тестовую подписку пользователю по ID"""
    async with async_session() as session:
        # Проверяем, существует ли пользователь
        result = await session.execute(select(User).where(User.tg_id == str(tg_id)))
        user = result.scalar_one_or_none()
        
        if not user:
            print(f"❌ Пользователь с ID {tg_id} не найден в базе данных.")
            print("Пользователь должен сначала использовать команду /start в боте.")
            sys.exit(1)
        
        # Находим активный сервер
        result = await session.execute(
            select(Server).where(Server.is_active == True).limit(1)
        )
        server = result.scalar_one_or_none()
        
        if not server:
            print("❌ Не найдено активных серверов в базе данных.")
            print("Создайте хотя бы один активный сервер через админ-панель.")
            sys.exit(1)
        
        # Находим или создаем тестовый тариф
        result = await session.execute(select(Tariff).limit(1))
        tariff = result.scalar_one_or_none()
        
        if not tariff:
            print("Создаю тестовый тариф...")
            tariff = Tariff(
                name="Тестовый",
                price=0.0,
                duration_days=30,
                traffic_limit=100.0  # 100 GB
            )
            session.add(tariff)
            await session.commit()
            await session.refresh(tariff)
        
        # Генерируем тестовый ключ
        test_key = generate_test_key()
        
        # Создаем подписку
        expire_date = datetime.utcnow() + timedelta(days=tariff.duration_days)
        subscription = Subscription(
            user_id=user.id,
            server_id=server.id,
            tariff_id=tariff.id,
            x3ui_client_id=test_key,
            status="active",
            expire_date=expire_date,
            traffic_limit=tariff.traffic_limit,
            traffic_used=0.0
        )
        session.add(subscription)
        await session.commit()
        await session.refresh(subscription)
        
        print(f"✅ Тестовая подписка добавлена пользователю {user.username or user.tg_id}!")
        print(f"   ID подписки: {subscription.id}")
        print(f"   Сервер: {server.name}")
        print(f"   Тариф: {tariff.name}")
        print(f"   Ключ: {test_key}")
        print(f"   Срок действия: {expire_date.strftime('%d.%m.%Y %H:%M')}")
        print(f"   Лимит трафика: {tariff.traffic_limit} GB")
        print("✅ Готово!")


async def add_test_subscription_by_username(username: str):
    """Добавить тестовую подписку пользователю по username"""
    # Убираем @ если есть
    username = username.lstrip('@')
    
    async with async_session() as session:
        # Проверяем, существует ли пользователь
        result = await session.execute(select(User).where(User.username == username))
        user = result.scalar_one_or_none()
        
        if not user:
            print(f"❌ Пользователь с username @{username} не найден в базе данных.")
            print("Пользователь должен сначала использовать команду /start в боте.")
            sys.exit(1)
        
        # Находим активный сервер
        result = await session.execute(
            select(Server).where(Server.is_active == True).limit(1)
        )
        server = result.scalar_one_or_none()
        
        if not server:
            print("❌ Не найдено активных серверов в базе данных.")
            print("Создайте хотя бы один активный сервер через админ-панель.")
            sys.exit(1)
        
        # Находим или создаем тестовый тариф
        result = await session.execute(select(Tariff).limit(1))
        tariff = result.scalar_one_or_none()
        
        if not tariff:
            print("Создаю тестовый тариф...")
            tariff = Tariff(
                name="Тестовый",
                price=0.0,
                duration_days=30,
                traffic_limit=100.0  # 100 GB
            )
            session.add(tariff)
            await session.commit()
            await session.refresh(tariff)
        
        # Генерируем тестовый ключ
        test_key = generate_test_key()
        
        # Создаем подписку
        expire_date = datetime.utcnow() + timedelta(days=tariff.duration_days)
        subscription = Subscription(
            user_id=user.id,
            server_id=server.id,
            tariff_id=tariff.id,
            x3ui_client_id=test_key,
            status="active",
            expire_date=expire_date,
            traffic_limit=tariff.traffic_limit,
            traffic_used=0.0
        )
        session.add(subscription)
        await session.commit()
        await session.refresh(subscription)
        
        print(f"✅ Тестовая подписка добавлена пользователю @{user.username} (ID: {user.tg_id})!")
        print(f"   ID подписки: {subscription.id}")
        print(f"   Сервер: {server.name}")
        print(f"   Тариф: {tariff.name}")
        print(f"   Ключ: {test_key}")
        print(f"   Срок действия: {expire_date.strftime('%d.%m.%Y %H:%M')}")
        print(f"   Лимит трафика: {tariff.traffic_limit} GB")
        print("✅ Готово!")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Использование:")
        print("  python scripts/add_test_subscription.py <telegram_user_id>")
        print("  python scripts/add_test_subscription.py <username>")
        print("\nПримеры:")
        print("  python scripts/add_test_subscription.py 123456789")
        print("  python scripts/add_test_subscription.py @username")
        print("  python scripts/add_test_subscription.py username")
        sys.exit(1)
    
    identifier = sys.argv[1]
    
    # Определяем, это ID или username
    if identifier.isdigit():
        # Это ID
        asyncio.run(add_test_subscription_by_id(identifier))
    else:
        # Это username
        asyncio.run(add_test_subscription_by_username(identifier))

