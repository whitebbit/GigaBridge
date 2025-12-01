from aiogram import F, Router, types
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from utils.filters import AdminFilter
from utils.keyboards.admin_kb import admin_menu
from utils.db import (
    get_all_support_tickets,
    get_open_support_tickets,
    get_support_ticket_by_id,
    answer_support_ticket,
    delete_support_ticket
)
from core.loader import bot
import html

router = Router()


class AnswerTicketStates(StatesGroup):
    """Состояния для ответа на тикет"""
    waiting_answer = State()


async def safe_edit_text(message: types.Message, text: str, reply_markup=None, parse_mode="HTML"):
    """Безопасное редактирование сообщения с обработкой ошибки 'message is not modified'"""
    try:
        await message.edit_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
    except TelegramBadRequest as e:
        if "message is not modified" not in str(e).lower():
            raise


def support_tickets_list_keyboard(tickets, page: int = 0, per_page: int = 5, show_all: bool = False):
    """Клавиатура со списком тикетов с пагинацией"""
    kb = InlineKeyboardBuilder()
    
    # Вычисляем индексы для текущей страницы
    start_idx = page * per_page
    end_idx = start_idx + per_page
    total_tickets = len(tickets)
    total_pages = (total_tickets + per_page - 1) // per_page if total_tickets > 0 else 1
    
    # Получаем тикеты для текущей страницы
    page_tickets = tickets[start_idx:end_idx]
    
    # Форматируем и добавляем тикеты
    for ticket in page_tickets:
        status_emoji = {
            "open": "🔴",
            "answered": "🟢",
            "closed": "⚫"
        }.get(ticket.status, "❓")
        
        username = ticket.user.username if ticket.user and ticket.user.username else f"ID: {ticket.user.tg_id if ticket.user else 'N/A'}"
        
        # Форматируем текст кнопки
        button_text = f"{status_emoji} #{ticket.id} | {username[:15]}"
        if len(button_text) > 40:
            button_text = button_text[:37] + "..."
        
        kb.button(
            text=button_text,
            callback_data=f"admin_support_ticket_{ticket.id}"
        )
    
    # Добавляем кнопки пагинации
    nav_buttons = []
    if page > 0:
        nav_buttons.append(("◀️ Назад", f"admin_support_page_{page - 1}_{int(show_all)}"))
    if page < total_pages - 1:
        nav_buttons.append(("Вперед ▶️", f"admin_support_page_{page + 1}_{int(show_all)}"))
    
    for text, callback_data in nav_buttons:
        kb.button(text=text, callback_data=callback_data)
    
    # Добавляем информацию о странице
    if total_pages > 1:
        kb.button(text=f"📄 Страница {page + 1}/{total_pages}", callback_data="admin_support_info")
    
    # Кнопки фильтров
    if show_all:
        kb.button(text="📋 Только открытые", callback_data="admin_support_open")
    else:
        kb.button(text="📋 Все тикеты", callback_data="admin_support_all")
    
    kb.button(text="🔙 Назад", callback_data="admin_menu")
    kb.adjust(1, 2 if nav_buttons else 1, 1, 1)
    return kb.as_markup()


def support_ticket_detail_keyboard(ticket_id: int, status: str):
    """Клавиатура для деталей тикета"""
    kb = InlineKeyboardBuilder()
    
    if status == "open":
        kb.button(text="💬 Ответить", callback_data=f"admin_support_answer_{ticket_id}")
    
    kb.button(text="🔙 Назад к списку", callback_data="admin_support")
    kb.adjust(1)
    return kb.as_markup()


