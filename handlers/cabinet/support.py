from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from utils.keyboards.main_kb import main_menu
from utils.db import (
    get_user_by_tg_id,
    create_support_ticket,
    get_user_support_tickets
)
from datetime import datetime

router = Router()


class SupportStates(StatesGroup):
    waiting_for_message = State()


@router.message(F.text == "💬 Поддержка")
async def support_handler(message: types.Message, state: FSMContext):
    """Обработчик кнопки Поддержка"""
    try:
        await message.delete()
    except:
        pass
    
    user = await get_user_by_tg_id(str(message.from_user.id))
    
    if not user:
        await message.answer("❌ Пользователь не найден. Используйте /start", reply_markup=main_menu())
        return
    
    # Получаем тикеты пользователя
    tickets = await get_user_support_tickets(user.id)
    open_tickets = [t for t in tickets if t.status == "open"]
    answered_tickets = [t for t in tickets if t.status == "answered"]
    
    text = "💬 <b>Поддержка</b>\n\n"
    
    if open_tickets:
        text += f"📬 У вас {len(open_tickets)} открытых обращений\n"
    if answered_tickets:
        text += f"✅ У вас {len(answered_tickets)} обращений с ответами\n\n"
    
    text += "Опишите вашу проблему или вопрос, и мы обязательно поможем вам!\n\n"
    text += "Напишите ваше сообщение:"
    
    # Создаем клавиатуру с кнопкой отмены
    kb = InlineKeyboardBuilder()
    kb.button(text="❌ Отмена", callback_data="cancel_support")
    kb.adjust(1)
    
    await state.set_state(SupportStates.waiting_for_message)
    await message.answer(text, parse_mode="HTML", reply_markup=kb.as_markup())


@router.message(SupportStates.waiting_for_message)
async def support_message_handler(message: types.Message, state: FSMContext):
    """Обработчик сообщения в поддержку"""
    try:
        await message.delete()
    except:
        pass
    
    user = await get_user_by_tg_id(str(message.from_user.id))
    
    if not user:
        await message.answer("❌ Пользователь не найден. Используйте /start", reply_markup=main_menu())
        await state.clear()
        return
    
    # Проверяем, что сообщение не пустое
    if not message.text or len(message.text.strip()) < 5:
        await message.answer(
            "❌ Сообщение слишком короткое. Пожалуйста, опишите проблему подробнее (минимум 5 символов).",
            reply_markup=main_menu()
        )
        return
    
    # Создаем тикет
    ticket = await create_support_ticket(user.id, message.text.strip())
    
    text = "✅ <b>Ваше обращение отправлено в поддержку!</b>\n\n"
    text += f"📝 <b>Ваше сообщение:</b>\n{message.text.strip()}\n\n"
    text += f"🆔 <b>Номер обращения:</b> #{ticket.id}\n\n"
    text += "Мы рассмотрим ваше обращение и ответим в ближайшее время."
    
    await state.clear()
    await message.answer(text, parse_mode="HTML", reply_markup=main_menu())


@router.callback_query(F.data == "cancel_support")
async def cancel_support_callback(callback: types.CallbackQuery, state: FSMContext):
    """Обработчик кнопки отмены отправки сообщения в поддержку"""
    await callback.answer("Отправка сообщения отменена")
    
    # Очищаем состояние
    await state.clear()
    
    # Отправляем сообщение об отмене
    text = "❌ <b>Отправка сообщения в поддержку отменена</b>"
    
    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=None)
    except:
        pass
    
    # Отправляем новое сообщение с главным меню
    await callback.message.answer(
        "Выберите действие:",
        reply_markup=main_menu()
    )

