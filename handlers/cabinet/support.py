from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from utils.keyboards.main_kb import main_menu
from utils.db import (
    get_user_by_tg_id,
    create_support_ticket,
    get_user_support_tickets,
    MAX_MESSAGE_LENGTH,
    MAX_PHOTO_SIZE_MB
)
from core.loader import bot
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
    text += "Вы можете отправить:\n"
    text += "• Текстовое сообщение\n"
    text += "• Фото с подписью\n\n"
    text += f"⚠️ <b>Ограничения:</b>\n"
    text += f"• Длина сообщения: до {MAX_MESSAGE_LENGTH} символов\n"
    text += f"• Размер изображения: до {MAX_PHOTO_SIZE_MB} МБ\n\n"
    text += "Напишите ваше сообщение или отправьте фото:"
    
    # Создаем клавиатуру с кнопкой отмены
    kb = InlineKeyboardBuilder()
    kb.button(text="❌ Отмена", callback_data="cancel_support")
    kb.adjust(1)
    
    await state.set_state(SupportStates.waiting_for_message)
    await message.answer(text, parse_mode="HTML", reply_markup=kb.as_markup())


@router.message(SupportStates.waiting_for_message)
async def support_message_handler(message: types.Message, state: FSMContext):
    """Обработчик сообщения в поддержку (текст или фото с подписью)"""
    try:
        await message.delete()
    except:
        pass
    
    user = await get_user_by_tg_id(str(message.from_user.id))
    
    if not user:
        await message.answer("❌ Пользователь не найден. Используйте /start", reply_markup=main_menu())
        await state.clear()
        return
    
    # Получаем текст сообщения (из текста или подписи к фото)
    message_text = ""
    photo_file_id = None
    
    # Проверяем, есть ли фото
    if message.photo:
        # Получаем самое большое фото
        photo = message.photo[-1]
        photo_file_id = photo.file_id
        
        # Проверяем размер файла
        try:
            file_info = await bot.get_file(photo_file_id)
            file_size_mb = file_info.file_size / (1024 * 1024)  # Размер в МБ
            
            if file_size_mb > MAX_PHOTO_SIZE_MB:
                await message.answer(
                    f"❌ Размер изображения слишком большой ({file_size_mb:.2f} МБ). "
                    f"Максимальный размер: {MAX_PHOTO_SIZE_MB} МБ.\n\n"
                    "Пожалуйста, отправьте изображение меньшего размера.",
                    reply_markup=main_menu()
                )
                return
        except Exception as e:
            await message.answer(
                "❌ Ошибка при проверке размера изображения. Попробуйте отправить другое изображение.",
                reply_markup=main_menu()
            )
            return
        
        # Получаем текст из подписи к фото
        message_text = message.caption or ""
    elif message.text:
        message_text = message.text
    else:
        await message.answer(
            "❌ Пожалуйста, отправьте текстовое сообщение или фото с подписью.",
            reply_markup=main_menu()
        )
        return
    
    # Проверяем, что сообщение не пустое
    message_text = message_text.strip()
    if len(message_text) < 5:
        await message.answer(
            "❌ Сообщение слишком короткое. Пожалуйста, опишите проблему подробнее (минимум 5 символов).",
            reply_markup=main_menu()
        )
        return
    
    # Проверяем максимальную длину сообщения
    if len(message_text) > MAX_MESSAGE_LENGTH:
        await message.answer(
            f"❌ Сообщение слишком длинное ({len(message_text)} символов). "
            f"Максимальная длина: {MAX_MESSAGE_LENGTH} символов.\n\n"
            "Пожалуйста, сократите ваше сообщение.",
            reply_markup=main_menu()
        )
        return
    
    # Создаем тикет
    ticket = await create_support_ticket(user.id, message_text, photo_file_id=photo_file_id)
    
    text = "✅ <b>Ваше обращение отправлено в поддержку!</b>\n\n"
    text += f"📝 <b>Ваше сообщение:</b>\n{message_text}\n\n"
    if photo_file_id:
        text += "📷 <b>Изображение прикреплено</b>\n\n"
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

