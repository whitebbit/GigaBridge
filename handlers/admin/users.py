from aiogram import F, Router, types
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.filters import or_f
from utils.filters import AdminFilter
from utils.keyboards.admin_kb import (
    admin_menu,
    users_menu,
    user_list_keyboard,
    user_detail_keyboard,
    cancel_keyboard,
    confirm_delete_all_subscriptions_keyboard
)
import html
from utils.db import (
    get_all_users,
    get_user_by_id,
    update_user,
    set_admin,
    get_user_subscriptions,
    get_server_by_id,
    get_location_by_id,
    get_subscription_by_id,
    update_subscription,
    get_subscription_identifier,
    get_user_by_tg_id,
    get_tariff_by_id
)
from services.x3ui_api import get_x3ui_client
from services.subscription import delete_all_user_subscriptions_completely
from database.base import async_session
from database.models import User
from sqlalchemy import select, or_

router = Router()

USERS_PER_PAGE = 5


class SendMessageStates(StatesGroup):
    """Состояния для отправки сообщения пользователю"""
    waiting_message = State()


class SearchUserStates(StatesGroup):
    """Состояния для поиска пользователя"""
    waiting_query = State()


class CreateSubscriptionStates(StatesGroup):
    """Состояния для создания подписки админом"""
    waiting_location = State()


async def safe_edit_text(message: types.Message, text: str, reply_markup=None, parse_mode="HTML"):
    """Безопасное редактирование сообщения с обработкой ошибки 'message is not modified'"""
    try:
        await message.edit_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
    except TelegramBadRequest as e:
        if "message is not modified" not in str(e).lower():
            raise


# Меню управления пользователями
@router.callback_query(F.data == "admin_users", AdminFilter())
async def users_menu_callback(callback: types.CallbackQuery):
    await callback.answer()
    await safe_edit_text(
        callback.message,
        "👥 <b>Управление пользователями</b>\n\n"
        "Выберите действие:",
        reply_markup=users_menu()
    )


# Список пользователей с пагинацией
@router.callback_query(F.data == "admin_user_list", AdminFilter())
async def user_list_callback(callback: types.CallbackQuery):
    await callback.answer()
    await show_users_page(callback.message, page=0)


async def show_users_page(message: types.Message, page: int = 0):
    """Показать страницу списка пользователей"""
    users = await get_all_users()
    
    if not users:
        await safe_edit_text(
            message,
            "👥 <b>Список пользователей</b>\n\n"
            "Пользователи не найдены.",
            reply_markup=users_menu()
        )
        return
    
    total_users = len(users)
    total_pages = (total_users + USERS_PER_PAGE - 1) // USERS_PER_PAGE
    
    if page < 0:
        page = 0
    if page >= total_pages:
        page = total_pages - 1
    
    start_idx = page * USERS_PER_PAGE
    end_idx = start_idx + USERS_PER_PAGE
    page_users = users[start_idx:end_idx]
    
    text = f"👥 <b>Список пользователей</b>\n\n"
    text += f"Всего пользователей: {total_users}\n"
    text += f"Страница {page + 1} из {total_pages}\n\n"
    
    for user in page_users:
        admin_badge = "👑" if user.is_admin else ""
        status_emoji = {
            "active": "✅",
            "paused": "⏸️",
            "expired": "❌"
        }.get(user.status, "❓")
        
        username = user.username or f"ID: {user.tg_id}"
        text += f"{status_emoji} {admin_badge} <b>{html.escape(username)}</b>\n"
        text += f"   ID: {user.id} | TG: {user.tg_id}\n\n"
    
    await safe_edit_text(
        message,
        text,
        reply_markup=user_list_keyboard(page_users, page, total_pages)
    )


# Обработчик пагинации
@router.callback_query(F.data.startswith("admin_users_page_"), AdminFilter())
async def users_page_callback(callback: types.CallbackQuery):
    await callback.answer()
    page = int(callback.data.split("_")[-1])
    await show_users_page(callback.message, page)


# Поиск пользователя
@router.callback_query(F.data == "admin_user_search", AdminFilter())
async def user_search_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    await safe_edit_text(
        callback.message,
        "🔍 <b>Поиск пользователя</b>\n\n"
        "Введите ID пользователя (число) или username (без @):",
        reply_markup=cancel_keyboard()
    )
    await state.set_state(SearchUserStates.waiting_query)


@router.message(SearchUserStates.waiting_query, AdminFilter())
async def user_search_process(message: types.Message, state: FSMContext):
    query = message.text.strip()
    
    if not query:
        await message.answer("❌ Введите ID или username пользователя:")
        return
    
    user = None
    
    # Пробуем найти по ID (число)
    try:
        user_id = int(query)
        user = await get_user_by_id(user_id)
    except ValueError:
        pass
    
    # Если не нашли по ID, ищем по username
    if not user:
        username = query.lstrip('@')
        async with async_session() as session:
            result = await session.execute(
                select(User).where(User.username == username)
            )
            user = result.scalar_one_or_none()
    
    # Если не нашли по username, пробуем по tg_id
    if not user:
        try:
            user = await get_user_by_tg_id(query)
        except:
            pass
    
    if not user:
        await message.answer(
            f"❌ Пользователь не найден по запросу: {html.escape(query)}\n\n"
            "Попробуйте ввести ID или username:",
            reply_markup=cancel_keyboard()
        )
        return
    
    await state.clear()
    # Сразу показываем профиль пользователя для редактирования
    text = await format_user_details_text(user)
    subscriptions = await get_user_subscriptions(user.id)
    await message.answer(
        text,
        reply_markup=user_detail_keyboard(user.id, user.is_admin, subscriptions),
        parse_mode="HTML"
    )


