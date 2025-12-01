from aiogram import F, Router, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.exceptions import TelegramBadRequest
from utils.filters import AdminFilter, SimpleEditServerFilter
import html
import logging

logger = logging.getLogger(__name__)
from utils.keyboards.admin_kb import (
    admin_menu,
    servers_menu,
    server_list_keyboard,
    server_edit_keyboard,
    confirm_delete_keyboard,
    cancel_keyboard
)
from utils.db import (
    get_all_servers,
    get_server_by_id,
    create_server,
    update_server,
    delete_server,
    get_all_locations,
    get_location_by_id
)

router = Router()


async def safe_edit_text(message: types.Message, text: str, reply_markup=None, parse_mode="HTML"):
    """Безопасное редактирование сообщения с обработкой ошибки 'message is not modified'"""
    try:
        await message.edit_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
    except TelegramBadRequest as e:
        # Игнорируем ошибку, если сообщение не изменилось
        if "message is not modified" not in str(e).lower():
            raise


class AddServerStates(StatesGroup):
    waiting_name = State()
    waiting_api_url = State()
    waiting_api_username = State()
    waiting_api_password = State()
    waiting_pbk = State()
    waiting_location_id = State()
    waiting_description = State()
    waiting_max_users = State()


class EditServerStates(StatesGroup):
    waiting_name = State()
    waiting_description = State()
    waiting_api_url = State()
    waiting_api_username = State()
    waiting_api_password = State()
    waiting_pbk = State()
    waiting_max_users = State()


# Главное меню админ-панели
@router.message(Command("admin"), AdminFilter())
async def admin_menu_handler(message: types.Message):
    await message.answer(
        "🔧 <b>Админ-панель</b>\n\n"
        "Выберите раздел для управления:",
        reply_markup=admin_menu()
    )


@router.callback_query(F.data == "admin_menu", AdminFilter())
async def admin_menu_callback(callback: types.CallbackQuery):
    await callback.answer()
    await safe_edit_text(
        callback.message,
        "🔧 <b>Админ-панель</b>\n\n"
        "Выберите раздел для управления:",
        reply_markup=admin_menu()
    )


# Управление серверами
@router.callback_query(F.data == "admin_servers", AdminFilter())
async def servers_menu_callback(callback: types.CallbackQuery):
    await callback.answer()
    await safe_edit_text(
        callback.message,
        "🖥️ <b>Управление серверами</b>\n\n"
        "Выберите действие:",
        reply_markup=servers_menu()
    )


# Список серверов
@router.callback_query(F.data == "admin_server_list", AdminFilter())
async def server_list_callback(callback: types.CallbackQuery):
    await callback.answer()
    servers = await get_all_servers()
    
    if not servers:
        await safe_edit_text(
            callback.message,
            "📋 <b>Список серверов</b>\n\n"
            "Серверы не найдены. Добавьте первый сервер!",
            reply_markup=servers_menu()
        )
        return
    
    text = "📋 <b>Список серверов</b>\n\n"
    for server in servers:
        status = "✅ Активен" if server.is_active else "❌ Неактивен"
        text += f"{status} <b>{html.escape(server.name)}</b>\n"
        if server.location:
            text += f"   🌍 Локация: {html.escape(server.location.name)} ({server.location.price:.0f} ₽)\n"
        text += f"   👥 Пользователей: {server.current_users}"
        if server.max_users:
            text += f" / {server.max_users}"
        text += "\n\n"
    
    await safe_edit_text(callback.message, text, reply_markup=server_list_keyboard(servers))


# Добавление сервера
@router.callback_query(F.data == "admin_server_add", AdminFilter())
async def server_add_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    await safe_edit_text(
        callback.message,
        "➕ <b>Добавление нового сервера</b>\n\n"
        "Введите название сервера:",
        reply_markup=cancel_keyboard()
    )
    await state.set_state(AddServerStates.waiting_name)


@router.message(AddServerStates.waiting_name, AdminFilter())
async def server_add_name(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text)
    await message.answer(
        "Введите API URL сервера:",
        reply_markup=cancel_keyboard()
    )
    await state.set_state(AddServerStates.waiting_api_url)


@router.message(AddServerStates.waiting_api_url, AdminFilter())
async def server_add_api_url(message: types.Message, state: FSMContext):
    api_url = message.text.strip()
    
    # Используем URL как есть, БЕЗ парсинга (сохраняем WebBasePath)
    await state.update_data(api_url=api_url)
    await message.answer(
        "Введите имя пользователя:",
        reply_markup=cancel_keyboard()
    )
    await state.set_state(AddServerStates.waiting_api_username)




