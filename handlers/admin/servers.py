from aiogram import F, Router, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.exceptions import TelegramBadRequest
from utils.filters import AdminFilter, SimpleEditServerFilter
from utils.message_utils import safe_callback_answer
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
    get_location_by_id,
    get_users_with_subscriptions_by_server
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
    waiting_location_id = State()
    waiting_description = State()
    waiting_max_users = State()
    waiting_payment_days = State()
    waiting_sub_url = State()


class NotifyUsersStates(StatesGroup):
    waiting_message = State()
    waiting_max_users = State()


class EditServerStates(StatesGroup):
    waiting_name = State()
    waiting_description = State()
    waiting_api_url = State()
    waiting_api_username = State()
    waiting_api_password = State()
    waiting_ssl_certificate = State()
    waiting_max_users = State()
    waiting_payment_days = State()
    waiting_sub_url = State()


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
    await safe_callback_answer(callback)
    await safe_edit_text(
        callback.message,
        "🔧 <b>Админ-панель</b>\n\n"
        "Выберите раздел для управления:",
        reply_markup=admin_menu()
    )


# Управление серверами
@router.callback_query(F.data == "admin_servers", AdminFilter())
async def servers_menu_callback(callback: types.CallbackQuery):
    await safe_callback_answer(callback)
    await safe_edit_text(
        callback.message,
        "🖥️ <b>Управление серверами</b>\n\n"
        "Выберите действие:",
        reply_markup=servers_menu()
    )


# Список серверов
@router.callback_query(F.data == "admin_server_list", AdminFilter())
async def server_list_callback(callback: types.CallbackQuery):
    await safe_callback_answer(callback)
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
    await safe_callback_answer(callback)
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
    await safe_callback_answer(callback)
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
    
    await state.update_data(max_users=max_users)
    await message.answer(
        "Введите количество дней, на которое куплен сервер (число или '-' чтобы пропустить):\n\n"
        "💡 Это нужно для напоминания об оплате сервера",
        reply_markup=cancel_keyboard()
    )
    await state.set_state(AddServerStates.waiting_payment_days)


@router.message(AddServerStates.waiting_payment_days, AdminFilter())
async def server_add_payment_days(message: types.Message, state: FSMContext):
    payment_days = None
    if message.text != "-":
        try:
            payment_days = int(message.text)
            if payment_days <= 0:
                await message.answer("❌ Количество дней должно быть больше 0. Введите число или '-' чтобы пропустить:")
                return
        except ValueError:
            await message.answer("❌ Неверный формат. Введите число или '-' чтобы пропустить:")
            return
    
    await state.update_data(payment_days=payment_days)
    await message.answer(
        "Введите URL для генерации ссылок подписки (формат: http://example.com/sub или '-' чтобы пропустить):\n\n"
        "💡 Это начало ссылки на подписку, к которому будет добавлен /{subID}\n"
        "Пример: http://example.com/sub → http://example.com/sub/{subID}",
        reply_markup=cancel_keyboard()
    )
    await state.set_state(AddServerStates.waiting_sub_url)