# Вспомогательная функция для форматирования текста деталей пользователя
async def format_user_details_text(user):
    """Форматировать текст деталей пользователя"""
    admin_badge = "👑 Администратор\n" if user.is_admin else ""
    status_text = {
        "active": "✅ Активен",
        "paused": "⏸️ Приостановлен",
        "expired": "❌ Истек"
    }.get(user.status, "❓ Неизвестно")
    
    text = f"👤 <b>Пользователь</b>\n\n"
    username_display = user.username if user.username else 'не указан'
    text += f"@{html.escape(username_display)}\n"
    text += f"ID: {user.id} | TG: {user.tg_id}\n"
    if admin_badge:
        text += f"{admin_badge}"
    text += f"Статус: {status_text}\n"
    
    # Получаем подписки пользователя
    subscriptions = await get_user_subscriptions(user.id)
    
    if subscriptions:
        text += f"\n📦 <b>Подписки: {len(subscriptions)}</b>\n"
    
    return text


# Вспомогательная функция для отображения деталей пользователя
async def show_user_details(message: types.Message, user_id: int):
    """Показать детали пользователя"""
    user = await get_user_by_id(user_id)
    
    if not user:
        await safe_edit_text(message, "❌ Пользователь не найден!", reply_markup=users_menu())
        return
    
    text = await format_user_details_text(user)
    subscriptions = await get_user_subscriptions(user_id)
    
    try:
        await safe_edit_text(message, text, reply_markup=user_detail_keyboard(user_id, user.is_admin, subscriptions))
    except TelegramBadRequest as e:
        if "message is too long" in str(e).lower() or "message_too_long" in str(e).lower():
            # Если все еще слишком длинное, отправляем минимальную версию
            minimal_text = f"👤 <b>Пользователь</b>\n\n"
            username_display = user.username if user.username else 'не указан'
            minimal_text += f"@{html.escape(username_display)}\n"
            minimal_text += f"ID: {user.id}\n"
            if user.is_admin:
                minimal_text += f"👑 Администратор\n"
            status_text = {
                "active": "✅ Активен",
                "paused": "⏸️ Приостановлен",
                "expired": "❌ Истек"
            }.get(user.status, "❓ Неизвестно")
            minimal_text += f"Статус: {status_text}\n"
            minimal_text += f"\n📦 <b>Подписки: {len(subscriptions)}</b>"
            await safe_edit_text(message, minimal_text, reply_markup=user_detail_keyboard(user_id, user.is_admin, subscriptions))
        else:
            raise


# Детали пользователя
@router.callback_query(F.data.startswith("admin_user_view_"), AdminFilter())
async def user_detail_callback(callback: types.CallbackQuery):
    await callback.answer()
    user_id = int(callback.data.split("_")[-1])
    await show_user_details(callback.message, user_id)


# Просмотр деталей подписки
@router.callback_query(F.data.startswith("admin_subscription_view_"), AdminFilter())
async def subscription_view_callback(callback: types.CallbackQuery):
    await callback.answer()
    subscription_id = int(callback.data.split("_")[-1])
    
    subscription = await get_subscription_by_id(subscription_id)
    if not subscription:
        await callback.message.answer("❌ Подписка не найдена!")
        return
    
    # Получаем информацию о подписке
    server = await get_server_by_id(subscription.server_id) if subscription.server_id else None
    location_name = "Неизвестно"
    if server and server.location:
        location_name = server.location.name
    elif server and server.location_id:
        location = await get_location_by_id(server.location_id)
        if location:
            location_name = location.name
    
    subscription_id_display = get_subscription_identifier(subscription, location_name)
    
    status_emoji = {
        "active": "✅",
        "paused": "⏸️",
        "expired": "❌"
    }.get(subscription.status, "❓")
    
    status_text = {
        "active": "Активна",
        "paused": "Приостановлена",
        "expired": "Истекла"
    }.get(subscription.status, "Неизвестно")
    
    from datetime import datetime
    from utils.db import utc_to_moscow
    
    text = f"📦 <b>Подписка {subscription_id_display}</b>\n\n"
    text += f"🌍 Локация: {location_name}\n"
    text += f"Статус: {status_emoji} {status_text}\n"
    
    if subscription.expire_date:
        expire_date_local = utc_to_moscow(subscription.expire_date) if isinstance(subscription.expire_date, datetime) else subscription.expire_date
        expire_str = expire_date_local.strftime("%d.%m.%Y в %H:%M") if isinstance(expire_date_local, datetime) else str(expire_date_local)
        text += f"📅 Окончание: {expire_str}\n"
    
    # Создаем клавиатуру для управления подпиской
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    kb = InlineKeyboardBuilder()
    
    # Кнопка продления подписки
    kb.button(text="⏰ Продлить на срок", callback_data=f"admin_subscription_extend_{subscription_id}")
    
    # Кнопка остановки (без возможности активации)
    if subscription.status == "active":
        kb.button(text="⏸️ Остановить", callback_data=f"admin_subscription_pause_{subscription_id}")
    
    # Кнопка удаления
    kb.button(text="🗑️ Удалить", callback_data=f"admin_subscription_delete_{subscription_id}")
    
    # Кнопка назад
    kb.button(text="🔙 Назад", callback_data=f"admin_user_view_{subscription.user_id}")
    
    kb.adjust(1, 1, 1, 1)
    
    await callback.message.answer(text, reply_markup=kb.as_markup(), parse_mode="HTML")