@router.message(AddServerStates.waiting_api_username, AdminFilter())
async def server_add_api_username(message: types.Message, state: FSMContext):
    await state.update_data(api_username=message.text)
    await message.answer(
        "Введите пароль:",
        reply_markup=cancel_keyboard()
    )
    await state.set_state(AddServerStates.waiting_api_password)


@router.message(AddServerStates.waiting_api_password, AdminFilter())
async def server_add_api_password(message: types.Message, state: FSMContext):
    await state.update_data(api_password=message.text)
    await message.answer(
        "Введите Public Key (PBK) для Reality:",
        reply_markup=cancel_keyboard()
    )
    await state.set_state(AddServerStates.waiting_pbk)


@router.message(AddServerStates.waiting_pbk, AdminFilter())
async def server_add_pbk(message: types.Message, state: FSMContext):
    await state.update_data(pbk=message.text)
    # Показываем список локаций для выбора
    locations = await get_all_locations()
    if not locations:
        await message.answer(
            "❌ Нет доступных локаций. Сначала создайте локацию в разделе управления локациями.",
            reply_markup=cancel_keyboard()
        )
        return
    
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    kb = InlineKeyboardBuilder()
    for location in locations:
        kb.button(
            text=f"🌍 {location.name} - {location.price:.0f} ₽",
            callback_data=f"admin_server_select_location_{location.id}"
        )
    kb.adjust(1)
    
    await message.answer(
        "Выберите локацию для сервера:",
        reply_markup=kb.as_markup()
    )