@router.callback_query(F.data == "admin_support", AdminFilter())
async def admin_support_callback(callback: types.CallbackQuery):
    """Обработчик кнопки 'Поддержка' в админ-панели"""
    await callback.answer()
    
    # Получаем открытые тикеты
    open_tickets = await get_open_support_tickets()
    all_tickets = await get_all_support_tickets()
    
    text = "💬 <b>Поддержка</b>\n\n"
    text += f"🔴 Открытых тикетов: <b>{len(open_tickets)}</b>\n"
    text += f"📋 Всего тикетов: <b>{len(all_tickets)}</b>\n\n"
    
    if open_tickets:
        text += "📋 <b>Открытые тикеты:</b>\n"
        await safe_edit_text(
            callback.message,
            text,
            reply_markup=support_tickets_list_keyboard(open_tickets, page=0, show_all=True)
        )
    elif all_tickets:
        text += "Нет открытых тикетов. Показаны все тикеты:"
        await safe_edit_text(
            callback.message,
            text,
            reply_markup=support_tickets_list_keyboard(all_tickets, page=0, show_all=False)
        )
    else:
        text += "Нет тикетов поддержки."
        await safe_edit_text(
            callback.message,
            text,
            reply_markup=admin_menu()
        )


@router.callback_query(F.data == "admin_support_all", AdminFilter())
async def admin_support_all_callback(callback: types.CallbackQuery):
    """Показать все тикеты"""
    await callback.answer()
    
    all_tickets = await get_all_support_tickets()
    
    text = "💬 <b>Все тикеты поддержки</b>\n\n"
    text += f"📋 Всего тикетов: <b>{len(all_tickets)}</b>\n\n"
    
    if all_tickets:
        await safe_edit_text(
            callback.message,
            text,
            reply_markup=support_tickets_list_keyboard(all_tickets, page=0, show_all=False)
        )
    else:
        text += "Нет тикетов поддержки."
        await safe_edit_text(
            callback.message,
            text,
            reply_markup=admin_menu()
        )


@router.callback_query(F.data == "admin_support_open", AdminFilter())
async def admin_support_open_callback(callback: types.CallbackQuery):
    """Показать только открытые тикеты"""
    await callback.answer()
    
    open_tickets = await get_open_support_tickets()
    
    text = "💬 <b>Открытые тикеты</b>\n\n"
    text += f"🔴 Открытых тикетов: <b>{len(open_tickets)}</b>\n\n"
    
    if open_tickets:
        await safe_edit_text(
            callback.message,
            text,
            reply_markup=support_tickets_list_keyboard(open_tickets, page=0, show_all=True)
        )
    else:
        text += "Нет открытых тикетов."
        await safe_edit_text(
            callback.message,
            text,
            reply_markup=admin_menu()
        )


@router.callback_query(F.data.startswith("admin_support_page_"), AdminFilter())
async def admin_support_page_callback(callback: types.CallbackQuery):
    """Обработчик пагинации тикетов"""
    await callback.answer()
    
    # Парсим данные: admin_support_page_{page}_{show_all}
    parts = callback.data.split("_")
    page = int(parts[3])
    show_all = bool(int(parts[4]))
    
    if show_all:
        tickets = await get_all_support_tickets()
        text = "💬 <b>Все тикеты поддержки</b>\n\n"
        text += f"📋 Всего тикетов: <b>{len(tickets)}</b>\n\n"
    else:
        tickets = await get_open_support_tickets()
        text = "💬 <b>Открытые тикеты</b>\n\n"
        text += f"🔴 Открытых тикетов: <b>{len(tickets)}</b>\n\n"
    
    if tickets:
        await safe_edit_text(
            callback.message,
            text,
            reply_markup=support_tickets_list_keyboard(tickets, page=page, show_all=show_all)
        )
    else:
        text += "Нет тикетов поддержки."
        await safe_edit_text(
            callback.message,
            text,
            reply_markup=admin_menu()
        )


@router.callback_query(F.data == "admin_support_info", AdminFilter())
async def admin_support_info_callback(callback: types.CallbackQuery):
    """Обработчик информационной кнопки (не делает ничего)"""
    await callback.answer()