# Продление подписки
@router.callback_query(F.data.startswith("admin_subscription_extend_"), AdminFilter())
async def subscription_extend_callback(callback: types.CallbackQuery):
    await callback.answer()
    subscription_id = int(callback.data.split("_")[-1])
    
    subscription = await get_subscription_by_id(subscription_id)
    if not subscription:
        await callback.message.answer("❌ Подписка не найдена!")
        return
    
    # Продлеваем подписку автоматически по TEST_MODE
    try:
        from datetime import datetime, timedelta
        from core.config import config
        from handlers.buy.payment import get_subscription_duration
        
        # Получаем длительность подписки в зависимости от TEST_MODE
        tariff = await get_tariff_by_id(subscription.tariff_id) if subscription.tariff_id else None
        if tariff:
            _, duration_timedelta = get_subscription_duration(tariff.duration_days)
        else:
            # Если тарифа нет, используем стандартную длительность
            if config.TEST_MODE:
                duration_timedelta = timedelta(minutes=1)
            else:
                duration_timedelta = timedelta(days=30)
        
        # Определяем новую дату окончания
        if subscription.expire_date and subscription.expire_date > datetime.utcnow():
            # Если подписка еще не истекла, продлеваем от текущей даты окончания
            new_expire_date = subscription.expire_date + duration_timedelta
        else:
            # Если подписка истекла, продлеваем от текущего момента
            new_expire_date = datetime.utcnow() + duration_timedelta
        
        # Обновляем подписку
        await update_subscription(
            subscription_id=subscription_id,
            expire_date=new_expire_date,
            status="active"  # Активируем подписку при продлении
        )
        
        # Если подписка была приостановлена, активируем ее через API
        if subscription.status == "paused" and subscription.x3ui_client_email:
            server = await get_server_by_id(subscription.server_id) if subscription.server_id else None
            if server:
                try:
                    x3ui_client = get_x3ui_client(server.api_url, server.api_username, server.api_password)
                    await x3ui_client.enable_client(subscription.x3ui_client_email)
                    await x3ui_client.close()
                except Exception as e:
                    import logging
                    logger = logging.getLogger(__name__)
                    logger.error(f"❌ Ошибка при активации подписки через API: {e}")
        
        # Определяем текст для отображения длительности
        if config.TEST_MODE:
            duration_text = "1 минуту"
        else:
            duration_text = "30 дней"
        
        await callback.message.answer(
            f"✅ <b>Подписка продлена!</b>\n\n"
            f"📅 Добавлено: {duration_text}\n"
            f"🆔 Подписка #{subscription_id}",
            parse_mode="HTML"
        )
        
        # Обновляем детали подписки
        subscription = await get_subscription_by_id(subscription_id)
        if subscription:
            # Отправляем обновленные детали подписки
            server = await get_server_by_id(subscription.server_id) if subscription.server_id else None
            location_name = "Неизвестно"
            if server and server.location:
                location_name = server.location.name
            elif server and server.location_id:
                location = await get_location_by_id(server.location_id)
                if location:
                    location_name = location.name
            
            subscription_id_display = get_subscription_identifier(subscription, location_name)
            status_emoji = "✅"
            status_text = "Активна"
            
            from utils.db import utc_to_moscow
            
            text = f"📦 <b>Подписка {subscription_id_display}</b>\n\n"
            text += f"🌍 Локация: {location_name}\n"
            text += f"Статус: {status_emoji} {status_text}\n"
            
            if subscription.expire_date:
                expire_date_local = utc_to_moscow(subscription.expire_date) if isinstance(subscription.expire_date, datetime) else subscription.expire_date
                expire_str = expire_date_local.strftime("%d.%m.%Y в %H:%M") if isinstance(expire_date_local, datetime) else str(expire_date_local)
                text += f"📅 Окончание: {expire_str}\n"
            
            from aiogram.utils.keyboard import InlineKeyboardBuilder
            kb = InlineKeyboardBuilder()
            kb.button(text="⏰ Продлить на срок", callback_data=f"admin_subscription_extend_{subscription_id}")
            kb.button(text="⏸️ Остановить", callback_data=f"admin_subscription_pause_{subscription_id}")
            kb.button(text="🗑️ Удалить", callback_data=f"admin_subscription_delete_{subscription_id}")
            kb.button(text="🔙 Назад", callback_data=f"admin_user_view_{subscription.user_id}")
            kb.adjust(1, 1, 1, 1)
            
            await callback.message.answer(text, reply_markup=kb.as_markup(), parse_mode="HTML")
        
    except Exception as e:
        import logging
        import traceback
        logger = logging.getLogger(__name__)
        logger.error(f"❌ Ошибка при продлении подписки: {e}")
        logger.error(traceback.format_exc())
        await callback.message.answer(f"❌ Ошибка при продлении подписки: {e}")


