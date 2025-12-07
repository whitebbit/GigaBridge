from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from .models import User
import uuid

async def get_user_by_tg_id(session: AsyncSession, tg_id: int | str):
    """Получить пользователя по Telegram ID"""
    result = await session.execute(select(User).where(User.tg_id == str(tg_id)))
    return result.scalars().first()

async def create_user(session: AsyncSession, tg_id: int | str, username: str | None = None, sub_id: str | None = None):
    """Создать нового пользователя
    
    Args:
        session: Сессия базы данных
        tg_id: Telegram ID пользователя
        username: Username пользователя (опционально)
        sub_id: SubId для подписок (опционально, если не указан - генерируется автоматически)
    """
    # Генерируем subId, если он не передан
    if sub_id is None:
        sub_id = str(uuid.uuid4())
    
    user = User(tg_id=str(tg_id), username=username, sub_id=sub_id)
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user
