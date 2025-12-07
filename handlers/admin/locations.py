"""
Обработчики для управления локациями в админ-панели
"""
from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.exceptions import TelegramBadRequest
from utils.filters import AdminFilter
from utils.keyboards.admin_kb import admin_menu, cancel_keyboard
from utils.message_utils import safe_callback_answer
import html
from utils.db import (
    get_all_locations,
    get_location_by_id,
    create_location,
    update_location,
    delete_location,
    get_servers_by_location
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


def locations_menu():
    """Меню управления локациями"""
    kb = InlineKeyboardBuilder()
    kb.button(text="➕ Добавить локацию", callback_data="admin_location_add")
    kb.button(text="📋 Список локаций", callback_data="admin_location_list")
    kb.button(text="🔙 Назад", callback_data="admin_menu")
    kb.adjust(1)
    return kb.as_markup()


def location_list_keyboard(locations: list):
    """Клавиатура со списком локаций"""
    kb = InlineKeyboardBuilder()
    for location in locations:
        status = "✅" if location.is_active else "❌"
        hidden = "👁️‍🗨️" if location.is_hidden else ""
        kb.button(
            text=f"{status} {hidden} {location.name} - {location.price:.0f} ₽",
            callback_data=f"admin_location_edit_{location.id}"
        )
    kb.button(text="🔙 Назад", callback_data="admin_locations")
    kb.adjust(1)
    return kb.as_markup()


def location_edit_keyboard(location_id: int):
    """Клавиатура для редактирования локации"""
    kb = InlineKeyboardBuilder()
    kb.button(text="✏️ Изменить название", callback_data=f"admin_location_edit_name_{location_id}")
    kb.button(text="💰 Изменить цену", callback_data=f"admin_location_edit_price_{location_id}")
    kb.button(text="📝 Изменить описание", callback_data=f"admin_location_edit_description_{location_id}")
    kb.button(text="🔄 Переключить статус", callback_data=f"admin_location_toggle_{location_id}")
    kb.button(text="👁️ Переключить видимость", callback_data=f"admin_location_toggle_hidden_{location_id}")
    kb.button(text="🗑️ Удалить локацию", callback_data=f"admin_location_delete_{location_id}")
    kb.button(text="🔙 Назад", callback_data="admin_location_list")
    kb.adjust(2, 2, 1, 1, 1)
    return kb.as_markup()


class AddLocationStates(StatesGroup):
    waiting_name = State()
    waiting_price = State()
    waiting_description = State()


class EditLocationStates(StatesGroup):
    waiting_name = State()
    waiting_price = State()
    waiting_description = State()


@router.callback_query(F.data == "admin_locations", AdminFilter())
async def locations_menu_callback(callback: types.CallbackQuery):
    """Меню управления локациями"""
    await callback.answer()
    await safe_edit_text(
        callback.message,
        "🌍 <b>Управление локациями</b>\n\n"
        "Выберите действие:",
        reply_markup=locations_menu()
    )


@router.callback_query(F.data == "admin_location_list", AdminFilter())
async def location_list_callback(callback: types.CallbackQuery):
    """Список локаций"""
    await callback.answer()
    locations = await get_all_locations()
    
    if not locations:
        await safe_edit_text(
            callback.message,
            "📋 <b>Список локаций</b>\n\n"
            "Локации не найдены. Добавьте первую локацию!",
            reply_markup=locations_menu()
        )
        return
    
    text = "📋 <b>Список локаций</b>\n\n"
    for location in locations:
        status = "✅ Активна" if location.is_active else "❌ Неактивна"
        hidden = "👁️‍🗨️ Скрыта" if location.is_hidden else "👁️ Видима"
        servers = await get_servers_by_location(location.id)
        active_servers = [s for s in servers if s.is_active]
        text += f"{status} | {hidden} <b>{html.escape(location.name)}</b>\n"
        text += f"   💰 Цена: {location.price:.0f} ₽\n"
        text += f"   🖥️ Серверов: {len(active_servers)}/{len(servers)}\n\n"
    
    await safe_edit_text(callback.message, text, reply_markup=location_list_keyboard(locations))


@router.callback_query(F.data == "admin_location_add", AdminFilter())
async def location_add_start(callback: types.CallbackQuery, state: FSMContext):
    """Начало добавления локации"""
    await callback.answer()
    await safe_edit_text(
        callback.message,
        "➕ <b>Добавление новой локации</b>\n\n"
        "Введите название локации:",
        reply_markup=cancel_keyboard()
    )
    await state.set_state(AddLocationStates.waiting_name)


@router.message(AddLocationStates.waiting_name, AdminFilter())
async def location_add_name(message: types.Message, state: FSMContext):
    """Ввод названия локации"""
    await state.update_data(name=message.text)
    await message.answer(
        "Введите цену в рублях (число, например: 100.50):",
        reply_markup=cancel_keyboard()
    )
    await state.set_state(AddLocationStates.waiting_price)


@router.message(AddLocationStates.waiting_price, AdminFilter())
async def location_add_price(message: types.Message, state: FSMContext):
    """Ввод цены локации"""
    try:
        price = float(message.text.replace(",", "."))
        await state.update_data(price=price)
        await message.answer(
            "Введите описание (или отправьте '-' чтобы пропустить):",
            reply_markup=cancel_keyboard()
        )
        await state.set_state(AddLocationStates.waiting_description)
    except ValueError:
        await message.answer("❌ Неверный формат цены. Введите число:")


@router.message(AddLocationStates.waiting_description, AdminFilter())
async def location_add_description(message: types.Message, state: FSMContext):
    """Ввод описания локации"""
    description = message.text if message.text != "-" else None
    await state.update_data(description=description)
    data = await state.get_data()
    await state.clear()
    
    try:
        location = await create_location(
            name=data["name"],
            price=data["price"],
            description=description
        )
        await message.answer(
            f"✅ <b>Локация успешно добавлена!</b>\n\n"
            f"ID: {location.id}\n"
            f"Название: {html.escape(location.name)}\n"
            f"Цена: {location.price:.0f} ₽",
            reply_markup=locations_menu(),
            parse_mode="HTML"
        )
    except Exception as e:
        await message.answer(
            f"❌ Ошибка при добавлении локации: {html.escape(str(e))}",
            reply_markup=locations_menu(),
            parse_mode="HTML"
        )


@router.callback_query(F.data.startswith("admin_location_edit_") & ~F.data.contains("_name_") & ~F.data.contains("_price_") & ~F.data.contains("_description_") & ~F.data.contains("_toggle_") & ~F.data.contains("_toggle_hidden_") & ~F.data.contains("_delete_"), AdminFilter())
async def location_edit_menu(callback: types.CallbackQuery):
    """Меню редактирования локации"""
    await callback.answer()
    location_id = int(callback.data.split("_")[-1])
    location = await get_location_by_id(location_id)
    
    if not location:
        await safe_edit_text(callback.message, "❌ Локация не найдена!", reply_markup=locations_menu())
        return
    
    servers = await get_servers_by_location(location_id)
    active_servers = [s for s in servers if s.is_active]
    
    status = "✅ Активна" if location.is_active else "❌ Неактивна"
    hidden = "👁️‍🗨️ Скрыта" if location.is_hidden else "👁️ Видима"
    text = f"✏️ <b>Редактирование локации</b>\n\n"
    text += f"ID: {location.id}\n"
    text += f"Название: {html.escape(location.name)}\n"
    text += f"Статус: {status}\n"
    text += f"Видимость: {hidden}\n"
    text += f"Цена: {location.price:.0f} ₽\n"
    if location.description:
        text += f"Описание: {html.escape(location.description)}\n"
    text += f"Серверов: {len(active_servers)}/{len(servers)}\n"
    
    await safe_edit_text(
        callback.message,
        text,
        reply_markup=location_edit_keyboard(location_id)
    )


# Редактирование названия
@router.callback_query(F.data.startswith("admin_location_edit_name_"), AdminFilter())
async def location_edit_name_start(callback: types.CallbackQuery, state: FSMContext):
    """Начало редактирования названия"""
    await callback.answer()
    location_id = int(callback.data.split("_")[-1])
    await state.update_data(location_id=location_id)
    await safe_edit_text(
        callback.message,
        "Введите новое название локации:",
        reply_markup=cancel_keyboard()
    )
    await state.set_state(EditLocationStates.waiting_name)


@router.message(EditLocationStates.waiting_name, AdminFilter())
async def location_edit_name(message: types.Message, state: FSMContext):
    """Редактирование названия"""
    data = await state.get_data()
    location = await update_location(data["location_id"], name=message.text)
    await state.clear()
    
    if location:
        await message.answer(
            f"✅ Название изменено на: <b>{html.escape(location.name)}</b>",
            reply_markup=location_edit_keyboard(location.id),
            parse_mode="HTML"
        )
    else:
        await message.answer("❌ Ошибка при обновлении локации", reply_markup=locations_menu())


# Редактирование цены
@router.callback_query(F.data.startswith("admin_location_edit_price_"), AdminFilter())
async def location_edit_price_start(callback: types.CallbackQuery, state: FSMContext):
    """Начало редактирования цены"""
    await callback.answer()
    location_id = int(callback.data.split("_")[-1])
    await state.update_data(location_id=location_id)
    await safe_edit_text(
        callback.message,
        "Введите новую цену в рублях (число, например: 100.50):",
        reply_markup=cancel_keyboard()
    )
    await state.set_state(EditLocationStates.waiting_price)


@router.message(EditLocationStates.waiting_price, AdminFilter())
async def location_edit_price(message: types.Message, state: FSMContext):
    """Редактирование цены"""
    try:
        price = float(message.text.replace(",", "."))
        data = await state.get_data()
        location = await update_location(data["location_id"], price=price)
        await state.clear()
        
        if location:
            await message.answer(
                f"✅ Цена изменена на: <b>{location.price:.0f} ₽</b>",
                reply_markup=location_edit_keyboard(location.id),
                parse_mode="HTML"
            )
        else:
            await message.answer("❌ Ошибка при обновлении локации", reply_markup=locations_menu())
    except ValueError:
        await message.answer("❌ Неверный формат цены. Введите число:", reply_markup=cancel_keyboard())


# Редактирование описания
@router.callback_query(F.data.startswith("admin_location_edit_description_"), AdminFilter())
async def location_edit_description_start(callback: types.CallbackQuery, state: FSMContext):
    """Начало редактирования описания"""
    await callback.answer()
    location_id = int(callback.data.split("_")[-1])
    await state.update_data(location_id=location_id)
    await safe_edit_text(
        callback.message,
        "Введите новое описание (или '-' чтобы удалить):",
        reply_markup=cancel_keyboard()
    )
    await state.set_state(EditLocationStates.waiting_description)


@router.message(EditLocationStates.waiting_description, AdminFilter())
async def location_edit_description(message: types.Message, state: FSMContext):
    """Редактирование описания"""
    description = message.text if message.text != "-" else None
    data = await state.get_data()
    location = await update_location(data["location_id"], description=description)
    await state.clear()
    
    if location:
        desc_text = location.description if location.description else "не указано"
        await message.answer(
            f"✅ Описание изменено на: <b>{html.escape(desc_text)}</b>",
            reply_markup=location_edit_keyboard(location.id),
            parse_mode="HTML"
        )
    else:
        await message.answer("❌ Ошибка при обновлении локации", reply_markup=locations_menu())


# Переключение статуса
@router.callback_query(F.data.startswith("admin_location_toggle_") & ~F.data.contains("_hidden_"), AdminFilter())
async def location_toggle(callback: types.CallbackQuery):
    """Переключение статуса локации"""
    await callback.answer()
    location_id = int(callback.data.split("_")[-1])
    location = await get_location_by_id(location_id)
    
    if not location:
        await safe_edit_text(callback.message, "❌ Локация не найдена!", reply_markup=locations_menu())
        return
    
    new_status = not location.is_active
    location = await update_location(location_id, is_active=new_status)
    
    if location:
        status_text = "активирована" if new_status else "деактивирована"
        await safe_edit_text(
            callback.message,
            f"✅ Локация <b>{html.escape(location.name)}</b> {status_text}",
            reply_markup=location_edit_keyboard(location_id)
        )
    else:
        await safe_edit_text(callback.message, "❌ Ошибка при обновлении локации", reply_markup=locations_menu())


# Переключение статуса скрытости
@router.callback_query(F.data.startswith("admin_location_toggle_hidden_"), AdminFilter())
async def location_toggle_hidden(callback: types.CallbackQuery):
    """Переключение статуса скрытости локации"""
    await callback.answer()
    location_id = int(callback.data.split("_")[-1])
    location = await get_location_by_id(location_id)
    
    if not location:
        await safe_edit_text(callback.message, "❌ Локация не найдена!", reply_markup=locations_menu())
        return
    
    new_hidden_status = not location.is_hidden
    location = await update_location(location_id, is_hidden=new_hidden_status)
    
    if location:
        hidden_text = "скрыта" if new_hidden_status else "отображена"
        await safe_edit_text(
            callback.message,
            f"✅ Локация <b>{html.escape(location.name)}</b> {hidden_text}",
            reply_markup=location_edit_keyboard(location_id)
        )
    else:
        await safe_edit_text(callback.message, "❌ Ошибка при обновлении локации", reply_markup=locations_menu())


# Удаление локации
@router.callback_query(F.data.startswith("admin_location_delete_"), AdminFilter())
async def location_delete(callback: types.CallbackQuery):
    """Удаление локации"""
    await callback.answer()
    location_id = int(callback.data.split("_")[-1])
    location = await get_location_by_id(location_id)
    
    if not location:
        await safe_edit_text(callback.message, "❌ Локация не найдена!", reply_markup=locations_menu())
        return
    
    servers = await get_servers_by_location(location_id)
    if servers:
        await safe_edit_text(
            callback.message,
            f"❌ Невозможно удалить локацию <b>{html.escape(location.name)}</b>!\n\n"
            f"К ней привязано серверов: {len(servers)}\n"
            f"Сначала удалите или переместите все серверы.",
            reply_markup=location_edit_keyboard(location_id)
        )
        return
    
    deleted = await delete_location(location_id)
    if deleted:
        await safe_edit_text(
            callback.message,
            f"✅ Локация <b>{html.escape(location.name)}</b> удалена",
            reply_markup=locations_menu()
        )
    else:
        await safe_edit_text(callback.message, "❌ Ошибка при удалении локации", reply_markup=locations_menu())


# Обработка отмены (должна быть после всех состояний)
@router.callback_query(F.data == "cancel", AdminFilter())
async def cancel_callback_handler(callback: types.CallbackQuery, state: FSMContext):
    """Обработчик кнопки отмены для callback"""
    current_state = await state.get_state()
    
    # Пропускаем состояния рассылки - они обрабатываются в dashboard.py
    if current_state and "BroadcastStates" in current_state:
        return
    
    # Проверяем, что мы находимся в состоянии, связанном с локациями
    location_states = [
        AddLocationStates.waiting_name,
        AddLocationStates.waiting_price,
        AddLocationStates.waiting_description,
        EditLocationStates.waiting_name,
        EditLocationStates.waiting_price,
        EditLocationStates.waiting_description,
    ]
    
    # Если состояние не связано с локациями, пропускаем обработку
    if current_state not in [str(s) for s in location_states]:
        return
    
    # Обрабатываем отмену для состояний локаций
    await safe_callback_answer(callback)
    await state.clear()
    await safe_edit_text(
        callback.message,
        "❌ Операция отменена",
        reply_markup=locations_menu()
    )


@router.message(F.text == "❌ Отмена", AdminFilter())
async def cancel_message_handler(message: types.Message, state: FSMContext):
    """Обработчик кнопки отмены для сообщений"""
    current_state = await state.get_state()
    
    # Проверяем, что мы находимся в состоянии, связанном с локациями
    location_states = [
        AddLocationStates.waiting_name,
        AddLocationStates.waiting_price,
        AddLocationStates.waiting_description,
        EditLocationStates.waiting_name,
        EditLocationStates.waiting_price,
        EditLocationStates.waiting_description,
    ]
    
    # Если состояние не связано с локациями, пропускаем обработку
    if current_state not in [str(s) for s in location_states]:
        return
    
    # Обрабатываем отмену для состояний локаций
    await state.clear()
    try:
        await message.delete()
    except:
        pass
    await message.answer(
        "❌ Операция отменена",
        reply_markup=locations_menu()
    )