# Остановка подписки
@router.callback_query(F.data.startswith("admin_subscription_pause_"), AdminFilter())
async def subscription_pause_callback(callback: types.CallbackQuery):
    await callback.answer()
    subscription_id = int(callback.data.split("_")[-1])
    
    subscription = await get_subscription_by_id(subscription_id)
    if not subscription:
        await callback.message.answer("❌ Подписка не найдена!")
        return
    
    if not subscription.x3ui_client_email:
        await callback.message.answer("❌ У подписки нет email клиента для управления через API!")
        return
    
    server = await get_server_by_id(subscription.server_id) if subscription.server_id else None
    if not server:
        await callback.message.answer("❌ Сервер не найден!")
        return
    
    try:
        # Отключаем клиента через API
        x3ui_client = get_x3ui_client(server.api_url, server.api_username, server.api_password)
        result = await x3ui_client.disable_client(subscription.x3ui_client_email)
        await x3ui_client.close()
        
        if result and not result.get("error"):
            # Сбрасываем срок подписки в 0 (expire_date = текущее время)
            from datetime import datetime
            await update_subscription(
                subscription_id=subscription_id,
                status="paused",
                expire_date=datetime.utcnow()  # Сбрасываем срок
            )
            await callback.message.answer(f"⏸️ Подписка #{subscription_id} приостановлена! Срок сброшен. Пользователь не сможет активировать ее самостоятельно.")
            # Обновляем детали подписки
            subscription = await get_subscription_by_id(subscription_id)
            if subscription:
                # Отправляем обновленные детали подписки
                server = await get_server_by_id(subscription.server_id) if subscription.server_id else None
                location_name = "Неизвестно"
                if server and server.location:
                    location_name = server.location.name
                elif server and server.location_id:
                    location = await get_location_by_id(server.location_id)
                    if location:
                        location_name = location.name
                
                subscription_id_display = get_subscription_identifier(subscription, location_name)
                status_emoji = "⏸️"
                status_text = "Приостановлена"
                
                from datetime import datetime
                from utils.db import utc_to_moscow
                
                text = f"📦 <b>Подписка {subscription_id_display}</b>\n\n"
                text += f"🌍 Локация: {location_name}\n"
                text += f"Статус: {status_emoji} {status_text}\n"
                
                if subscription.expire_date:
                    expire_date_local = utc_to_moscow(subscription.expire_date) if isinstance(subscription.expire_date, datetime) else subscription.expire_date
                    expire_str = expire_date_local.strftime("%d.%m.%Y в %H:%M") if isinstance(expire_date_local, datetime) else str(expire_date_local)
                    text += f"📅 Окончание: {expire_str}\n"
                
                from aiogram.utils.keyboard import InlineKeyboardBuilder
                kb = InlineKeyboardBuilder()
                kb.button(text="⏰ Продлить на срок", callback_data=f"admin_subscription_extend_{subscription_id}")
                kb.button(text="🗑️ Удалить", callback_data=f"admin_subscription_delete_{subscription_id}")
                kb.button(text="🔙 Назад", callback_data=f"admin_user_view_{subscription.user_id}")
                kb.adjust(1, 1, 1)
                
                await callback.message.answer(text, reply_markup=kb.as_markup(), parse_mode="HTML")
        else:
            error_msg = result.get("message", "Неизвестная ошибка") if result else "Нет ответа от API"
            await callback.message.answer(f"❌ Ошибка при приостановке подписки: {error_msg}")
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"❌ Ошибка при приостановке подписки: {e}")
        await callback.message.answer(f"❌ Ошибка при приостановке подписки: {e}")


# Запуск подписки
@router.callback_query(F.data.startswith("admin_subscription_resume_"), AdminFilter())
async def subscription_resume_callback(callback: types.CallbackQuery):
    await callback.answer()
    subscription_id = int(callback.data.split("_")[-1])
    
    subscription = await get_subscription_by_id(subscription_id)
    if not subscription:
        await callback.message.answer("❌ Подписка не найдена!")
        return
    
    if not subscription.x3ui_client_email:
        await callback.message.answer("❌ У подписки нет email клиента для управления через API!")
        return
    
    server = await get_server_by_id(subscription.server_id) if subscription.server_id else None
    if not server:
        await callback.message.answer("❌ Сервер не найден!")
        return
    
    try:
        # Включаем клиента через API
        x3ui_client = get_x3ui_client(server.api_url, server.api_username, server.api_password)
        result = await x3ui_client.enable_client(subscription.x3ui_client_email)
        await x3ui_client.close()
        
        if result and not result.get("error"):
            # Возобновляем срок подписки (добавляем 30 дней или 1 минуту в зависимости от TEST_MODE)
            from datetime import datetime, timedelta
            from core.config import config
            from handlers.buy.payment import get_subscription_duration
            
            # Получаем длительность подписки
            tariff = await get_tariff_by_id(subscription.tariff_id) if subscription.tariff_id else None
            if tariff:
                _, duration_timedelta = get_subscription_duration(tariff.duration_days)
            else:
                # Если тарифа нет, используем стандартную длительность
                if config.TEST_MODE:
                    duration_timedelta = timedelta(minutes=1)
                else:
                    duration_timedelta = timedelta(days=30)
            
            # Устанавливаем новый срок действия
            new_expire_date = datetime.utcnow() + duration_timedelta
            
            await update_subscription(
                subscription_id=subscription_id,
                status="active",
                expire_date=new_expire_date
            )
            
            duration_text = "1 минуту" if config.TEST_MODE else "30 дней"
            await callback.message.answer(f"✅ Подписка #{subscription_id} активирована! Срок продлен на {duration_text}.")
            # Обновляем детали пользователя
            await show_user_details(callback.message, subscription.user_id)
        else:
            error_msg = result.get("message", "Неизвестная ошибка") if result else "Нет ответа от API"
            await callback.message.answer(f"❌ Ошибка при активации подписки: {error_msg}")
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"❌ Ошибка при активации подписки: {e}")
        await callback.message.answer(f"❌ Ошибка при активации подписки: {e}")


# Удаление подписки
@router.callback_query(F.data.startswith("admin_subscription_delete_"), AdminFilter())
async def subscription_delete_callback(callback: types.CallbackQuery):
    await callback.answer()
    subscription_id = int(callback.data.split("_")[-1])
    
    subscription = await get_subscription_by_id(subscription_id)
    if not subscription:
        await callback.message.answer("❌ Подписка не найдена!")
        return
    
    user_id = subscription.user_id
    
    # Удаляем подписку через сервис (полное удаление из БД и API)
    from services.subscription import delete_subscription_completely
    success, error_message = await delete_subscription_completely(subscription_id)
    
    if success:
        await callback.message.answer(f"✅ Подписка #{subscription_id} успешно удалена!")
        # Возвращаем на профиль пользователя
        await show_user_details(callback.message, user_id)
    else:
        await callback.message.answer(f"❌ Ошибка при удалении подписки: {error_message}")


