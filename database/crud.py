from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from .models import User

async def get_user_by_tg_id(session: AsyncSession, tg_id: int | str):
    """Получить пользователя по Telegram ID"""
    result = await session.execute(select(User).where(User.tg_id == str(tg_id)))
    return result.scalars().first()

async def create_user(session: AsyncSession, tg_id: int | str, username: str | None = None):
    """Создать нового пользователя"""
    user = User(tg_id=str(tg_id), username=username)
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user