@router.callback_query(F.data.startswith("admin_support_ticket_"), AdminFilter())
async def admin_support_ticket_detail_callback(callback: types.CallbackQuery):
    """Обработчик просмотра деталей тикета"""
    await callback.answer()
    
    ticket_id = int(callback.data.split("_")[-1])
    ticket = await get_support_ticket_by_id(ticket_id)
    
    if not ticket:
        await safe_edit_text(
            callback.message,
            "❌ Тикет не найден (возможно, уже удален)",
            reply_markup=admin_menu()
        )
        return
    
    user = ticket.user
    username = user.username if user and user.username else f"ID: {user.tg_id if user else 'N/A'}"
    
    status_text = {
        "open": "🔴 Открыт",
        "answered": "🟢 Отвечен",
        "closed": "⚫ Закрыт"
    }.get(ticket.status, "❓ Неизвестно")
    
    # Форматируем дату создания
    created_at = ticket.created_at.strftime("%d.%m.%Y в %H:%M") if ticket.created_at else "Неизвестно"
    
    text = f"💬 <b>Тикет #{ticket.id}</b>\n"
    text += "━" * 30 + "\n\n"
    text += f"👤 <b>Пользователь:</b> {html.escape(username)}\n"
    text += f"📅 <b>Создан:</b> {created_at}\n"
    text += f"📊 <b>Статус:</b> {status_text}\n\n"
    text += f"📝 <b>Сообщение пользователя:</b>\n"
    text += "─" * 20 + "\n"
    text += f"{html.escape(ticket.message)}\n\n"
    
    if ticket.admin_response:
        answered_at = ticket.answered_at.strftime("%d.%m.%Y в %H:%M") if ticket.answered_at else "Неизвестно"
        text += f"💬 <b>Ответ администратора:</b>\n"
        text += "─" * 20 + "\n"
        text += f"{html.escape(ticket.admin_response)}\n\n"
        text += f"📅 <b>Ответ дан:</b> {answered_at}"
    else:
        text += "💬 <b>Ответ администратора:</b> Пока нет ответа"
    
    await safe_edit_text(
        callback.message,
        text,
        reply_markup=support_ticket_detail_keyboard(ticket_id, ticket.status)
    )


@router.callback_query(F.data.startswith("admin_support_answer_"), AdminFilter())
async def admin_support_answer_callback(callback: types.CallbackQuery, state: FSMContext):
    """Обработчик начала ответа на тикет"""
    await callback.answer()
    
    ticket_id = int(callback.data.split("_")[-1])
    ticket = await get_support_ticket_by_id(ticket_id)
    
    if not ticket:
        await safe_edit_text(
            callback.message,
            "❌ Тикет не найден",
            reply_markup=admin_menu()
        )
        return
    
    if ticket.status != "open":
        await safe_edit_text(
            callback.message,
            "❌ Этот тикет уже обработан",
            reply_markup=support_ticket_detail_keyboard(ticket_id, ticket.status)
        )
        return
    
    # Сохраняем ticket_id в state
    await state.update_data(ticket_id=ticket_id)
    await state.set_state(AnswerTicketStates.waiting_answer)
    
    text = f"💬 <b>Ответ на тикет #{ticket_id}</b>\n\n"
    text += f"📝 <b>Сообщение пользователя:</b>\n{html.escape(ticket.message)}\n\n"
    text += "✍️ <b>Введите ваш ответ:</b>"
    
    kb = InlineKeyboardBuilder()
    kb.button(text="❌ Отмена", callback_data=f"admin_support_ticket_{ticket_id}")
    kb.adjust(1)
    
    await safe_edit_text(
        callback.message,
        text,
        reply_markup=kb.as_markup()
    )