# Переключение статуса администратора
@router.callback_query(F.data.startswith("admin_user_toggle_admin_"), AdminFilter())
async def user_toggle_admin(callback: types.CallbackQuery):
    await callback.answer()
    user_id = int(callback.data.split("_")[-1])
    user = await get_user_by_id(user_id)
    
    if not user:
        await safe_edit_text(callback.message, "❌ Пользователь не найден!", reply_markup=users_menu())
        return
    
    # Нельзя снять права администратора у самого себя
    if str(user.tg_id) == str(callback.from_user.id):
        subscriptions = await get_user_subscriptions(user_id)
        await safe_edit_text(
            callback.message,
            "❌ Вы не можете изменить свои собственные права администратора!",
            reply_markup=user_detail_keyboard(user_id, user.is_admin, subscriptions)
        )
        return
    
    new_admin_status = not user.is_admin
    updated_user = await set_admin(user.tg_id, new_admin_status)
    
    if updated_user:
        status_text = "назначен администратором" if new_admin_status else "лишен прав администратора"
        # Обновляем информацию о пользователе
        await user_detail_callback(callback)


# Создание подписки админом
@router.callback_query(F.data.startswith("admin_user_create_subscription_"), AdminFilter())
async def create_subscription_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    user_id = int(callback.data.split("_")[-1])
    
    user = await get_user_by_id(user_id)
    if not user:
        await callback.message.answer("❌ Пользователь не найден!")
        return
    
    # Получаем список активных локаций
    from utils.db import get_active_locations
    locations = await get_active_locations()
    
    if not locations:
        await callback.message.answer("❌ Нет доступных локаций!")
        return
    
    # Сохраняем user_id в state
    await state.update_data(target_user_id=user_id)
    
    # Создаем клавиатуру для выбора локации
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    kb = InlineKeyboardBuilder()
    for location in locations:
        kb.button(
            text=f"🌍 {location.name}",
            callback_data=f"admin_create_sub_location_{location.id}"
        )
    kb.button(text="❌ Отмена", callback_data=f"admin_user_view_{user_id}")
    kb.adjust(1)
    
    await safe_edit_text(
        callback.message,
        f"➕ <b>Выдача подписки пользователю</b>\n\n"
        f"👤 Пользователь: @{html.escape(user.username or f'ID: {user.tg_id}')}\n\n"
        f"Выберите локацию:",
        reply_markup=kb.as_markup()
    )
    await state.set_state(CreateSubscriptionStates.waiting_location)