@router.message(AddServerStates.waiting_sub_url, AdminFilter())
async def server_add_sub_url(message: types.Message, state: FSMContext):
    sub_url = None
    if message.text != "-":
        sub_url = message.text.strip()
        # Проверяем, что URL заканчивается без слеша (если есть, убираем)
        if sub_url.endswith('/'):
            sub_url = sub_url[:-1]
    
    data = await state.get_data()
    await state.clear()
    
    try:
        server = await create_server(
            name=data["name"],
            api_url=data["api_url"],
            api_username=data["api_username"],
            api_password=data["api_password"],
            location_id=data["location_id"],
            description=data.get("description"),
            max_users=data.get("max_users"),
            payment_days=data.get("payment_days"),
            sub_url=sub_url
        )
        location = await get_location_by_id(data["location_id"])
        location_name = location.name if location else "Неизвестно"
        
        expire_info = ""
        if server.payment_expire_date:
            from datetime import datetime
            expire_date_str = server.payment_expire_date.strftime("%d.%m.%Y")
            expire_info = f"\n📅 Оплата до: {expire_date_str}"
        
        await message.answer(
            f"✅ <b>Сервер успешно добавлен!</b>\n\n"
            f"ID: {server.id}\n"
            f"Название: {html.escape(server.name)}\n"
            f"Локация: {html.escape(location_name)}{expire_info}",
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
    await safe_callback_answer(callback)
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
    await safe_callback_answer(callback)
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
    await safe_callback_answer(callback)
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
    await safe_callback_answer(callback)
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
    await safe_callback_answer(callback)
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
    await safe_callback_answer(callback)
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
    await safe_callback_answer(callback)
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


# Изменение SSL сертификата
@router.callback_query(F.data.startswith("admin_server_edit_ssl_cert_"), AdminFilter())
async def server_edit_ssl_cert_start(callback: types.CallbackQuery, state: FSMContext):
    await safe_callback_answer(callback)
    server_id = int(callback.data.split("_")[-1])
    server = await get_server_by_id(server_id)
    if not server:
        await safe_edit_text(callback.message, "❌ Сервер не найден!", reply_markup=servers_menu())
        return
    
    current_cert = server.ssl_certificate if server.ssl_certificate else "не установлен"
    cert_preview = current_cert[:100] + "..." if current_cert != "не установлен" and len(current_cert) > 100 else current_cert
    await state.update_data(server_id=server_id)
    await safe_edit_text(
        callback.message,
        f"Введите SSL сертификат (.crt) в формате PEM:\n\n"
        f"Текущий статус: {'✅ Установлен' if server.ssl_certificate else '❌ Не установлен'}\n\n"
        f"Вы можете:\n"
        f"• Отправить файл сертификата (.crt, .pem, .cer)\n"
        f"• Отправить текст сертификата\n"
        f"• Отправить '-' чтобы удалить",
        reply_markup=cancel_keyboard(),
        parse_mode="HTML"
    )
    await state.set_state(EditServerStates.waiting_ssl_certificate)


@router.message(EditServerStates.waiting_ssl_certificate, F.document, AdminFilter())
async def server_edit_ssl_certificate_file(message: types.Message, state: FSMContext):
    """Обработка файла сертификата"""
    from core.loader import bot
    
    data = await state.get_data()
    server_id = data["server_id"]
    
    try:
        # Получаем информацию о файле
        document = message.document
        file_id = document.file_id
        file_name = document.file_name or "certificate"
        
        # Проверяем расширение файла
        if not (file_name.endswith('.crt') or file_name.endswith('.pem') or file_name.endswith('.cer')):
            await message.answer(
                "⚠️ Файл должен иметь расширение .crt, .pem или .cer\n"
                "Попробуйте еще раз или отправьте текст сертификата:",
                reply_markup=cancel_keyboard()
            )
            return
        
        # Скачиваем файл
        file_info = await bot.get_file(file_id)
        
        # Проверяем размер файла (максимум 10 КБ для сертификата)
        if file_info.file_size > 10 * 1024:
            await message.answer(
                "❌ Файл слишком большой. Сертификат должен быть меньше 10 КБ.\n"
                "Попробуйте еще раз или отправьте текст сертификата:",
                reply_markup=cancel_keyboard()
            )
            return
        
        # Скачиваем содержимое файла
        file_content = await bot.download_file(file_info.file_path)
        ssl_certificate = file_content.read().decode('utf-8').strip()
        
        # Проверяем, что это PEM сертификат
        if not (ssl_certificate.startswith("-----BEGIN") and "CERTIFICATE" in ssl_certificate):
            await message.answer(
                "⚠️ Файл не содержит валидный PEM сертификат.\n"
                "Сертификат должен начинаться с '-----BEGIN CERTIFICATE-----'\n"
                "Попробуйте еще раз или отправьте текст сертификата:",
                reply_markup=cancel_keyboard()
            )
            return
        
        # Сохраняем сертификат
        server = await update_server(server_id, ssl_certificate=ssl_certificate)
        await state.clear()
        
        if server:
            await message.answer(
                f"✅ SSL сертификат успешно установлен из файла <code>{html.escape(file_name)}</code>",
                reply_markup=server_edit_keyboard(server.id),
                parse_mode="HTML"
            )
        else:
            await message.answer("❌ Ошибка при обновлении сервера", reply_markup=servers_menu())
            
    except UnicodeDecodeError:
        await message.answer(
            "❌ Ошибка: файл должен быть в текстовом формате (UTF-8).\n"
            "Попробуйте еще раз или отправьте текст сертификата:",
            reply_markup=cancel_keyboard()
        )
    except Exception as e:
        logger.error(f"Ошибка при обработке файла сертификата: {e}")
        await message.answer(
            f"❌ Ошибка при обработке файла: {html.escape(str(e))}\n"
            "Попробуйте еще раз или отправьте текст сертификата:",
            reply_markup=cancel_keyboard(),
            parse_mode="HTML"
        )


@router.message(EditServerStates.waiting_ssl_certificate, AdminFilter())
async def server_edit_ssl_certificate(message: types.Message, state: FSMContext):
    data = await state.get_data()
    
    # Проверяем, нужно ли подтверждение
    if data.get("need_confirm"):
        if message.text.lower() not in ["да", "yes", "y"]:
            await state.clear()
            await message.answer("❌ Операция отменена", reply_markup=servers_menu())
            return
        # Используем сохраненный сертификат
        ssl_certificate = data.get("ssl_certificate_temp")
    else:
        # Обрабатываем новый ввод
        if message.text == "-":
            ssl_certificate = None
        else:
            ssl_certificate = message.text.strip()
            # Проверяем, что это похоже на PEM сертификат
            if ssl_certificate and not (ssl_certificate.startswith("-----BEGIN") or "CERTIFICATE" in ssl_certificate):
                await message.answer(
                    "⚠️ Предупреждение: Сертификат не похож на PEM формат.\n"
                    "Продолжить? (Отправьте 'да' для подтверждения или другое сообщение для отмены):",
                    reply_markup=cancel_keyboard()
                )
                # Сохраняем сертификат во временное хранилище для подтверждения
                await state.update_data(ssl_certificate_temp=ssl_certificate, need_confirm=True)
                return
    
    server_id = data["server_id"]
    server = await update_server(server_id, ssl_certificate=ssl_certificate)
    await state.clear()
    
    if server:
        status_text = "✅ Установлен" if server.ssl_certificate else "❌ Удален"
        await message.answer(
            f"✅ SSL сертификат {status_text.lower()}",
            reply_markup=server_edit_keyboard(server.id),
            parse_mode="HTML"
        )
    else:
        await message.answer("❌ Ошибка при обновлении сервера", reply_markup=servers_menu())


# Проверка соединения с сервером
@router.callback_query(F.data.startswith("admin_server_test_connection_"), AdminFilter())
async def server_test_connection(callback: types.CallbackQuery):
    """Проверка соединения с API сервера"""
    await safe_callback_answer(callback)
    server_id = int(callback.data.split("_")[-1])
    server = await get_server_by_id(server_id)
    
    if not server:
        await safe_edit_text(callback.message, "❌ Сервер не найден!", reply_markup=servers_menu())
        return
    
    # Показываем сообщение о начале проверки
    await safe_edit_text(
        callback.message,
        f"🔍 <b>Проверка соединения</b>\n\n"
        f"Сервер: <b>{html.escape(server.name)}</b>\n"
        f"API URL: <code>{html.escape(server.api_url)}</code>\n\n"
        f"⏳ Выполняется проверка...",
        reply_markup=None,
        parse_mode="HTML"
    )
    
    try:
        from services.x3ui_api import get_x3ui_client
        
        # Создаем клиент API
        x3ui_client = get_x3ui_client(
            server.api_url,
            server.api_username,
            server.api_password,
            server.ssl_certificate
        )
        
        # Пытаемся выполнить login (самый простой запрос)
        login_success = await x3ui_client.login()
        
        if login_success:
            # Если login успешен, пробуем получить список inbounds для более полной проверки
            inbounds = await x3ui_client.get_inbounds()
            inbound_count = len(inbounds) if inbounds else 0
            
            await safe_edit_text(
                callback.message,
                f"✅ <b>Соединение успешно!</b>\n\n"
                f"Сервер: <b>{html.escape(server.name)}</b>\n"
                f"API URL: <code>{html.escape(server.api_url)}</code>\n"
                f"Username: <code>{html.escape(server.api_username)}</code>\n\n"
                f"📊 Статус:\n"
                f"• Аутентификация: ✅ Успешно\n"
                f"• Доступ к API: ✅ Работает\n"
                f"• Найдено inbounds: {inbound_count}\n"
                f"{'• SSL сертификат: ✅ Используется' if server.ssl_certificate else '• SSL сертификат: ❌ Не установлен'}",
                reply_markup=server_edit_keyboard(server_id),
                parse_mode="HTML"
            )
        else:
            await safe_edit_text(
                callback.message,
                f"❌ <b>Ошибка соединения</b>\n\n"
                f"Сервер: <b>{html.escape(server.name)}</b>\n"
                f"API URL: <code>{html.escape(server.api_url)}</code>\n"
                f"Username: <code>{html.escape(server.api_username)}</code>\n\n"
                f"⚠️ Не удалось выполнить аутентификацию.\n\n"
                f"Возможные причины:\n"
                f"• Неверный URL сервера\n"
                f"• Неверные учетные данные\n"
                f"• Сервер недоступен\n"
                f"• Проблемы с SSL сертификатом\n\n"
                f"Проверьте настройки сервера.",
                reply_markup=server_edit_keyboard(server_id),
                parse_mode="HTML"
            )
        
        # Закрываем сессию
        await x3ui_client.close()
        
    except Exception as e:
        logger.error(f"Ошибка при проверке соединения с сервером {server_id}: {e}")
        import traceback
        logger.error(traceback.format_exc())
        
        error_message = str(e)
        # Обрезаем длинные сообщения об ошибках
        if len(error_message) > 200:
            error_message = error_message[:200] + "..."
        
        await safe_edit_text(
            callback.message,
            f"❌ <b>Ошибка при проверке соединения</b>\n\n"
            f"Сервер: <b>{html.escape(server.name)}</b>\n"
            f"API URL: <code>{html.escape(server.api_url)}</code>\n\n"
            f"⚠️ Ошибка: <code>{html.escape(error_message)}</code>\n\n"
            f"Возможные причины:\n"
            f"• Сервер недоступен\n"
            f"• Неверный формат URL\n"
            f"• Проблемы с SSL сертификатом\n"
            f"• Таймаут соединения",
            reply_markup=server_edit_keyboard(server_id),
            parse_mode="HTML"
        )


# Изменение максимального количества пользователей
@router.callback_query(F.data.startswith("admin_server_edit_max_users_"), AdminFilter())
async def server_edit_max_users_start(callback: types.CallbackQuery, state: FSMContext):
    await safe_callback_answer(callback)
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


# Изменение периода оплаты сервера
@router.callback_query(F.data.startswith("admin_server_edit_payment_days_"), AdminFilter())
async def server_edit_payment_days_start(callback: types.CallbackQuery, state: FSMContext):
    await safe_callback_answer(callback)
    server_id = int(callback.data.split("_")[-1])
    server = await get_server_by_id(server_id)
    if not server:
        await safe_edit_text(callback.message, "❌ Сервер не найден!", reply_markup=servers_menu())
        return
    
    current_info = ""
    if server.payment_days:
        current_info = f"\n\nТекущий период: {server.payment_days} дн."
    if server.payment_expire_date:
        from datetime import datetime
        expire_date_str = server.payment_expire_date.strftime("%d.%m.%Y")
        current_info += f"\nТекущая дата окончания: {expire_date_str}"
    
    await state.update_data(server_id=server_id)
    await safe_edit_text(
        callback.message,
        f"Введите количество дней, на которое куплен сервер (число или '-' чтобы удалить):{current_info}",
        reply_markup=cancel_keyboard()
    )
    await state.set_state(EditServerStates.waiting_payment_days)


@router.message(EditServerStates.waiting_payment_days, AdminFilter())
async def server_edit_payment_days(message: types.Message, state: FSMContext):
    from datetime import datetime, timedelta
    
    payment_days = None
    payment_expire_date = None
    
    if message.text != "-":
        try:
            payment_days = int(message.text)
            if payment_days <= 0:
                await message.answer(
                    "❌ Количество дней должно быть больше 0. Введите число или '-' чтобы удалить:",
                    reply_markup=cancel_keyboard()
                )
                return
            # Вычисляем новую дату окончания от текущего момента
            payment_expire_date = datetime.utcnow() + timedelta(days=payment_days)
        except ValueError:
            await message.answer(
                "❌ Неверный формат. Введите число или '-' чтобы удалить:",
                reply_markup=cancel_keyboard()
            )
            return
    
    data = await state.get_data()
    server = await update_server(
        data["server_id"],
        payment_days=payment_days,
        payment_expire_date=payment_expire_date
    )
    await state.clear()
    
    if server:
        if payment_days:
            expire_date_str = payment_expire_date.strftime("%d.%m.%Y")
            await message.answer(
                f"✅ Период оплаты обновлен:\n"
                f"Количество дней: <b>{payment_days}</b>\n"
                f"Дата окончания: <b>{expire_date_str}</b>",
                reply_markup=server_edit_keyboard(server.id),
                parse_mode="HTML"
            )
        else:
            await message.answer(
                "✅ Период оплаты удален",
                reply_markup=server_edit_keyboard(server.id),
                parse_mode="HTML"
            )
    else:
        await message.answer("❌ Ошибка при обновлении сервера", reply_markup=servers_menu())


# Изменение Sub URL
@router.callback_query(F.data.startswith("admin_server_edit_sub_url_"), AdminFilter())
async def server_edit_sub_url_start(callback: types.CallbackQuery, state: FSMContext):
    await safe_callback_answer(callback)
    server_id = int(callback.data.split("_")[-1])
    server = await get_server_by_id(server_id)
    if not server:
        await safe_edit_text(callback.message, "❌ Сервер не найден!", reply_markup=servers_menu())
        return
    
    current_info = ""
    if server.sub_url:
        current_info = f"\n\nТекущий URL: <code>{html.escape(server.sub_url)}</code>"
    
    await state.update_data(server_id=server_id)
    await safe_edit_text(
        callback.message,
        f"Введите URL для генерации ссылок подписки (формат: http://example.com/sub или '-' чтобы удалить):{current_info}\n\n"
        f"💡 Это начало ссылки на подписку, к которому будет добавлен /{{subID}}\n"
        f"Пример: http://example.com/sub → http://example.com/sub/{{subID}}",
        reply_markup=cancel_keyboard(),
        parse_mode="HTML"
    )
    await state.set_state(EditServerStates.waiting_sub_url)


@router.message(EditServerStates.waiting_sub_url, AdminFilter())
async def server_edit_sub_url(message: types.Message, state: FSMContext):
    sub_url = None
    if message.text != "-":
        sub_url = message.text.strip()
        # Проверяем, что URL заканчивается без слеша (если есть, убираем)
        if sub_url.endswith('/'):
            sub_url = sub_url[:-1]
    
    data = await state.get_data()
    server = await update_server(data["server_id"], sub_url=sub_url)
    await state.clear()
    
    if server:
        sub_url_text = server.sub_url if server.sub_url else "не указан (будет использован шаблон по IP)"
        await message.answer(
            f"✅ Sub URL изменен на: <b>{html.escape(sub_url_text)}</b>",
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
    await safe_callback_answer(callback)
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
    
    # Показываем информацию об оплате
    if server.payment_expire_date:
        from datetime import datetime
        expire_date_str = server.payment_expire_date.strftime("%d.%m.%Y")
        days_left = (server.payment_expire_date - datetime.utcnow()).days
        if days_left > 0:
            text += f"\n💰 Оплата до: {expire_date_str} (осталось {days_left} дн.)\n"
        elif days_left == 0:
            text += f"\n⚠️ Оплата истекает сегодня: {expire_date_str}\n"
        else:
            text += f"\n❌ Оплата истекла: {expire_date_str} ({abs(days_left)} дн. назад)\n"
    elif server.payment_days:
        text += f"\n💰 Период оплаты: {server.payment_days} дн. (дата окончания не установлена)\n"
    else:
        text += f"\n💰 Период оплаты: не указан\n"
        
    # Показываем API URL и информацию о подключении
    text += f"\n🔗 API URL: {html.escape(server.api_url)}\n"
    text += f"👤 Username: {html.escape(server.api_username)}\n"
    text += f"🔐 Password: {'*' * len(server.api_password)}\n"
    if server.sub_url:
        text += f"📋 Sub URL: {html.escape(server.sub_url)}\n"
    else:
        text += f"📋 Sub URL: не указан (будет использован шаблон по IP)\n"

    await safe_edit_text(callback.message, text, reply_markup=server_edit_keyboard(server_id))


# Уведомление пользователей о работах на сервере
@router.callback_query(F.data.startswith("admin_server_notify_users_"), AdminFilter())
async def server_notify_users_start(callback: types.CallbackQuery, state: FSMContext):
    """Начало процесса отправки уведомлений пользователям сервера"""
    await safe_callback_answer(callback)
    server_id = int(callback.data.split("_")[-1])
    server = await get_server_by_id(server_id)
    
    if not server:
        await safe_edit_text(callback.message, "❌ Сервер не найден!", reply_markup=servers_menu())
        return
    
    # Получаем количество пользователей с подписками на этом сервере
    users = await get_users_with_subscriptions_by_server(server_id)
    users_count = len(users)
    
    if users_count == 0:
        await safe_callback_answer(callback, "⚠️ На этом сервере нет пользователей с подписками", show_alert=True)
        return
    
    # Сохраняем server_id в состоянии
    await state.update_data(server_id=server_id, users_count=users_count)
    
    text = f"📢 <b>Уведомление пользователей сервера</b>\n\n"
    text += f"Сервер: <b>{html.escape(server.name)}</b>\n"
    text += f"Пользователей с подписками: <b>{users_count}</b>\n\n"
    text += "Введите сообщение для отправки пользователям:\n\n"
    text += "💡 <i>Можно указать о проводимых работах, проблемах с подключением или необходимости обновить подписку</i>"
    
    await safe_edit_text(callback.message, text, reply_markup=cancel_keyboard())
    await state.set_state(NotifyUsersStates.waiting_message)


@router.message(NotifyUsersStates.waiting_message, AdminFilter())
async def server_notify_users_send(message: types.Message, state: FSMContext):
    """Отправка уведомлений пользователям"""
    data = await state.get_data()
    server_id = data.get("server_id")
    users_count = data.get("users_count", 0)
    
    if not server_id:
        await message.answer("❌ Ошибка: сервер не найден", reply_markup=servers_menu())
        await state.clear()
        return
    
    server = await get_server_by_id(server_id)
    if not server:
        await message.answer("❌ Сервер не найден", reply_markup=servers_menu())
        await state.clear()
        return
    
    notification_text = message.text
    
    # Получаем всех пользователей с подписками на этом сервере
    users = await get_users_with_subscriptions_by_server(server_id)
    
    if not users:
        await message.answer("❌ На этом сервере нет пользователей с подписками", reply_markup=servers_menu())
        await state.clear()
        return
    
    # Формируем сообщение для пользователей
    location_name = server.location.name if server.location else "локации"
    user_message = f"🔔 <b>Уведомление о локации {html.escape(location_name)}</b>\n\n"
    user_message += f"{notification_text}"
    
    # Отправляем сообщения пользователям
    from core.loader import bot
    sent_count = 0
    failed_count = 0
    
    await message.answer(f"📤 Отправка уведомлений {users_count} пользователям...")
    
    for user in users:
        try:
            await bot.send_message(
                chat_id=int(user.tg_id),
                text=user_message,
                parse_mode="HTML"
            )
            sent_count += 1
        except Exception as e:
            logger.error(f"❌ Ошибка при отправке уведомления пользователю {user.tg_id}: {e}")
            failed_count += 1
    
    # Отправляем отчет администратору
    result_text = f"✅ <b>Уведомления отправлены</b>\n\n"
    result_text += f"Сервер: <b>{html.escape(server.name)}</b>\n"
    result_text += f"Всего пользователей: <b>{users_count}</b>\n"
    result_text += f"✅ Отправлено: <b>{sent_count}</b>\n"
    if failed_count > 0:
        result_text += f"❌ Ошибок: <b>{failed_count}</b>\n"
    
    await message.answer(result_text, reply_markup=servers_menu())
    await state.clear()
    
    # Возвращаемся к меню редактирования сервера
    await server_edit_menu_after_update(message, server_id)


# Обработка отмены (должна быть после всех состояний)
# Этот обработчик обрабатывает только отмены для серверов
# Отмены для других модулей обрабатываются в соответствующих файлах
@router.callback_query(F.data == "cancel", AdminFilter())
async def cancel_handler(callback: types.CallbackQuery, state: FSMContext):
    current_state = await state.get_state()
    
    # Пропускаем состояния рассылки - они обрабатываются в dashboard.py
    if current_state and "BroadcastStates" in current_state:
        return
    
    # Проверяем, что мы находимся в состоянии, связанном с серверами
    server_states = [
        AddServerStates.waiting_name,
        AddServerStates.waiting_api_url,
        AddServerStates.waiting_api_username,
        AddServerStates.waiting_api_password,
        AddServerStates.waiting_location_id,
        AddServerStates.waiting_description,
        AddServerStates.waiting_max_users,
        AddServerStates.waiting_payment_days,
        AddServerStates.waiting_sub_url,
        EditServerStates.waiting_name,
        EditServerStates.waiting_description,
        EditServerStates.waiting_api_url,
        EditServerStates.waiting_api_username,
        EditServerStates.waiting_api_password,
        EditServerStates.waiting_ssl_certificate,
        EditServerStates.waiting_sub_url,
        EditServerStates.waiting_max_users,
        EditServerStates.waiting_payment_days,
        NotifyUsersStates.waiting_message,
    ]
    
    # Если состояние не связано с серверами, пропускаем обработку
    if current_state not in [str(s) for s in server_states]:
        return
    
    # Обрабатываем отмену для состояний серверов
    if current_state == NotifyUsersStates.waiting_message:
        data = await state.get_data()
        server_id = data.get("server_id")
        await state.clear()
        await safe_callback_answer(callback)
        if server_id:
            await server_edit_menu_after_update(callback, server_id)
        else:
            await safe_edit_text(callback.message, "❌ Операция отменена", reply_markup=servers_menu())
        return
    
    # Для всех остальных состояний серверов возвращаемся в меню серверов
    await safe_callback_answer(callback)
    await state.clear()
    await safe_edit_text(
        callback.message,
        "❌ Операция отменена",
        reply_markup=servers_menu()
    )


@router.message(F.text == "❌ Отмена", AdminFilter())
async def cancel_message_handler(message: types.Message, state: FSMContext):
    current_state = await state.get_state()
    
    # Проверяем, что мы находимся в состоянии, связанном с серверами
    server_states = [
        AddServerStates.waiting_name,
        AddServerStates.waiting_api_url,
        AddServerStates.waiting_api_username,
        AddServerStates.waiting_api_password,
        AddServerStates.waiting_location_id,
        AddServerStates.waiting_description,
        AddServerStates.waiting_max_users,
        AddServerStates.waiting_payment_days,
        AddServerStates.waiting_sub_url,
        EditServerStates.waiting_name,
        EditServerStates.waiting_description,
        EditServerStates.waiting_api_url,
        EditServerStates.waiting_api_username,
        EditServerStates.waiting_api_password,
        EditServerStates.waiting_ssl_certificate,
        EditServerStates.waiting_sub_url,
        EditServerStates.waiting_max_users,
        EditServerStates.waiting_payment_days,
        NotifyUsersStates.waiting_message,
    ]
    
    # Если состояние не связано с серверами, пропускаем обработку
    if current_state not in [str(s) for s in server_states]:
        return
    
    # Обрабатываем отмену для состояний серверов
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
    await safe_callback_answer(callback)
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
    await safe_callback_answer(callback)
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
    await safe_callback_answer(callback)
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
    
    # Показываем информацию об оплате
    if server.payment_expire_date:
        from datetime import datetime
        expire_date_str = server.payment_expire_date.strftime("%d.%m.%Y")
        days_left = (server.payment_expire_date - datetime.utcnow()).days
        if days_left > 0:
            text += f"\n💰 Оплата до: {expire_date_str} (осталось {days_left} дн.)\n"
        elif days_left == 0:
            text += f"\n⚠️ Оплата истекает сегодня: {expire_date_str}\n"
        else:
            text += f"\n❌ Оплата истекла: {expire_date_str} ({abs(days_left)} дн. назад)\n"
    elif server.payment_days:
        text += f"\n💰 Период оплаты: {server.payment_days} дн. (дата окончания не установлена)\n"
    else:
        text += f"\n💰 Период оплаты: не указан\n"
    
    # Показываем API URL и информацию о подключении
    text += f"\n🔗 API URL: {html.escape(server.api_url)}\n"
    text += f"👤 Username: {html.escape(server.api_username)}\n"
    text += f"🔐 Password: {'*' * len(server.api_password)}\n"
    if server.sub_url:
        text += f"📋 Sub URL: {html.escape(server.sub_url)}\n"
    else:
        text += f"📋 Sub URL: не указан (будет использован шаблон по IP)\n"
    text += f"🔒 SSL Сертификат: {'✅ Установлен' if server.ssl_certificate else '❌ Не установлен'}\n"
    
    # Если это callback, редактируем сообщение
    if isinstance(message_or_callback, types.CallbackQuery):
        await safe_edit_text(message_or_callback.message, text, reply_markup=server_edit_keyboard(server_id))
    # Если это message, отправляем новое сообщение
    elif isinstance(message_or_callback, types.Message):
        await message_or_callback.answer(text, reply_markup=server_edit_keyboard(server_id))

