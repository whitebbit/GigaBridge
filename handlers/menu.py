from aiogram import F, Router, types
from aiogram.filters import Command
from utils.keyboards.main_kb import main_menu, instructions_platform_keyboard, instructions_more_keyboard
from utils.texts.messages import (
    INSTRUCTIONS_PC_BASIC,
    INSTRUCTIONS_PC_MORE,
    INSTRUCTIONS_MOBILE_BASIC,
    INSTRUCTIONS_MOBILE_MORE
)

router = Router()


@router.message(Command("menu"))
async def menu_handler(message: types.Message):
    try:
        await message.delete()
    except:
        pass
    await message.answer(
        "Выберите действие:",
        reply_markup=main_menu()
    )


@router.callback_query(F.data == "menu")
async def menu_callback(callback: types.CallbackQuery):
    """Обработчик кнопки 'Назад' из админ-панели - возвращает в главное меню"""
    from utils.message_utils import callback_answer_and_save
    await callback_answer_and_save(
        callback,
        "Выберите действие:",
        reply_markup=main_menu()
    )


@router.message(F.text == "📖 Инструкции")
async def instructions_handler(message: types.Message):
    """Обработчик кнопки Инструкции - показывает выбор платформы"""
    try:
        await message.delete()
    except:
        pass
    await message.answer(
        "📖 <b>Инструкции по использованию</b>\n\n"
        "Выберите платформу:",
        reply_markup=instructions_platform_keyboard(),
        parse_mode="HTML"
    )


@router.callback_query(F.data == "instructions_pc")
async def instructions_pc_callback(callback: types.CallbackQuery):
    """Инструкция для ПК"""
    from utils.message_utils import callback_answer_and_save
    await callback_answer_and_save(
        callback,
        INSTRUCTIONS_PC_BASIC,
        reply_markup=instructions_more_keyboard("pc"),
        parse_mode="HTML"
    )
    
    # Отправляем сообщение с кнопками главного меню после inline-сообщения
    from core.loader import bot
    await bot.send_message(
        chat_id=callback.from_user.id,
        text=" ",  # Минимальный текст (пробел)
        reply_markup=main_menu()
    )


@router.callback_query(F.data == "instructions_mobile")
async def instructions_mobile_callback(callback: types.CallbackQuery):
    """Инструкция для телефонов"""
    from utils.message_utils import callback_answer_and_save
    await callback_answer_and_save(
        callback,
        INSTRUCTIONS_MOBILE_BASIC,
        reply_markup=instructions_more_keyboard("mobile"),
        parse_mode="HTML"
    )
    
    # Отправляем сообщение с кнопками главного меню после inline-сообщения
    from core.loader import bot
    await bot.send_message(
        chat_id=callback.from_user.id,
        text=" ",  # Минимальный текст (пробел)
        reply_markup=main_menu()
    )


@router.callback_query(F.data.startswith("instructions_more_"))
async def instructions_more_callback(callback: types.CallbackQuery):
    """Дополнительная информация для инструкций"""
    platform = callback.data.split("_")[-1]
    
    if platform == "pc":
        text = INSTRUCTIONS_PC_MORE
    elif platform == "mobile":
        text = INSTRUCTIONS_MOBILE_MORE
    else:
        text = "Информация не найдена"
    
    from utils.message_utils import callback_answer_and_save
    await callback_answer_and_save(callback, text, parse_mode="HTML")
    
    # Отправляем сообщение с кнопками главного меню после инструкций
    from core.loader import bot
    await bot.send_message(
        chat_id=callback.from_user.id,
        text=" ",  # Минимальный текст (пробел)
        reply_markup=main_menu()
    )


@router.callback_query(F.data == "instructions_back")
async def instructions_back_callback(callback: types.CallbackQuery):
    """Вернуться к выбору платформы"""
    from utils.message_utils import callback_answer_and_save
    await callback_answer_and_save(
        callback,
        "📖 <b>Инструкции по использованию</b>\n\n"
        "Выберите платформу:",
        reply_markup=instructions_platform_keyboard(),
        parse_mode="HTML"
    )