@router.callback_query(F.data.startswith("admin_create_sub_location_"), CreateSubscriptionStates.waiting_location, AdminFilter())
async def create_subscription_location_selected(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    location_id = int(callback.data.split("_")[-1])
    
    state_data = await state.get_data()
    user_id = state_data.get("target_user_id")
    
    if not user_id:
        await callback.message.answer("❌ Ошибка: данные пользователя не найдены.")
        await state.clear()
        return
    
    # Получаем данные
    user = await get_user_by_id(user_id)
    location = await get_location_by_id(location_id)
    
    if not user or not location:
        await callback.message.answer("❌ Ошибка: пользователь или локация не найдены!")
        await state.clear()
        return
    
    # Выбираем доступный сервер из локации
    from utils.db import select_available_server_for_location
    server = await select_available_server_for_location(location_id)
    
    if not server:
        await callback.message.answer("❌ Нет доступных серверов в этой локации!")
        await state.clear()
        return
    
    # Получаем первый доступный тариф (или стандартный тариф локации)
    from database.models import Tariff
    from database.base import async_session
    from sqlalchemy import select
    
    async with async_session() as session:
        result = await session.execute(select(Tariff).order_by(Tariff.id).limit(1))
        tariff = result.scalar_one_or_none()
    
    if not tariff:
        await callback.message.answer("❌ Нет доступных тарифов!")
        await state.clear()
        return
    
    # Определяем длительность подписки в зависимости от TEST_MODE
    from core.config import config
    from handlers.buy.payment import get_subscription_duration
    from datetime import datetime, timedelta
    
    # Используем стандартную длительность тарифа для определения дней
    days_for_api, duration_timedelta = get_subscription_duration(tariff.duration_days)
    
    # Создаем подписку
    try:
        from services.x3ui_api import get_x3ui_client
        from utils.db import create_subscription, update_server_current_users
        import uuid as uuid_lib
        
        # Создаем клиента в 3x-ui
        x3ui_client = get_x3ui_client(server.api_url, server.api_username, server.api_password)
        
        # Генерируем уникальный email
        unique_id = str(uuid_lib.uuid4())[:8]
        if user.username:
            client_email = f"{user.username}_{unique_id}"
        else:
            client_email = f"user_{user.tg_id}_{unique_id}"
        
        # Определяем дни для API (0 = без ограничения)
        api_days = 0  # Без ограничения по времени в API
        
        # Добавляем клиента в 3x-ui
        add_result = await x3ui_client.add_client(
            email=client_email,
            days=api_days,
            tg_id=str(user.tg_id),
            limit_ip=3
        )
        
        if not add_result or (isinstance(add_result, dict) and add_result.get("error")):
            error_msg = add_result.get("message", "Неизвестная ошибка") if isinstance(add_result, dict) else "Ошибка API"
            await x3ui_client.close()
            await callback.message.answer(f"❌ Ошибка при создании клиента в 3x-ui: {error_msg}")
            await state.clear()
            return
        
        # Получаем client_id
        x3ui_client_id = None
        if isinstance(add_result, dict):
            x3ui_client_id = add_result.get("client_id") or add_result.get("id")
        
        if not x3ui_client_id:
            client_info = await x3ui_client.get_client_by_email(client_email)
            if client_info:
                x3ui_client_id = client_info.get("id") or client_email
        
        if not x3ui_client_id:
            x3ui_client_id = client_email
        
        # Получаем VLESS ссылку
        x3ui_subscription_link = await x3ui_client.get_client_vless_link(
            client_email=client_email,
            client_username=client_email,
            server_pbk=server.pbk
        )
        
        if not x3ui_subscription_link:
            x3ui_subscription_link = await x3ui_client.get_client_subscription_link(client_email)
        
        await x3ui_client.close()
        
        # Создаем подписку в БД
        expire_date = datetime.utcnow() + duration_timedelta
        subscription = await create_subscription(
            user_id=user_id,
            server_id=server.id,
            tariff_id=tariff.id,
            x3ui_client_id=x3ui_subscription_link,
            x3ui_client_email=client_email,
            status="active",
            expire_date=expire_date,
            traffic_limit=tariff.traffic_limit
        )
        
        # Обновляем счетчик пользователей на сервере
        await update_server_current_users(server.id)
        
        # Определяем текст для отображения длительности
        if config.TEST_MODE:
            duration_text = "1 минута (тестовый режим)"
        else:
            duration_text = f"{tariff.duration_days} дней"
        
        await callback.message.answer(
            f"✅ <b>Подписка успешно выдана!</b>\n\n"
            f"👤 Пользователь: @{html.escape(user.username or f'ID: {user.tg_id}')}\n"
            f"🌍 Локация: {location.name}\n"
            f"📦 Тариф: {tariff.name}\n"
            f"📅 Длительность: {duration_text}\n"
            f"🆔 Подписка #{subscription.id}",
            parse_mode="HTML"
        )
        
        # Отправляем уведомление пользователю
        try:
            from core.loader import bot
            from utils.db import utc_to_moscow
            from datetime import datetime
            
            subscription_id_display = get_subscription_identifier(subscription, location.name)
            
            user_message = f"✅ <b>Вам выдана подписка!</b>\n\n"
            user_message += f"📦 <b>{location.name} ({subscription_id_display})</b>\n\n"
            
            # Ключ
            if subscription.x3ui_client_id:
                user_message += f"🔑 <b>Ваш ключ:</b>\n"
                user_message += f"<code>{subscription.x3ui_client_id}</code>\n\n"
            
            # Время действия
            if subscription.expire_date:
                expire_date_local = utc_to_moscow(subscription.expire_date) if isinstance(subscription.expire_date, datetime) else subscription.expire_date
                expire_str = expire_date_local.strftime("%d.%m.%Y в %H:%M") if isinstance(expire_date_local, datetime) else str(expire_date_local)
                user_message += f"📅 <b>Окончание подписки:</b> {expire_str}\n"
            
            # Генерируем QR-код для ключа (если есть)
            photo = None
            if subscription.x3ui_client_id:
                try:
                    import qrcode
                    import io
                    # Генерируем QR-код
                    qr = qrcode.QRCode(version=1, box_size=10, border=5)
                    qr.add_data(subscription.x3ui_client_id)
                    qr.make(fit=True)
                    
                    # Создаем изображение
                    img = qr.make_image(fill_color="black", back_color="white")
                    
                    # Конвертируем в bytes
                    img_byte_arr = io.BytesIO()
                    img.save(img_byte_arr, format='PNG')
                    img_byte_arr.seek(0)
                    
                    # Создаем BufferedInputFile для отправки
                    from aiogram.types import BufferedInputFile
                    photo = BufferedInputFile(img_byte_arr.read(), filename="qrcode.png")
                except Exception as qr_error:
                    import logging
                    logger = logging.getLogger(__name__)
                    logger.error(f"Ошибка при генерации QR-кода: {qr_error}")
                    # Если не удалось сгенерировать, просто не отправляем фото
            
            # Отправляем сообщение с фото (если есть) или без
            if photo:
                await bot.send_photo(
                    chat_id=int(user.tg_id),
                    photo=photo,
                    caption=user_message,
                    parse_mode="HTML"
                )
            else:
                await bot.send_message(
                    chat_id=int(user.tg_id),
                    text=user_message,
                    parse_mode="HTML"
                )
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"❌ Ошибка при отправке уведомления пользователю {user.tg_id}: {e}")
            # Не прерываем выполнение, просто логируем ошибку
        
        # Обновляем детали пользователя
        await show_user_details(callback.message, user_id)
        
    except Exception as e:
        import logging
        import traceback
        logger = logging.getLogger(__name__)
        logger.error(f"❌ Ошибка при создании подписки: {e}")
        logger.error(traceback.format_exc())
        await callback.message.answer(f"❌ Ошибка при создании подписки: {e}")
    
    await state.clear()


# Обработчик для кнопки-разделителя (noop)
@router.callback_query(F.data == "noop", AdminFilter())
async def noop_callback(callback: types.CallbackQuery):
    await callback.answer()


# Начало отправки сообщения пользователю
@router.callback_query(F.data.startswith("admin_user_send_message_"), AdminFilter())
async def send_message_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    user_id = int(callback.data.split("_")[-1])
    
    user = await get_user_by_id(user_id)
    if not user:
        await callback.message.answer("❌ Пользователь не найден!")
        return
    
    # Сохраняем ID пользователя в state
    await state.update_data(target_user_id=user_id, target_user_tg_id=user.tg_id)
    
    username = user.username or f"ID: {user.tg_id}"
    await callback.message.answer(
        f"📨 <b>Отправка сообщения пользователю</b>\n\n"
        f"👤 Получатель: @{html.escape(username)}\n"
        f"🆔 Telegram ID: {user.tg_id}\n\n"
        f"Введите текст сообщения, которое хотите отправить:",
        reply_markup=cancel_keyboard(),
        parse_mode="HTML"
    )
    
    await state.set_state(SendMessageStates.waiting_message)


