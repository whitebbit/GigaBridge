from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext
from utils.keyboards.main_kb import main_menu
from utils.db import (
    get_active_locations,
    get_location_by_id,
    has_available_server_for_location,
    get_user_by_tg_id,
    has_user_made_purchase
)
from core.config import config
from aiogram.utils.keyboard import InlineKeyboardBuilder

router = Router()


@router.message(F.text == "🛒 Покупка")
async def purchase_start(message: types.Message):
    """Обработчик кнопки Покупка - показывает список доступных локаций"""
    try:
        await message.delete()
    except:
        pass
    
    locations = await get_active_locations()
    
    if not locations:
        await message.answer(
            "❌ К сожалению, сейчас нет доступных локаций для покупки.\n"
            "Попробуйте позже.",
            reply_markup=main_menu()
        )
        return
    
    # Проверяем, является ли пользователь новым
    user = await get_user_by_tg_id(str(message.from_user.id))
    is_new_user = False
    discount_percent = config.FIRST_PURCHASE_DISCOUNT_PERCENT
    
    if user:
        has_purchase = await has_user_made_purchase(user.id)
        if not has_purchase and not user.used_first_purchase_discount:
            is_new_user = True
    
    text = "🛒 <b>Выберите локацию для GigaBridge-подключения</b>\n\n"
    
    if is_new_user:
        text += f"🎉 <b>Специальное предложение!</b>\n"
        text += f"🎁 Скидка {discount_percent:.0f}% на первую покупку для новых пользователей!\n\n"
    
    text += "📍 Доступные локации:\n\n"
    
    kb = InlineKeyboardBuilder()
    location_buttons = []
    
    for location in locations:
        # Проверяем, есть ли доступные серверы в локации (с учетом загрузки)
        has_available = await has_available_server_for_location(location.id)
        if has_available:
            if is_new_user:
                # Вычисляем цену со скидкой
                discounted_price = location.price * (1 - discount_percent / 100)
                button_text = f"{location.name}\n{discounted_price:.0f}₽ (-{discount_percent:.0f}%)"
            else:
                button_text = f"{location.name}\n{location.price:.0f}₽"
            
            location_buttons.append((button_text, f"buy_location_{location.id}"))
    
    if not location_buttons:
        await message.answer(
            "❌ К сожалению, все серверы на доступных локациях заполнены.\n"
            "Попробуйте позже.",
            reply_markup=main_menu()
        )
        return
    
    # Добавляем все кнопки локаций
    for button_text, callback_data in location_buttons:
        kb.button(text=button_text, callback_data=callback_data)
    
    # Добавляем кнопку "Отмена"
    kb.button(text="❌ Отмена", callback_data="cancel_purchase")
    
    # Располагаем кнопки: локации по 3 в ряд (или все в один, если меньше 3), отмена отдельно
    location_buttons_count = len(location_buttons)
    if location_buttons_count < 3:
        # Все кнопки локаций в один ряд, отмена отдельно
        adjust_params = [location_buttons_count, 1]
    else:
        # По 3 кнопки локаций в ряд, отмена отдельно
        # Вычисляем количество полных рядов по 3 и остаток
        full_rows = location_buttons_count // 3
        remainder = location_buttons_count % 3
        adjust_params = [3] * full_rows
        if remainder > 0:
            adjust_params.append(remainder)
        adjust_params.append(1)  # Кнопка отмены
    
    kb.adjust(*adjust_params)
    
    await message.answer(text, reply_markup=kb.as_markup(), parse_mode="HTML")


@router.callback_query(F.data == "cancel_purchase")
async def cancel_purchase_callback(callback: types.CallbackQuery, state: FSMContext):
    """Отмена покупки"""
    await state.clear()
    from utils.message_utils import callback_answer_and_save
    await callback_answer_and_save(callback, "❌ Покупка отменена", reply_markup=main_menu())