@router.callback_query(F.data == "show_instructions_after_purchase")
async def show_instructions_after_purchase_callback(callback: types.CallbackQuery):
    """Показать инструкции после покупки - НЕ удаляет сообщение с ключом"""
    # Отвечаем на callback без удаления сообщения
    try:
        await callback.answer()
    except:
        pass
    
    # Отправляем новое сообщение с инструкциями, НЕ удаляя старое
    from core.loader import bot
    sent_message = await bot.send_message(
        chat_id=callback.from_user.id,
        text="📖 <b>Инструкции по использованию</b>\n\n"
             "Выберите платформу:",
        reply_markup=instructions_platform_keyboard(),
        parse_mode="HTML"
    )
    
    # Отправляем сообщение с кнопками главного меню после inline-сообщения
    await bot.send_message(
        chat_id=callback.from_user.id,
        text=" ",  # Минимальный текст (пробел)
        reply_markup=main_menu()
    )


@router.callback_query(F.data == "get_key")
async def get_key_callback(callback: types.CallbackQuery):
    """Обработчик кнопки 'Получить ключ' - открывает список локаций для покупки"""
    
    # Импортируем функции для покупки
    from utils.db import get_active_locations, has_available_server_for_location, get_user_by_tg_id, has_user_made_purchase
    from core.config import config
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    
    locations = await get_active_locations()
    
    if not locations:
        from utils.message_utils import callback_answer_and_save
        await callback_answer_and_save(
            callback,
            "❌ К сожалению, сейчас нет доступных локаций для покупки.\n"
            "Попробуйте позже.",
            reply_markup=main_menu()
        )
        return
    
    # Проверяем, является ли пользователь новым
    user = await get_user_by_tg_id(str(callback.from_user.id))
    is_new_user = False
    discount_percent = config.FIRST_PURCHASE_DISCOUNT_PERCENT
    
    if user:
        has_purchase = await has_user_made_purchase(user.id)
        if not has_purchase and not user.used_first_purchase_discount:
            is_new_user = True
            discount_percent = config.FIRST_PURCHASE_DISCOUNT_PERCENT
    
    text = "🛒 <b>Выберите локацию для GigaBridge-подключения</b>\n\n"
    
    if is_new_user:
        text += f"🎉 <b>Специальное предложение!</b>\n"
        text += f"🎁 Скидка {discount_percent:.0f}% на первую покупку для новых пользователей!\n\n"
    
    text += "📍 Доступные локации:\n\n"
    
    kb = InlineKeyboardBuilder()
    for location in locations:
        # Проверяем, есть ли доступные серверы в локации (с учетом загрузки)
        has_available = await has_available_server_for_location(location.id)
        if has_available:
            if is_new_user:
                # Вычисляем цену со скидкой
                discounted_price = location.price * (1 - discount_percent / 100)
                button_text = f"🌍 {location.name} - {discounted_price:.0f} ₽ (скидка {discount_percent:.0f}%)"
            else:
                button_text = f"🌍 {location.name} - {location.price:.0f} ₽"
            
            kb.button(
                text=button_text,
                callback_data=f"buy_location_{location.id}"
            )
    
    if not kb.buttons:
        from utils.message_utils import callback_answer_and_save
        await callback_answer_and_save(
            callback,
            "❌ К сожалению, все серверы на доступных локациях заполнены.\n"
            "Попробуйте позже.",
            reply_markup=main_menu()
        )
        return
    
    kb.button(text="❌ Отмена", callback_data="cancel_purchase")
    kb.adjust(1)
    
    from utils.message_utils import callback_answer_and_save
    await callback_answer_and_save(callback, text, reply_markup=kb.as_markup(), parse_mode="HTML")


@router.callback_query(F.data == "help")
async def help_callback(callback: types.CallbackQuery):
    from utils.texts.messages import HELP_MESSAGE
    from utils.message_utils import callback_answer_and_save
    await callback_answer_and_save(callback, HELP_MESSAGE, parse_mode="HTML", reply_markup=main_menu())