# Обработка ввода текста сообщения
@router.message(SendMessageStates.waiting_message, AdminFilter())
async def send_message_process(message: types.Message, state: FSMContext):
    from core.loader import bot
    from utils.keyboards.main_kb import main_menu
    
    state_data = await state.get_data()
    target_user_id = state_data.get("target_user_id")
    target_user_tg_id = state_data.get("target_user_tg_id")
    
    if not target_user_id or not target_user_tg_id:
        await message.answer("❌ Ошибка: данные пользователя не найдены. Начните заново.")
        await state.clear()
        return
    
    user = await get_user_by_id(target_user_id)
    if not user:
        await message.answer("❌ Пользователь не найден!")
        await state.clear()
        return
    
    message_text = message.text or message.caption or ""
    message_text = message_text.strip() if message_text else ""
    
    # Проверяем, есть ли медиа без текста
    has_media = bool(message.photo or message.video or message.document or message.audio or message.voice or message.video_note)
    
    if not message_text and not has_media:
        await message.answer("❌ Сообщение не может быть пустым. Введите текст сообщения или отправьте медиа с подписью:")
        return
    
    try:
        # Отправляем сообщение пользователю
        username = user.username or f"ID: {user.tg_id}"
        
        # Если есть медиа, отправляем медиа с подписью
        if has_media:
            # Формируем подпись для медиа
            caption = f"📨 <b>Сообщение от администратора</b>\n\n{message_text}" if message_text else "📨 <b>Сообщение от администратора</b>"
            
            # Отправляем медиа в зависимости от типа
            if message.photo:
                await bot.send_photo(
                    chat_id=int(target_user_tg_id),
                    photo=message.photo[-1].file_id,
                    caption=caption,
                    parse_mode="HTML"
                )
            elif message.video:
                await bot.send_video(
                    chat_id=int(target_user_tg_id),
                    video=message.video.file_id,
                    caption=caption,
                    parse_mode="HTML"
                )
            elif message.document:
                await bot.send_document(
                    chat_id=int(target_user_tg_id),
                    document=message.document.file_id,
                    caption=caption,
                    parse_mode="HTML"
                )
            elif message.audio:
                await bot.send_audio(
                    chat_id=int(target_user_tg_id),
                    audio=message.audio.file_id,
                    caption=caption,
                    parse_mode="HTML"
                )
            elif message.voice:
                # Для voice отправляем отдельно, так как у него нет caption
                await bot.send_voice(
                    chat_id=int(target_user_tg_id),
                    voice=message.voice.file_id
                )
                # Если есть текст, отправляем его отдельным сообщением
                if message_text:
                    await bot.send_message(
                        chat_id=int(target_user_tg_id),
                        text=f"📨 <b>Сообщение от администратора</b>\n\n{message_text}",
                        parse_mode="HTML"
                    )
                else:
                    # Отправляем заголовок отдельным сообщением
                    await bot.send_message(
                        chat_id=int(target_user_tg_id),
                        text="📨 <b>Сообщение от администратора</b>",
                        parse_mode="HTML"
                    )
            elif message.video_note:
                # Для video_note отправляем отдельно, так как у него нет caption
                await bot.send_video_note(
                    chat_id=int(target_user_tg_id),
                    video_note=message.video_note.file_id
                )
                # Если есть текст, отправляем его отдельным сообщением
                if message_text:
                    await bot.send_message(
                        chat_id=int(target_user_tg_id),
                        text=f"📨 <b>Сообщение от администратора</b>\n\n{message_text}",
                        parse_mode="HTML"
                    )
        else:
            # Отправляем только текстовое сообщение
            # Формируем сообщение для пользователя
            user_message = f"📨 <b>Сообщение от администратора</b>\n\n{message_text}"
            
            # Проверяем, что сообщение не пустое после форматирования
            if not user_message.strip() or not message_text:
                await message.answer("❌ Сообщение не может быть пустым. Введите текст сообщения:")
                return
            
            await bot.send_message(
                chat_id=int(target_user_tg_id),
                text=user_message,
                parse_mode="HTML"
            )
        
        # Подтверждаем администратору
        confirmation_text = f"✅ <b>Сообщение отправлено!</b>\n\n"
        confirmation_text += f"👤 Получатель: @{html.escape(username)}\n"
        
        if has_media:
            media_type = "📷 Фото" if message.photo else \
                        "🎥 Видео" if message.video else \
                        "📄 Документ" if message.document else \
                        "🎵 Аудио" if message.audio else \
                        "🎤 Голосовое" if message.voice else \
                        "📹 Видеосообщение" if message.video_note else "📎 Медиа"
            confirmation_text += f"📎 Тип: {media_type}\n"
        
        if message_text:
            confirmation_text += f"📝 Текст: {html.escape(message_text[:100])}{'...' if len(message_text) > 100 else ''}"
        elif has_media:
            confirmation_text += "📝 Текст: (без текста)"
        
        confirmation_msg = await message.answer(
            confirmation_text,
            parse_mode="HTML"
        )
        
        # Обновляем детали пользователя - используем новое сообщение вместо старого
        try:
            await show_user_details(confirmation_msg, target_user_id)
        except Exception as detail_error:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"❌ Ошибка при отображении деталей пользователя: {detail_error}")
            # Если не удалось обновить, просто игнорируем - главное, что сообщение отправлено
        
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"❌ Ошибка при отправке сообщения пользователю {target_user_tg_id}: {e}")
        
        error_msg = str(e)
        if "chat not found" in error_msg.lower() or "user is deactivated" in error_msg.lower():
            await message.answer(
                f"❌ <b>Не удалось отправить сообщение</b>\n\n"
                f"Пользователь заблокировал бота или удалил аккаунт.",
                parse_mode="HTML"
            )
        else:
            await message.answer(
                f"❌ <b>Ошибка при отправке сообщения:</b>\n{html.escape(error_msg)}",
                parse_mode="HTML"
            )
    
    finally:
        await state.clear()