@router.callback_query(F.data.startswith("admin_server_select_location_"), AdminFilter())
async def server_add_location_selected(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    location_id = int(callback.data.split("_")[-1])
    await state.update_data(location_id=location_id)
    await callback.message.answer(
        "Введите описание сервера (или отправьте '-' чтобы пропустить):",
        reply_markup=cancel_keyboard()
    )
    await state.set_state(AddServerStates.waiting_description)


@router.message(AddServerStates.waiting_description, AdminFilter())
async def server_add_description(message: types.Message, state: FSMContext):
    description = message.text if message.text != "-" else None
    await state.update_data(description=description)
    await message.answer(
        "Введите максимальное количество пользователей (число или '-' чтобы пропустить):",
        reply_markup=cancel_keyboard()
    )
    await state.set_state(AddServerStates.waiting_max_users)


@router.message(AddServerStates.waiting_max_users, AdminFilter())
async def server_add_max_users(message: types.Message, state: FSMContext):
    max_users = None
    if message.text != "-":
        try:
            max_users = int(message.text)
        except ValueError:
            await message.answer("❌ Неверный формат. Введите число или '-' чтобы пропустить:")
            return
    
    data = await state.get_data()
    await state.clear()
    
    try:
        server = await create_server(
            name=data["name"],
            api_url=data["api_url"],
            api_username=data["api_username"],
            api_password=data["api_password"],
            pbk=data.get("pbk"),
            location_id=data["location_id"],
            description=data.get("description"),
            max_users=max_users
        )
        location = await get_location_by_id(data["location_id"])
        location_name = location.name if location else "Неизвестно"
        await message.answer(
            f"✅ <b>Сервер успешно добавлен!</b>\n\n"
            f"ID: {server.id}\n"
            f"Название: {html.escape(server.name)}\n"
            f"Локация: {html.escape(location_name)}",
            reply_markup=servers_menu(),
            parse_mode="HTML"
        )
    except Exception as e:
        await message.answer(
            f"❌ Ошибка при добавлении сервера: {html.escape(str(e))}",
            reply_markup=servers_menu(),
            parse_mode="HTML"
        )


# Изменение названия
@router.callback_query(F.data.startswith("admin_server_edit_name_"), AdminFilter())
async def server_edit_name_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    server_id = int(callback.data.split("_")[-1])
    await state.update_data(server_id=server_id)
    await safe_edit_text(
        callback.message,
        "Введите новое название сервера:",
        reply_markup=cancel_keyboard()
    )
    await state.set_state(EditServerStates.waiting_name)


@router.message(EditServerStates.waiting_name, AdminFilter())
async def server_edit_name(message: types.Message, state: FSMContext):
    data = await state.get_data()
    server = await update_server(data["server_id"], name=message.text)
    await state.clear()
    
    if server:
        await message.answer(
            f"✅ Название изменено на: <b>{html.escape(server.name)}</b>",
            reply_markup=server_edit_keyboard(server.id),
            parse_mode="HTML"
        )
    else:
        await message.answer("❌ Ошибка при обновлении сервера", reply_markup=servers_menu())


# Цена теперь хранится в локации, редактирование цены удалено


# Изменение локации
@router.callback_query(F.data.startswith("admin_server_edit_location_"), AdminFilter())
async def server_edit_location_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    server_id = int(callback.data.split("_")[-1])
    await state.update_data(server_id=server_id)
    
    # Показываем список локаций для выбора
    locations = await get_all_locations()
    if not locations:
        await safe_edit_text(
            callback.message,
            "❌ Нет доступных локаций. Сначала создайте локацию.",
            reply_markup=server_edit_keyboard(server_id)
        )
        return
    
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    kb = InlineKeyboardBuilder()
    for location in locations:
        kb.button(
            text=f"🌍 {location.name} - {location.price:.0f} ₽",
            callback_data=f"admin_server_set_location_{server_id}_{location.id}"
        )
    kb.button(text="🔙 Назад", callback_data=f"admin_server_edit_{server_id}")
    kb.adjust(1)
    
    await safe_edit_text(
        callback.message,
        "Выберите новую локацию для сервера:",
        reply_markup=kb.as_markup()
    )


@router.callback_query(F.data.startswith("admin_server_set_location_"), AdminFilter())
async def server_edit_location_selected(callback: types.CallbackQuery):
    await callback.answer()
    parts = callback.data.split("_")
    server_id = int(parts[-2])
    location_id = int(parts[-1])
    
    server = await update_server(server_id, location_id=location_id)
    
    if server:
        location = await get_location_by_id(location_id)
        location_name = location.name if location else "Неизвестно"
        await server_edit_menu_after_update(callback, server_id)
    else:
        await safe_edit_text(
            callback.message,
            "❌ Ошибка при обновлении локации сервера",
            reply_markup=server_edit_keyboard(server_id)
        )


# Изменение описания
@router.callback_query(F.data.startswith("admin_server_edit_description_"), AdminFilter())
async def server_edit_description_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    server_id = int(callback.data.split("_")[-1])
    await state.update_data(server_id=server_id)
    await safe_edit_text(
        callback.message,
        "Введите новое описание (или '-' чтобы удалить):",
        reply_markup=cancel_keyboard()
    )
    await state.set_state(EditServerStates.waiting_description)


@router.message(EditServerStates.waiting_description, AdminFilter())
async def server_edit_description(message: types.Message, state: FSMContext):
    description = message.text if message.text != "-" else None
    data = await state.get_data()
    server = await update_server(data["server_id"], description=description)
    await state.clear()
    
    if server:
        desc_text = server.description if server.description else "не указано"
        await message.answer(
            f"✅ Описание изменено на: <b>{html.escape(desc_text)}</b>",
            reply_markup=server_edit_keyboard(server.id),
            parse_mode="HTML"
        )
    else:
        await message.answer("❌ Ошибка при обновлении сервера", reply_markup=servers_menu())


# Изменение API URL
@router.callback_query(F.data.startswith("admin_server_edit_api_url_"), AdminFilter())
async def server_edit_api_url_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    server_id = int(callback.data.split("_")[-1])
    server = await get_server_by_id(server_id)
    await state.update_data(server_id=server_id)
    
    current_url = server.api_url if server else ""
    await safe_edit_text(
        callback.message,
        f"Введите API URL:\n\n"
        f"Текущий: <code>{html.escape(current_url)}</code>",
        reply_markup=cancel_keyboard(),
        parse_mode="HTML"
    )
    await state.set_state(EditServerStates.waiting_api_url)


@router.message(EditServerStates.waiting_api_url, AdminFilter())
async def server_edit_api_url(message: types.Message, state: FSMContext):
    api_url = message.text.strip()
    
    # Используем URL как есть, БЕЗ парсинга
    data = await state.get_data()
    server = await update_server(data["server_id"], api_url=api_url)
    await state.clear()
    
    if server:
        await message.answer(
            f"✅ API URL изменен на:\n<code>{html.escape(server.api_url)}</code>",
            reply_markup=server_edit_keyboard(server.id),
            parse_mode="HTML"
        )
    else:
        await message.answer("❌ Ошибка при обновлении сервера", reply_markup=servers_menu())


# Изменение API Username
@router.callback_query(F.data.startswith("admin_server_edit_api_username_"), AdminFilter())
async def server_edit_api_username_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    server_id = int(callback.data.split("_")[-1])
    server = await get_server_by_id(server_id)
    if not server:
        await safe_edit_text(callback.message, "❌ Сервер не найден!", reply_markup=servers_menu())
        return
    
    current_username = server.api_username if server else ""
    await state.update_data(server_id=server_id)
    await safe_edit_text(
        callback.message,
        f"Введите имя пользователя (Username):\n\n"
        f"Текущий: <code>{html.escape(current_username)}</code>",
        reply_markup=cancel_keyboard(),
        parse_mode="HTML"
    )
    await state.set_state(EditServerStates.waiting_api_username)


@router.message(EditServerStates.waiting_api_username, AdminFilter())
async def server_edit_api_username(message: types.Message, state: FSMContext):
    api_username = message.text.strip()
    data = await state.get_data()
    server = await update_server(data["server_id"], api_username=api_username)
    await state.clear()
    
    if server:
        await message.answer(
            f"✅ Username изменен на:\n<code>{html.escape(server.api_username)}</code>",
            reply_markup=server_edit_keyboard(server.id),
            parse_mode="HTML"
        )
    else:
        await message.answer("❌ Ошибка при обновлении сервера", reply_markup=servers_menu())


# Изменение API Password
@router.callback_query(F.data.startswith("admin_server_edit_api_password_"), AdminFilter())
async def server_edit_api_password_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    server_id = int(callback.data.split("_")[-1])
    server = await get_server_by_id(server_id)
    if not server:
        await safe_edit_text(callback.message, "❌ Сервер не найден!", reply_markup=servers_menu())
        return
    
    await state.update_data(server_id=server_id)
    await safe_edit_text(
        callback.message,
        "Введите пароль (Password):",
        reply_markup=cancel_keyboard()
    )
    await state.set_state(EditServerStates.waiting_api_password)


@router.message(EditServerStates.waiting_api_password, AdminFilter())
async def server_edit_api_password(message: types.Message, state: FSMContext):
    api_password = message.text.strip()
    data = await state.get_data()
    server = await update_server(data["server_id"], api_password=api_password)
    await state.clear()
    
    if server:
        await message.answer(
            f"✅ Password изменен",
            reply_markup=server_edit_keyboard(server.id),
            parse_mode="HTML"
        )
    else:
        await message.answer("❌ Ошибка при обновлении сервера", reply_markup=servers_menu())


# Изменение PBK
@router.callback_query(F.data.startswith("admin_server_edit_pbk_"), AdminFilter())
async def server_edit_pbk_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    server_id = int(callback.data.split("_")[-1])
    server = await get_server_by_id(server_id)
    if not server:
        await safe_edit_text(callback.message, "❌ Сервер не найден!", reply_markup=servers_menu())
        return
    
    current_pbk = server.pbk if server.pbk else "не установлен"
    await state.update_data(server_id=server_id)
    await safe_edit_text(
        callback.message,
        f"Введите Public Key (PBK) для Reality:\n\n"
        f"Текущий: <code>{html.escape(current_pbk)}</code>",
        reply_markup=cancel_keyboard(),
        parse_mode="HTML"
    )
    await state.set_state(EditServerStates.waiting_pbk)


@router.message(EditServerStates.waiting_pbk, AdminFilter())
async def server_edit_pbk(message: types.Message, state: FSMContext):
    pbk = message.text.strip()
    data = await state.get_data()
    server = await update_server(data["server_id"], pbk=pbk)
    await state.clear()
    
    if server:
        await message.answer(
            f"✅ PBK изменен на:\n<code>{html.escape(server.pbk or 'не установлен')}</code>",
            reply_markup=server_edit_keyboard(server.id),
            parse_mode="HTML"
        )
    else:
        await message.answer("❌ Ошибка при обновлении сервера", reply_markup=servers_menu())


# Изменение максимального количества пользователей
@router.callback_query(F.data.startswith("admin_server_edit_max_users_"), AdminFilter())
async def server_edit_max_users_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    server_id = int(callback.data.split("_")[-1])
    await state.update_data(server_id=server_id)
    await safe_edit_text(
        callback.message,
        "Введите максимальное количество пользователей (число или '-' чтобы удалить):",
        reply_markup=cancel_keyboard()
    )
    await state.set_state(EditServerStates.waiting_max_users)


@router.message(EditServerStates.waiting_max_users, AdminFilter())
async def server_edit_max_users(message: types.Message, state: FSMContext):
    max_users = None
    if message.text != "-":
        try:
            max_users = int(message.text)
        except ValueError:
            await message.answer(
                "❌ Неверный формат. Введите число или '-' чтобы удалить:",
                reply_markup=cancel_keyboard()
            )
            return
    
    data = await state.get_data()
    server = await update_server(data["server_id"], max_users=max_users)
    await state.clear()
    
    if server:
        max_text = str(server.max_users) if server.max_users else "не ограничено"
        await message.answer(
            f"✅ Максимальное количество пользователей изменено на: <b>{html.escape(max_text)}</b>",
            reply_markup=server_edit_keyboard(server.id),
            parse_mode="HTML"
        )
    else:
        await message.answer("❌ Ошибка при обновлении сервера", reply_markup=servers_menu())


# Редактирование сервера (должен быть ПОСЛЕ всех специфичных обработчиков)
# Обрабатывает только callback_data вида "admin_server_edit_{id}" (только число после edit_)
@router.callback_query(SimpleEditServerFilter(), AdminFilter())
async def server_edit_menu(callback: types.CallbackQuery):
    """Обработчик для открытия меню редактирования сервера (только для admin_server_edit_{id})"""
    await callback.answer()
    server_id = int(callback.data.split("_")[-1])
    server = await get_server_by_id(server_id)
    
    if not server:
        await safe_edit_text(callback.message, "❌ Сервер не найден!", reply_markup=servers_menu())
        return
    
    status = "✅ Активен" if server.is_active else "❌ Неактивен"
    text = f"✏️ <b>Редактирование сервера</b>\n\n"
    text += f"ID: {server.id}\n"
    text += f"Название: {html.escape(server.name)}\n"
    text += f"Статус: {status}\n"
    if server.location:
        text += f"Локация: {html.escape(server.location.name)} ({server.location.price:.0f} ₽)\n"
    else:
        text += f"Локация: не указана\n"
    text += f"Пользователей: {server.current_users}"
    if server.max_users:
        text += f" / {server.max_users}"
    text += "\n"
    if server.description:
        text += f"Описание: {html.escape(server.description)}\n"
        
    # Показываем API URL и информацию о подключении
    text += f"\n🔗 API URL: {html.escape(server.api_url)}\n"
    text += f"👤 Username: {html.escape(server.api_username)}\n"
    text += f"🔐 Password: {'*' * len(server.api_password)}\n"

    await safe_edit_text(callback.message, text, reply_markup=server_edit_keyboard(server_id))


# Обработка отмены (должна быть после всех состояний)
# Этот обработчик обрабатывает только отмены для серверов
# Отмены для users.py обрабатываются в handlers/admin/users.py
@router.callback_query(F.data == "cancel", AdminFilter())
async def cancel_handler(callback: types.CallbackQuery, state: FSMContext):
    # Проверяем, не находится ли пользователь в состоянии из users.py
    # Если да, то пропускаем этот обработчик (он обработается в users.py)
    from handlers.admin.users import SendMessageStates, SearchUserStates, CreateSubscriptionStates
    current_state = await state.get_state()
    if current_state in [SendMessageStates.waiting_message, SearchUserStates.waiting_query, CreateSubscriptionStates.waiting_location]:
        # Пропускаем обработку, пусть обработает users.py
        return
    
    await callback.answer()
    await state.clear()
    await safe_edit_text(
        callback.message,
        "❌ Операция отменена",
        reply_markup=servers_menu()
    )


@router.message(F.text == "❌ Отмена", AdminFilter())
async def cancel_message_handler(message: types.Message, state: FSMContext):
    await state.clear()
    try:
        await message.delete()
    except:
        pass
    await message.answer(
        "❌ Операция отменена",
        reply_markup=servers_menu()
    )


# Переключение статуса
@router.callback_query(F.data.startswith("admin_server_toggle_"), AdminFilter())
async def server_toggle_status(callback: types.CallbackQuery):
    await callback.answer()
    server_id = int(callback.data.split("_")[-1])
    server = await get_server_by_id(server_id)
    
    if not server:
        await safe_edit_text(callback.message, "❌ Сервер не найден!", reply_markup=servers_menu())
        return
    
    new_status = not server.is_active
    updated_server = await update_server(server_id, is_active=new_status)
    
    if updated_server:
        status_text = "активирован" if new_status else "деактивирован"
        # Обновляем информацию о сервере
        await server_edit_menu_after_update(callback, server_id)


# Удаление сервера
# ВАЖНО: Обработчик подтверждения должен быть ПЕРЕД общим обработчиком удаления
@router.callback_query(F.data.startswith("admin_server_delete_confirm_"), AdminFilter())
async def server_delete_execute(callback: types.CallbackQuery):
    """Обработчик подтверждения удаления сервера"""
    await callback.answer()
    server_id = int(callback.data.split("_")[-1])
    server = await get_server_by_id(server_id)
    
    if not server:
        await safe_edit_text(callback.message, "❌ Сервер не найден!", reply_markup=servers_menu())
        return
    
    # Проверяем наличие активных подписок перед удалением
    from database.models import Subscription
    from database.base import async_session
    from sqlalchemy import select
    
    async with async_session() as session:
        result = await session.execute(
            select(Subscription).where(Subscription.server_id == server_id)
        )
        subscriptions = result.scalars().all()
        active_subscriptions = [s for s in subscriptions if s.status == "active"]
    
    if active_subscriptions:
        await safe_edit_text(
            callback.message,
            f"❌ Невозможно удалить сервер <b>{html.escape(server.name)}</b>!\n\n"
            f"⚠️ На сервере есть активные подписки ({len(active_subscriptions)}).\n"
            f"Сначала необходимо деактивировать или удалить все подписки.",
            reply_markup=server_edit_keyboard(server_id),
            parse_mode="HTML"
        )
        return
    
    success = await delete_server(server_id)
    
    if success:
        await safe_edit_text(
            callback.message,
            f"✅ Сервер <b>{html.escape(server.name)}</b> успешно удален!",
            reply_markup=servers_menu(),
            parse_mode="HTML"
        )
    else:
        await safe_edit_text(
            callback.message,
            "❌ Ошибка при удалении сервера!\n\n"
            "Возможные причины:\n"
            "• На сервере есть активные подписки\n"
            "• Сервер не найден",
            reply_markup=servers_menu(),
            parse_mode="HTML"
        )


@router.callback_query(
    F.data.startswith("admin_server_delete_") & 
    ~F.data.startswith("admin_server_delete_confirm_"),
    AdminFilter()
)
async def server_delete_confirm(callback: types.CallbackQuery):
    """Обработчик запроса подтверждения удаления сервера"""
    await callback.answer()
    server_id = int(callback.data.split("_")[-1])
    server = await get_server_by_id(server_id)
    
    if not server:
        await safe_edit_text(callback.message, "❌ Сервер не найден!", reply_markup=servers_menu())
        return
    
    await safe_edit_text(
        callback.message,
        f"⚠️ <b>Подтверждение удаления</b>\n\n"
        f"Вы уверены, что хотите удалить сервер <b>{html.escape(server.name)}</b>?\n\n"
        f"Это действие нельзя отменить!",
        reply_markup=confirm_delete_keyboard(server_id)
    )


# Вспомогательная функция для обновления меню после редактирования
async def server_edit_menu_after_update(message_or_callback, server_id: int):
    """Обновить меню редактирования сервера после изменения"""
    server = await get_server_by_id(server_id)
    if not server:
        return
    
    status = "✅ Активен" if server.is_active else "❌ Неактивен"
    text = f"✏️ <b>Редактирование сервера</b>\n\n"
    text += f"ID: {server.id}\n"
    text += f"Название: {html.escape(server.name)}\n"
    text += f"Статус: {status}\n"
    if server.location:
        text += f"Локация: {html.escape(server.location.name)} ({server.location.price:.0f} ₽)\n"
    else:
        text += f"Локация: не указана\n"
    text += f"Пользователей: {server.current_users}"
    if server.max_users:
        text += f" / {server.max_users}"
    text += "\n"
    if server.description:
        text += f"Описание: {html.escape(server.description)}\n"
    # Показываем API URL и информацию о подключении
    text += f"\n🔗 API URL: {html.escape(server.api_url)}\n"
    text += f"👤 Username: {html.escape(server.api_username)}\n"
    text += f"🔐 Password: {'*' * len(server.api_password)}\n"
    
    # Если это callback, редактируем сообщение
    if isinstance(message_or_callback, types.CallbackQuery):
        await safe_edit_text(message_or_callback.message, text, reply_markup=server_edit_keyboard(server_id))
    # Если это message, отправляем новое сообщение
    elif isinstance(message_or_callback, types.Message):
        await message_or_callback.answer(text, reply_markup=server_edit_keyboard(server_id))

