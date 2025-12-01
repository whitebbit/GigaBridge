# handlers/start.py
from aiogram import Router, types
from aiogram.filters import Command
from utils.keyboards.main_kb import main_menu, start_menu
from utils.texts.messages import START_MESSAGE
from database.base import async_session
from database.crud import get_user_by_tg_id, create_user

router = Router()

@router.message(Command("start"))
async def start_handler(message: types.Message):
    """Обработчик команды /start - добавляет пользователя в БД, если его еще нет"""
    async with async_session() as session:
        user = await get_user_by_tg_id(session, message.from_user.id)
        if not user:
            await create_user(session, message.from_user.id, message.from_user.username)
    
    # Отправляем стартовое сообщение с inline-кнопками
    # Кнопки управления (ReplyKeyboardMarkup) будут добавлены автоматически через патч
    await message.answer(START_MESSAGE, reply_markup=start_menu())