# Отмена отправки сообщения
@router.callback_query(F.data == "cancel", SendMessageStates.waiting_message, AdminFilter())
async def cancel_send_message(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    
    state_data = await state.get_data()
    user_id = state_data.get("target_user_id")
    
    await state.clear()
    
    if user_id:
        await show_user_details(callback.message, user_id)
    else:
        # Возвращаем на главную панель администратора
        await safe_edit_text(
            callback.message,
            "🔧 <b>Админ-панель</b>\n\n"
            "Выберите раздел для управления:",
            reply_markup=admin_menu()
        )


# Отмена поиска
@router.callback_query(F.data == "cancel", SearchUserStates.waiting_query, AdminFilter())
async def cancel_search(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.clear()
    await safe_edit_text(
        callback.message,
        "👥 <b>Управление пользователями</b>\n\n"
        "Выберите действие:",
        reply_markup=users_menu()
    )


# Отмена создания подписки (на этапе выбора локации)
@router.callback_query(F.data == "cancel", CreateSubscriptionStates.waiting_location, AdminFilter())
async def cancel_create_subscription(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    state_data = await state.get_data()
    user_id = state_data.get("target_user_id")
    await state.clear()
    if user_id:
        await show_user_details(callback.message, user_id)
    else:
        await safe_edit_text(
            callback.message,
            "👥 <b>Управление пользователями</b>\n\n"
            "Выберите действие:",
            reply_markup=users_menu()
        )


# Подтверждение и удаление всех подписок пользователя (должен быть ПЕРВЫМ, так как более специфичный)
@router.callback_query(F.data.startswith("admin_user_delete_all_subscriptions_confirm_"), AdminFilter())
async def delete_all_subscriptions_execute_callback(callback: types.CallbackQuery):
    await callback.answer()
    user_id = int(callback.data.split("_")[-1])
    
    user = await get_user_by_id(user_id)
    if not user:
        await callback.message.answer("❌ Пользователь не найден!")
        return
    
    # Показываем сообщение о начале удаления
    await callback.message.answer("⏳ Удаление подписок...")
    
    # Удаляем все подписки
    success_count, error_count, errors = await delete_all_user_subscriptions_completely(user_id)
    
    username = user.username or f"ID: {user.tg_id}"
    
    if success_count > 0:
        result_text = (
            f"✅ <b>Подписки удалены</b>\n\n"
            f"👤 Пользователь: @{html.escape(username)}\n"
            f"✅ Успешно удалено: {success_count}\n"
        )
        
        if error_count > 0:
            result_text += f"❌ Ошибок: {error_count}\n"
            if errors:
                result_text += f"\nОшибки:\n"
                for error in errors[:5]:  # Показываем максимум 5 ошибок
                    result_text += f"• {html.escape(error)}\n"
                if len(errors) > 5:
                    result_text += f"... и еще {len(errors) - 5} ошибок\n"
        
        await callback.message.answer(result_text, parse_mode="HTML")
    else:
        error_text = (
            f"❌ <b>Ошибка при удалении подписок</b>\n\n"
            f"👤 Пользователь: @{html.escape(username)}\n"
            f"❌ Не удалось удалить подписки\n"
        )
        
        if errors:
            error_text += f"\nОшибки:\n"
            for error in errors[:5]:
                error_text += f"• {html.escape(error)}\n"
            if len(errors) > 5:
                error_text += f"... и еще {len(errors) - 5} ошибок\n"
        
        await callback.message.answer(error_text, parse_mode="HTML")
    
    # Обновляем детали пользователя
    await show_user_details(callback.message, user_id)


# Запрос подтверждения удаления всех подписок пользователя (должен быть ПОСЛЕ confirm обработчика)
@router.callback_query(F.data.startswith("admin_user_delete_all_subscriptions_"), AdminFilter())
async def delete_all_subscriptions_confirm_callback(callback: types.CallbackQuery):
    await callback.answer()
    user_id = int(callback.data.split("_")[-1])
    
    user = await get_user_by_id(user_id)
    if not user:
        await callback.message.answer("❌ Пользователь не найден!")
        return
    
    subscriptions = await get_user_subscriptions(user_id)
    if not subscriptions:
        await callback.message.answer("❌ У пользователя нет подписок для удаления!")
        return
    
    username = user.username or f"ID: {user.tg_id}"
    await safe_edit_text(
        callback.message,
        f"⚠️ <b>Подтверждение удаления</b>\n\n"
        f"👤 Пользователь: @{html.escape(username)}\n"
        f"📦 Количество подписок: {len(subscriptions)}\n\n"
        f"Вы уверены, что хотите удалить <b>все</b> подписки этого пользователя?\n"
        f"Это действие удалит подписки из базы данных и из 3x-ui API.\n\n"
        f"<b>Это действие необратимо!</b>",
        reply_markup=confirm_delete_all_subscriptions_keyboard(user_id),
        parse_mode="HTML"
    )
