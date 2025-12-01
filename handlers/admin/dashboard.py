from aiogram import F, Router, types
from aiogram.exceptions import TelegramBadRequest
from utils.filters import AdminFilter
from utils.keyboards.admin_kb import admin_menu, stats_keyboard
from utils.db import (
    get_total_revenue,
    get_revenue_by_period,
    get_subscriptions_count_by_status,
    get_users_with_active_subscriptions_count,
    get_paid_payments_count_by_period,
    get_new_users_count_by_period
)
from datetime import datetime, timedelta

router = Router()


async def safe_edit_text(message: types.Message, text: str, reply_markup=None, parse_mode="HTML"):
    """Безопасное редактирование сообщения с обработкой ошибки 'message is not modified'"""
    try:
        await message.edit_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
    except TelegramBadRequest as e:
        if "message is not modified" not in str(e).lower():
            raise


# Статистика
@router.callback_query(F.data == "admin_stats", AdminFilter())
async def stats_callback(callback: types.CallbackQuery):
    await callback.answer()
    
    # Определяем периоды
    now = datetime.utcnow()
    today_start = datetime(now.year, now.month, now.day, 0, 0, 0)
    week_start = today_start - timedelta(days=7)
    month_start = datetime(now.year, now.month, 1, 0, 0, 0)
    
    # Получаем статистику по подпискам
    active_subscriptions = await get_subscriptions_count_by_status("active")
    expired_subscriptions = await get_subscriptions_count_by_status("expired")
    paused_subscriptions = await get_subscriptions_count_by_status("paused")
    total_subscriptions = active_subscriptions + expired_subscriptions + paused_subscriptions
    
    # Получаем статистику по пользователям
    users_with_subscriptions = await get_users_with_active_subscriptions_count()
    
    # Получаем финансовую статистику
    total_revenue = await get_total_revenue()
    revenue_today = await get_revenue_by_period(today_start)
    revenue_week = await get_revenue_by_period(week_start)
    revenue_month = await get_revenue_by_period(month_start)
    
    # Получаем статистику по платежам
    payments_today = await get_paid_payments_count_by_period(today_start)
    
    # Получаем статистику по новым пользователям
    new_users_today = await get_new_users_count_by_period(today_start)
    
    # Формируем сообщение
    text = "📊 <b>Статистика</b>\n\n"
    
    # Подписки
    text += "📦 <b>Подписки:</b>\n"
    text += f"   ✅ Активных: <b>{active_subscriptions}</b>\n"
    if expired_subscriptions > 0:
        text += f"   ❌ Истекших: {expired_subscriptions}\n"
    if paused_subscriptions > 0:
        text += f"   ⏸️ Приостановленных: {paused_subscriptions}\n"
    text += f"   👥 Пользователей с подписками: <b>{users_with_subscriptions}</b>\n\n"
    
    # Финансы
    text += "💰 <b>Финансы:</b>\n"
    if revenue_today > 0:
        text += f"   📈 За сегодня: <b>{revenue_today:.0f} ₽</b>\n"
    if revenue_week > 0:
        text += f"   📊 За неделю: {revenue_week:.0f} ₽\n"
    if revenue_month > 0:
        text += f"   📅 За месяц: {revenue_month:.0f} ₽\n"
    text += f"   💎 Всего: <b>{total_revenue:.0f} ₽</b>\n\n"
    
    # Активность за сегодня
    text += "📅 <b>Сегодня:</b>\n"
    if payments_today > 0:
        text += f"   💳 Успешных платежей: <b>{payments_today}</b>\n"
    if new_users_today > 0:
        text += f"   👤 Новых пользователей: <b>{new_users_today}</b>\n"
    if payments_today == 0 and new_users_today == 0:
        text += "   Нет активности\n"
    
    await safe_edit_text(callback.message, text, reply_markup=stats_keyboard())