@router.message(AnswerTicketStates.waiting_answer)
async def admin_support_answer_message_handler(message: types.Message, state: FSMContext):
    """Обработчик сообщения с ответом на тикет"""
    try:
        await message.delete()
    except:
        pass
    
    data = await state.get_data()
    ticket_id = data.get("ticket_id")
    
    if not ticket_id:
        await message.answer("❌ Ошибка: не найден тикет", reply_markup=admin_menu())
        await state.clear()
        return
    
    # Проверяем, что сообщение не пустое
    if not message.text or len(message.text.strip()) < 3:
        await message.answer(
            "❌ Сообщение слишком короткое. Пожалуйста, введите ответ (минимум 3 символа)."
        )
        return
    
    ticket = await get_support_ticket_by_id(ticket_id)
    
    if not ticket:
        await message.answer("❌ Тикет не найден", reply_markup=admin_menu())
        await state.clear()
        return
    
    if ticket.status != "open":
        await message.answer("❌ Этот тикет уже обработан", reply_markup=admin_menu())
        await state.clear()
        return
    
    # Получаем данные тикета для уведомления (перед удалением)
    answered_ticket = await answer_support_ticket(ticket_id, message.text.strip())
    
    if not answered_ticket:
        await message.answer("❌ Ошибка: тикет не найден", reply_markup=admin_menu())
        await state.clear()
        return
    
    # Сохраняем данные для уведомления
    user = answered_ticket.user
    ticket_message = answered_ticket.message
    admin_response_text = message.text.strip()
    
    # Удаляем тикет из базы данных сразу после получения данных
    deleted = await delete_support_ticket(ticket_id)
    
    if not deleted:
        await message.answer("❌ Ошибка при удалении тикета из базы данных", reply_markup=admin_menu())
        await state.clear()
        return
    
    # Отправляем уведомление пользователю
    if user:
        try:
            notification_text = "💬 <b>Получен ответ от поддержки</b>\n\n"
            notification_text += f"🆔 <b>Номер обращения:</b> #{ticket_id}\n\n"
            notification_text += f"📝 <b>Ваше сообщение:</b>\n{html.escape(ticket_message)}\n\n"
            notification_text += f"💬 <b>Ответ поддержки:</b>\n{html.escape(admin_response_text)}\n\n"
            notification_text += "Спасибо за обращение!"
            
            await bot.send_message(
                chat_id=int(user.tg_id),
                text=notification_text,
                parse_mode="HTML"
            )
        except Exception as e:
            print(f"Ошибка при отправке уведомления пользователю: {e}")
    
    # Показываем подтверждение админу и автоматически обновляем список тикетов
    if user and user.username:
        user_display = user.username
    elif user:
        user_display = f"ID: {user.tg_id}"
    else:
        user_display = "N/A"
    
    text = f"✅ <b>Ответ отправлен!</b>\n\n"
    text += f"🆔 <b>Тикет:</b> #{ticket_id}\n"
    text += f"👤 <b>Пользователь:</b> {user_display}\n\n"
    text += f"💬 <b>Ваш ответ:</b>\n{html.escape(admin_response_text)}\n\n"
    text += "🗑️ <b>Тикет удален из базы данных.</b>"
    
    # Отправляем подтверждение
    await message.answer(text, parse_mode="HTML")
    
    # Автоматически обновляем список тикетов (открытые)
    open_tickets = await get_open_support_tickets()
    all_tickets = await get_all_support_tickets()
    
    list_text = "💬 <b>Поддержка</b>\n\n"
    list_text += f"🔴 Открытых тикетов: <b>{len(open_tickets)}</b>\n"
    list_text += f"📋 Всего тикетов: <b>{len(all_tickets)}</b>\n\n"
    
    if open_tickets:
        list_text += "📋 <b>Открытые тикеты:</b>\n"
        kb = support_tickets_list_keyboard(open_tickets, page=0, show_all=True)
    elif all_tickets:
        list_text += "Нет открытых тикетов. Показаны все тикеты:"
        kb = support_tickets_list_keyboard(all_tickets, page=0, show_all=False)
    else:
        list_text += "Нет тикетов поддержки."
        kb = admin_menu()
    
    await message.answer(list_text, parse_mode="HTML", reply_markup=kb)
    await state.clear()

