"""
Скрипт для назначения пользователя администратором
Использование: 
    python scripts/set_admin.py <telegram_user_id>
    python scripts/set_admin.py <username>
"""
import asyncio
import sys
from pathlib import Path

# Добавляем корневую директорию проекта в PYTHONPATH
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from database.base import async_session
from database.models import User
from sqlalchemy import select
import uuid


async def set_admin_by_id(tg_id: str):
    """Установить пользователя администратором по ID"""
    async with async_session() as session:
        # Проверяем, существует ли пользователь
        result = await session.execute(select(User).where(User.tg_id == str(tg_id)))
        user = result.scalar_one_or_none()
        
        if not user:
            print(f"❌ Пользователь с ID {tg_id} не найден в базе данных.")
            print("Создаю нового пользователя...")
            user = User(
                tg_id=str(tg_id),
                username=None,
                is_admin=True,
                sub_id=str(uuid.uuid4())  # Генерируем subId для пользователя
            )
            session.add(user)
        else:
            user.is_admin = True
            print(f"✅ Пользователь {user.username or user.tg_id} назначен администратором!")
        
        await session.commit()
        print("✅ Готово!")


async def set_admin_by_username(username: str):
    """Установить пользователя администратором по username"""
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
        else:
            user.is_admin = True
            print(f"✅ Пользователь @{user.username} (ID: {user.tg_id}) назначен администратором!")
        
        await session.commit()
        print("✅ Готово!")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Использование:")
        print("  python scripts/set_admin.py <telegram_user_id>")
        print("  python scripts/set_admin.py <username>")
        print("\nПримеры:")
        print("  python scripts/set_admin.py 123456789")
        print("  python scripts/set_admin.py @username")
        print("  python scripts/set_admin.py username")
        sys.exit(1)
    
    identifier = sys.argv[1]
    
    # Определяем, это ID или username
    if identifier.isdigit():
        # Это ID
        asyncio.run(set_admin_by_id(identifier))
    else:
        # Это username
        asyncio.run(set_admin_by_username(identifier))

