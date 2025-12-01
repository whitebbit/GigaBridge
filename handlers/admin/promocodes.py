"""
Обработчики для управления промокодами в админ-панели
"""
from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.exceptions import TelegramBadRequest
from utils.filters import AdminFilter
from utils.keyboards.admin_kb import admin_menu, cancel_keyboard
import html
from utils.db import (
    get_all_promo_codes,
    get_promo_code_by_id,
    create_promo_code,
    update_promo_code,
    delete_promo_code
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

router = Router()


async def safe_edit_text(message: types.Message, text: str, reply_markup=None, parse_mode="HTML"):
    """Безопасное редактирование сообщения"""
    try:
        await message.edit_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
    except TelegramBadRequest as e:
        if "message is not modified" not in str(e).lower():
            raise


def promocodes_menu():
    """Меню управления промокодами"""
    kb = InlineKeyboardBuilder()
    kb.button(text="➕ Добавить", callback_data="admin_promocode_add")
    kb.button(text="📋 Список", callback_data="admin_promocode_list")
    kb.button(text="🔙 Назад", callback_data="admin_menu")
    kb.adjust(1)
    return kb.as_markup()


def promocode_list_keyboard(promocodes: list):
    """Клавиатура со списком промокодов"""
    kb = InlineKeyboardBuilder()
    for promo in promocodes:
        status = "✅" if promo.is_active else "❌"
        if promo.max_uses is None:
            uses_text = f"{promo.current_uses}/∞"
        else:
            uses_text = f"{promo.current_uses}/{promo.max_uses}"
        kb.button(
            text=f"{status} {promo.code} - {promo.discount_percent:.0f}% ({uses_text})",
            callback_data=f"admin_promocode_edit_{promo.id}"
        )
    kb.button(text="🔙 Назад", callback_data="admin_promocodes")
    kb.adjust(1)
    return kb.as_markup()


def promocode_edit_keyboard(promocode_id: int):
    """Клавиатура для редактирования промокода"""
    kb = InlineKeyboardBuilder()
    kb.button(text="✏️ Код", callback_data=f"admin_promocode_edit_code_{promocode_id}")
    kb.button(text="💰 Скидка", callback_data=f"admin_promocode_edit_discount_{promocode_id}")
    kb.button(text="🔢 Лимит", callback_data=f"admin_promocode_edit_max_uses_{promocode_id}")
    kb.button(text="🔄 Статус", callback_data=f"admin_promocode_toggle_{promocode_id}")
    kb.button(text="🗑️ Удалить", callback_data=f"admin_promocode_delete_{promocode_id}")
    kb.button(text="🔙 Назад", callback_data="admin_promocode_list")
    kb.adjust(2, 2, 1, 1)
    return kb.as_markup()


class AddPromoCodeStates(StatesGroup):
    waiting_code = State()
    waiting_discount = State()
    waiting_max_uses = State()


class EditPromoCodeStates(StatesGroup):
    waiting_code = State()
    waiting_discount = State()
    waiting_max_uses = State()


@router.callback_query(F.data == "admin_promocodes", AdminFilter())
async def promocodes_menu_callback(callback: types.CallbackQuery):
    """Меню управления промокодами"""
    await callback.answer()
    await safe_edit_text(
        callback.message,
        "🎟️ <b>Управление промокодами</b>\n\n"
        "Выберите действие:",
        reply_markup=promocodes_menu()
    )


@router.callback_query(F.data == "admin_promocode_list", AdminFilter())
async def promocode_list_callback(callback: types.CallbackQuery):
    """Список промокодов"""
    await callback.answer()
    promocodes = await get_all_promo_codes()
    
    if not promocodes:
        await safe_edit_text(
            callback.message,
            "📋 <b>Список промокодов</b>\n\n"
            "Промокоды не найдены. Добавьте первый промокод!",
            reply_markup=promocodes_menu()
        )
        return
    
    text = "📋 <b>Список промокодов</b>\n\n"
    for promo in promocodes:
        status = "✅ Активен" if promo.is_active else "❌ Неактивен"
        text += f"{status} <b>{html.escape(promo.code)}</b>\n"
        text += f"   💰 Скидка: {promo.discount_percent:.0f}%\n"
        if promo.max_uses is None:
            text += f"   📊 Использований: {promo.current_uses}/∞ (безлимитный)\n\n"
        else:
            text += f"   📊 Использований: {promo.current_uses}/{promo.max_uses}\n\n"
    
    await safe_edit_text(callback.message, text, reply_markup=promocode_list_keyboard(promocodes))


@router.callback_query(F.data == "admin_promocode_add", AdminFilter())
async def promocode_add_start(callback: types.CallbackQuery, state: FSMContext):
    """Начало добавления промокода"""
    await callback.answer()
    await safe_edit_text(
        callback.message,
        "➕ <b>Добавление нового промокода</b>\n\n"
        "Введите код промокода (например: PROMO2024):",
        reply_markup=cancel_keyboard()
    )
    await state.set_state(AddPromoCodeStates.waiting_code)


@router.message(AddPromoCodeStates.waiting_code, AdminFilter())
async def promocode_add_code(message: types.Message, state: FSMContext):
    """Ввод кода промокода"""
    code = message.text.strip().upper()
    if not code:
        await message.answer("❌ Код не может быть пустым. Введите код промокода:")
        return
    
    # Проверяем, существует ли уже такой промокод
    from utils.db import get_promo_code_by_code
    existing = await get_promo_code_by_code(code)
    if existing:
        await message.answer("❌ Промокод с таким кодом уже существует. Введите другой код:")
        return
    
    await state.update_data(code=code)
    await message.answer(
        "Введите процент скидки (число от 0 до 100, например: 10 для 10%):",
        reply_markup=cancel_keyboard()
    )
    await state.set_state(AddPromoCodeStates.waiting_discount)


@router.message(AddPromoCodeStates.waiting_discount, AdminFilter())
async def promocode_add_discount(message: types.Message, state: FSMContext):
    """Ввод процента скидки"""
    try:
        discount = float(message.text.replace(",", "."))
        if discount < 0 or discount > 100:
            await message.answer("❌ Скидка должна быть от 0 до 100. Введите процент скидки:")
            return
        await state.update_data(discount_percent=discount)
        await message.answer(
            "Введите максимальное количество использований:\n"
            "• Число (например: 100) - для промокода с лимитом\n"
            "• 0 или 'unlimited' - для безлимитного промокода",
            reply_markup=cancel_keyboard()
        )
        await state.set_state(AddPromoCodeStates.waiting_max_uses)
    except ValueError:
        await message.answer("❌ Неверный формат. Введите число от 0 до 100:")


@router.message(AddPromoCodeStates.waiting_max_uses, AdminFilter())
async def promocode_add_max_uses(message: types.Message, state: FSMContext):
    """Ввод максимального количества использований"""
    text_input = message.text.strip().lower()
    max_uses = None
    
    # Проверяем, является ли ввод запросом на безлимитный промокод
    if text_input in ["0", "unlimited", "безлимит", "∞"]:
        max_uses = None  # Безлимитный промокод
    else:
        try:
            max_uses = int(text_input)
            if max_uses < 1:
                await message.answer("❌ Количество использований должно быть больше 0. Введите число или 0 для безлимитного:", reply_markup=cancel_keyboard())
                return
        except ValueError:
            await message.answer("❌ Неверный формат. Введите целое число или 0/unlimited для безлимитного:", reply_markup=cancel_keyboard())
            return
    
    data = await state.get_data()
    await state.clear()
    
    try:
        promo_code = await create_promo_code(
            code=data["code"],
            discount_percent=data["discount_percent"],
            max_uses=max_uses
        )
        
        if max_uses is None:
            max_uses_text = "∞ (безлимитный)"
        else:
            max_uses_text = str(max_uses)
        
        await message.answer(
            f"✅ <b>Промокод успешно добавлен!</b>\n\n"
            f"Код: <b>{html.escape(promo_code.code)}</b>\n"
            f"Скидка: {promo_code.discount_percent:.0f}%\n"
            f"Макс. использований: {max_uses_text}",
            reply_markup=promocodes_menu(),
            parse_mode="HTML"
        )
    except Exception as e:
        await message.answer(
            f"❌ Ошибка при добавлении промокода: {html.escape(str(e))}",
            reply_markup=promocodes_menu(),
            parse_mode="HTML"
        )


@router.callback_query(F.data.startswith("admin_promocode_edit_") & ~F.data.contains("_code_") & ~F.data.contains("_discount_") & ~F.data.contains("_max_uses_") & ~F.data.contains("_toggle_") & ~F.data.contains("_delete_"), AdminFilter())
async def promocode_edit_menu(callback: types.CallbackQuery):
    """Меню редактирования промокода"""
    await callback.answer()
    promocode_id = int(callback.data.split("_")[-1])
    promo = await get_promo_code_by_id(promocode_id)
    
    if not promo:
        await safe_edit_text(callback.message, "❌ Промокод не найден!", reply_markup=promocodes_menu())
        return
    
    status = "✅ Активен" if promo.is_active else "❌ Неактивен"
    text = f"✏️ <b>Редактирование промокода</b>\n\n"
    text += f"ID: {promo.id}\n"
    text += f"Код: <b>{html.escape(promo.code)}</b>\n"
    text += f"Статус: {status}\n"
    text += f"Скидка: {promo.discount_percent:.0f}%\n"
    if promo.max_uses is None:
        text += f"Использований: {promo.current_uses}/∞ (безлимитный)\n"
    else:
        text += f"Использований: {promo.current_uses}/{promo.max_uses}\n"
    text += f"Создан: {promo.created_at.strftime('%d.%m.%Y %H:%M')}\n"
    
    await safe_edit_text(
        callback.message,
        text,
        reply_markup=promocode_edit_keyboard(promocode_id)
    )


# Редактирование кода
@router.callback_query(F.data.startswith("admin_promocode_edit_code_"), AdminFilter())
async def promocode_edit_code_start(callback: types.CallbackQuery, state: FSMContext):
    """Начало редактирования кода"""
    await callback.answer()
    promocode_id = int(callback.data.split("_")[-1])
    await state.update_data(promocode_id=promocode_id)
    await safe_edit_text(
        callback.message,
        "Введите новый код промокода:",
        reply_markup=cancel_keyboard()
    )
    await state.set_state(EditPromoCodeStates.waiting_code)


@router.message(EditPromoCodeStates.waiting_code, AdminFilter())
async def promocode_edit_code(message: types.Message, state: FSMContext):
    """Редактирование кода"""
    code = message.text.strip().upper()
    if not code:
        await message.answer("❌ Код не может быть пустым. Введите код промокода:", reply_markup=cancel_keyboard())
        return
    
    # Проверяем, существует ли уже такой промокод (кроме текущего)
    from utils.db import get_promo_code_by_code
    existing = await get_promo_code_by_code(code)
    data = await state.get_data()
    if existing and existing.id != data["promocode_id"]:
        await message.answer("❌ Промокод с таким кодом уже существует. Введите другой код:", reply_markup=cancel_keyboard())
        return
    
    promo = await update_promo_code(data["promocode_id"], code=code)
    await state.clear()
    
    if promo:
        await message.answer(
            f"✅ Код изменен на: <b>{html.escape(promo.code)}</b>",
            reply_markup=promocode_edit_keyboard(promo.id),
            parse_mode="HTML"
        )
    else:
        await message.answer("❌ Ошибка при обновлении промокода", reply_markup=promocodes_menu())


# Редактирование скидки
@router.callback_query(F.data.startswith("admin_promocode_edit_discount_"), AdminFilter())
async def promocode_edit_discount_start(callback: types.CallbackQuery, state: FSMContext):
    """Начало редактирования скидки"""
    await callback.answer()
    promocode_id = int(callback.data.split("_")[-1])
    await state.update_data(promocode_id=promocode_id)
    await safe_edit_text(
        callback.message,
        "Введите новый процент скидки (от 0 до 100):",
        reply_markup=cancel_keyboard()
    )
    await state.set_state(EditPromoCodeStates.waiting_discount)


@router.message(EditPromoCodeStates.waiting_discount, AdminFilter())
async def promocode_edit_discount(message: types.Message, state: FSMContext):
    """Редактирование скидки"""
    try:
        discount = float(message.text.replace(",", "."))
        if discount < 0 or discount > 100:
            await message.answer("❌ Скидка должна быть от 0 до 100. Введите процент скидки:", reply_markup=cancel_keyboard())
            return
        
        data = await state.get_data()
        promo = await update_promo_code(data["promocode_id"], discount_percent=discount)
        await state.clear()
        
        if promo:
            await message.answer(
                f"✅ Скидка изменена на: <b>{promo.discount_percent:.0f}%</b>",
                reply_markup=promocode_edit_keyboard(promo.id),
                parse_mode="HTML"
            )
        else:
            await message.answer("❌ Ошибка при обновлении промокода", reply_markup=promocodes_menu())
    except ValueError:
        await message.answer("❌ Неверный формат. Введите число от 0 до 100:", reply_markup=cancel_keyboard())


# Редактирование лимита использований
@router.callback_query(F.data.startswith("admin_promocode_edit_max_uses_"), AdminFilter())
async def promocode_edit_max_uses_start(callback: types.CallbackQuery, state: FSMContext):
    """Начало редактирования лимита использований"""
    await callback.answer()
    promocode_id = int(callback.data.split("_")[-1])
    await state.update_data(promocode_id=promocode_id)
    await safe_edit_text(
        callback.message,
        "Введите новое максимальное количество использований:\n"
        "• Число (например: 100) - для промокода с лимитом\n"
        "• 0 или 'unlimited' - для безлимитного промокода",
        reply_markup=cancel_keyboard()
    )
    await state.set_state(EditPromoCodeStates.waiting_max_uses)


@router.message(EditPromoCodeStates.waiting_max_uses, AdminFilter())
async def promocode_edit_max_uses(message: types.Message, state: FSMContext):
    """Редактирование лимита использований"""
    text_input = message.text.strip().lower()
    max_uses = None
    
    # Проверяем, является ли ввод запросом на безлимитный промокод
    if text_input in ["0", "unlimited", "безлимит", "∞"]:
        max_uses = None  # Безлимитный промокод
    else:
        try:
            max_uses = int(text_input)
            if max_uses < 1:
                await message.answer("❌ Количество использований должно быть больше 0. Введите число или 0 для безлимитного:", reply_markup=cancel_keyboard())
                return
        except ValueError:
            await message.answer("❌ Неверный формат. Введите целое число или 0/unlimited для безлимитного:", reply_markup=cancel_keyboard())
            return
    
    data = await state.get_data()
    promo = await update_promo_code(data["promocode_id"], max_uses=max_uses)
    await state.clear()
    
    if promo:
        if max_uses is None:
            max_uses_text = "∞ (безлимитный)"
        else:
            max_uses_text = str(promo.max_uses)
        await message.answer(
            f"✅ Лимит использований изменен на: <b>{max_uses_text}</b>",
            reply_markup=promocode_edit_keyboard(promo.id),
            parse_mode="HTML"
        )
    else:
        await message.answer("❌ Ошибка при обновлении промокода", reply_markup=promocodes_menu())


# Переключение статуса
@router.callback_query(F.data.startswith("admin_promocode_toggle_"), AdminFilter())
async def promocode_toggle(callback: types.CallbackQuery):
    """Переключение статуса промокода"""
    await callback.answer()
    promocode_id = int(callback.data.split("_")[-1])
    promo = await get_promo_code_by_id(promocode_id)
    
    if not promo:
        await safe_edit_text(callback.message, "❌ Промокод не найден!", reply_markup=promocodes_menu())
        return
    
    new_status = not promo.is_active
    promo = await update_promo_code(promocode_id, is_active=new_status)
    
    if promo:
        status_text = "активирован" if new_status else "деактивирован"
        await safe_edit_text(
            callback.message,
            f"✅ Промокод <b>{html.escape(promo.code)}</b> {status_text}",
            reply_markup=promocode_edit_keyboard(promocode_id)
        )
    else:
        await safe_edit_text(callback.message, "❌ Ошибка при обновлении промокода", reply_markup=promocodes_menu())


# Удаление промокода
@router.callback_query(F.data.startswith("admin_promocode_delete_"), AdminFilter())
async def promocode_delete(callback: types.CallbackQuery):
    """Удаление промокода"""
    await callback.answer()
    promocode_id = int(callback.data.split("_")[-1])
    promo = await get_promo_code_by_id(promocode_id)
    
    if not promo:
        await safe_edit_text(callback.message, "❌ Промокод не найден!", reply_markup=promocodes_menu())
        return
    
    deleted = await delete_promo_code(promocode_id)
    if deleted:
        await safe_edit_text(
            callback.message,
            f"✅ Промокод <b>{html.escape(promo.code)}</b> удален",
            reply_markup=promocodes_menu()
        )
    else:
        await safe_edit_text(callback.message, "❌ Ошибка при удалении промокода", reply_markup=promocodes_menu())


# Обработка отмены
@router.message(F.text == "❌ Отмена", AdminFilter())
async def cancel_message_handler(message: types.Message, state: FSMContext):
    """Обработчик кнопки отмены для всех состояний"""
    await state.clear()
    try:
        await message.delete()
    except:
        pass
    await message.answer(
        "❌ Операция отменена",
        reply_markup=promocodes_menu()
    )

