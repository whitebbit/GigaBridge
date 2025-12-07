from aiogram import F, Router, types
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from utils.filters import AdminFilter
from utils.keyboards.admin_kb import admin_menu, stats_keyboard, cancel_keyboard
from utils.db import (
    get_total_revenue,
    get_revenue_by_period,
    get_subscriptions_count_by_status,
    get_users_with_active_subscriptions_count,
    get_paid_payments_count_by_period,
    get_new_users_count_by_period,
    get_all_users
)
from datetime import datetime, timedelta
import html

router = Router()


class BroadcastStates(StatesGroup):
    """Состояния для массовой рассылки"""
    waiting_message = State()
    waiting_confirm = State()


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


# Массовая рассылка
@router.callback_query(F.data == "admin_broadcast", AdminFilter())
async def broadcast_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    
    # Получаем количество пользователей
    users = await get_all_users()
    total_users = len(users)
    
    await callback.message.answer(
        f"📢 <b>Массовая рассылка сообщений</b>\n\n"
        f"👥 Всего пользователей в базе: <b>{total_users}</b>\n\n"
        f"Введите сообщение, которое хотите отправить всем пользователям.\n"
        f"Вы можете отправить текст, фото, видео или другой медиа-контент:",
        reply_markup=cancel_keyboard(),
        parse_mode="HTML"
    )
    
    await state.set_state(BroadcastStates.waiting_message)


@router.message(BroadcastStates.waiting_message, AdminFilter())
async def broadcast_message_received(message: types.Message, state: FSMContext):
    """Обработка полученного сообщения для рассылки"""
    message_text = message.text or message.caption or ""
    message_text = message_text.strip() if message_text else ""
    
    # Проверяем, есть ли медиа
    has_media = bool(message.photo or message.video or message.document or 
                     message.audio or message.voice or message.video_note)
    
    if not message_text and not has_media:
        await message.answer(
            "❌ Сообщение не может быть пустым. Введите текст сообщения или отправьте медиа с подписью:",
            reply_markup=cancel_keyboard()
        )
        return
    
    # Сохраняем данные сообщения в state
    message_data = {
        "text": message_text,
        "has_media": has_media,
        "media_type": None,
        "file_id": None
    }
    
    # Определяем тип медиа и сохраняем file_id
    if message.photo:
        message_data["media_type"] = "photo"
        message_data["file_id"] = message.photo[-1].file_id
    elif message.video:
        message_data["media_type"] = "video"
        message_data["file_id"] = message.video.file_id
    elif message.document:
        message_data["media_type"] = "document"
        message_data["file_id"] = message.document.file_id
    elif message.audio:
        message_data["media_type"] = "audio"
        message_data["file_id"] = message.audio.file_id
    elif message.voice:
        message_data["media_type"] = "voice"
        message_data["file_id"] = message.voice.file_id
    elif message.video_note:
        message_data["media_type"] = "video_note"
        message_data["file_id"] = message.video_note.file_id
    
    await state.update_data(message_data=message_data)
    
    # Получаем количество пользователей для подтверждения
    users = await get_all_users()
    total_users = len(users)
    
    # Формируем превью сообщения
    preview_text = "📢 <b>Подтверждение рассылки</b>\n\n"
    preview_text += f"👥 Получателей: <b>{total_users}</b>\n\n"
    
    if has_media:
        media_type_names = {
            "photo": "📷 Фото",
            "video": "🎥 Видео",
            "document": "📄 Документ",
            "audio": "🎵 Аудио",
            "voice": "🎤 Голосовое",
            "video_note": "📹 Видеосообщение"
        }
        preview_text += f"📎 Тип: {media_type_names.get(message_data['media_type'], 'Медиа')}\n"
    
    if message_text:
        preview_text += f"📝 Текст:\n{html.escape(message_text[:200])}"
        if len(message_text) > 200:
            preview_text += "..."
    else:
        preview_text += "📝 Текст: (без текста)"
    
    preview_text += f"\n\n⚠️ <b>Внимание!</b> Это сообщение будет отправлено всем {total_users} пользователям.\n"
    preview_text += "Продолжить?"
    
    # Создаем клавиатуру подтверждения
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Да, отправить всем", callback_data="broadcast_confirm")
    kb.button(text="❌ Отмена", callback_data="broadcast_cancel")
    kb.adjust(1)
    
    await message.answer(
        preview_text,
        reply_markup=kb.as_markup(),
        parse_mode="HTML"
    )
    
    await state.set_state(BroadcastStates.waiting_confirm)


@router.callback_query(F.data == "broadcast_confirm", BroadcastStates.waiting_confirm, AdminFilter())
async def broadcast_execute(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    
    state_data = await state.get_data()
    message_data = state_data.get("message_data")
    
    if not message_data:
        await callback.message.answer("❌ Ошибка: данные сообщения не найдены. Начните заново.")
        await state.clear()
        return
    
    # Получаем всех пользователей
    users = await get_all_users()
    total_users = len(users)
    
    if total_users == 0:
        await callback.message.answer("❌ В базе данных нет пользователей для рассылки.")
        await state.clear()
        return
    
    # Отправляем сообщение о начале рассылки
    status_msg = await callback.message.answer(
        f"⏳ <b>Начало рассылки...</b>\n\n"
        f"📊 Отправка сообщений {total_users} пользователям...\n"
        f"✅ Успешно: 0\n"
        f"❌ Ошибок: 0",
        parse_mode="HTML"
    )
    
    # Импортируем bot
    from core.loader import bot
    
    success_count = 0
    error_count = 0
    errors_list = []
    
    message_text = message_data.get("text", "")
    has_media = message_data.get("has_media", False)
    media_type = message_data.get("media_type")
    file_id = message_data.get("file_id")
    
    # Формируем текст сообщения для пользователей
    user_message_text = f"📨 <b>Сообщение от администратора</b>\n\n{message_text}" if message_text else "📨 <b>Сообщение от администратора</b>"
    
    # Отправляем сообщения каждому пользователю
    for i, user in enumerate(users, 1):
        try:
            if has_media:
                # Отправляем медиа с подписью
                caption = user_message_text if message_text else "📨 <b>Сообщение от администратора</b>"
                
                if media_type == "photo":
                    await bot.send_photo(
                        chat_id=int(user.tg_id),
                        photo=file_id,
                        caption=caption,
                        parse_mode="HTML"
                    )
                elif media_type == "video":
                    await bot.send_video(
                        chat_id=int(user.tg_id),
                        video=file_id,
                        caption=caption,
                        parse_mode="HTML"
                    )
                elif media_type == "document":
                    await bot.send_document(
                        chat_id=int(user.tg_id),
                        document=file_id,
                        caption=caption,
                        parse_mode="HTML"
                    )
                elif media_type == "audio":
                    await bot.send_audio(
                        chat_id=int(user.tg_id),
                        audio=file_id,
                        caption=caption,
                        parse_mode="HTML"
                    )
                elif media_type == "voice":
                    # Для voice отправляем отдельно, так как у него нет caption
                    await bot.send_voice(
                        chat_id=int(user.tg_id),
                        voice=file_id
                    )
                    if message_text:
                        await bot.send_message(
                            chat_id=int(user.tg_id),
                            text=user_message_text,
                            parse_mode="HTML"
                        )
                    else:
                        await bot.send_message(
                            chat_id=int(user.tg_id),
                            text="📨 <b>Сообщение от администратора</b>",
                            parse_mode="HTML"
                        )
                elif media_type == "video_note":
                    # Для video_note отправляем отдельно, так как у него нет caption
                    await bot.send_video_note(
                        chat_id=int(user.tg_id),
                        video_note=file_id
                    )
                    if message_text:
                        await bot.send_message(
                            chat_id=int(user.tg_id),
                            text=user_message_text,
                            parse_mode="HTML"
                        )
                    else:
                        await bot.send_message(
                            chat_id=int(user.tg_id),
                            text="📨 <b>Сообщение от администратора</b>",
                            parse_mode="HTML"
                        )
            else:
                # Отправляем только текстовое сообщение
                await bot.send_message(
                    chat_id=int(user.tg_id),
                    text=user_message_text,
                    parse_mode="HTML"
                )
            
            success_count += 1
            
            # Обновляем статус каждые 10 сообщений или в конце
            if i % 10 == 0 or i == total_users:
                try:
                    await status_msg.edit_text(
                        f"⏳ <b>Рассылка в процессе...</b>\n\n"
                        f"📊 Отправка сообщений {total_users} пользователям...\n"
                        f"📈 Прогресс: {i}/{total_users} ({i * 100 // total_users}%)\n"
                        f"✅ Успешно: {success_count}\n"
                        f"❌ Ошибок: {error_count}",
                        parse_mode="HTML"
                    )
                except:
                    pass  # Игнорируем ошибки редактирования статуса
            
            # Небольшая задержка, чтобы не превышать лимиты Telegram API
            if i % 30 == 0:  # Задержка каждые 30 сообщений
                import asyncio
                await asyncio.sleep(1)
                
        except Exception as e:
            error_count += 1
            error_msg = str(e)
            
            # Короткое логирование ошибки
            username = user.username or f"ID: {user.tg_id}"
            if len(errors_list) < 5:  # Сохраняем только первые 5 ошибок
                errors_list.append(f"@{username}: {error_msg[:50]}")
            
            # Обновляем статус при ошибках тоже
            if error_count % 10 == 0 or i == total_users:
                try:
                    await status_msg.edit_text(
                        f"⏳ <b>Рассылка в процессе...</b>\n\n"
                        f"📊 Отправка сообщений {total_users} пользователям...\n"
                        f"📈 Прогресс: {i}/{total_users} ({i * 100 // total_users}%)\n"
                        f"✅ Успешно: {success_count}\n"
                        f"❌ Ошибок: {error_count}",
                        parse_mode="HTML"
                    )
                except:
                    pass
    
    # Финальное сообщение о результатах
    result_text = f"✅ <b>Рассылка завершена!</b>\n\n"
    result_text += f"👥 Всего пользователей: {total_users}\n"
    result_text += f"✅ Успешно отправлено: <b>{success_count}</b>\n"
    result_text += f"❌ Ошибок: <b>{error_count}</b>\n"
    
    if errors_list:
        result_text += f"\n<b>Примеры ошибок:</b>\n"
        for error in errors_list:
            result_text += f"• {html.escape(error)}\n"
        if error_count > len(errors_list):
            result_text += f"... и еще {error_count - len(errors_list)} ошибок\n"
    
    await status_msg.edit_text(result_text, parse_mode="HTML")
    
    # Возвращаем в админ-меню
    await callback.message.answer(
        "🔧 <b>Админ-панель</b>\n\n"
        "Выберите раздел для управления:",
        reply_markup=admin_menu(),
        parse_mode="HTML"
    )
    
    await state.clear()


@router.callback_query(F.data == "broadcast_cancel", BroadcastStates.waiting_confirm, AdminFilter())
async def broadcast_cancel_confirm(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.clear()
    
    await safe_edit_text(
        callback.message,
        "❌ Рассылка отменена.",
        reply_markup=admin_menu()
    )


# Отмена рассылки на этапе ввода сообщения
@router.callback_query(F.data == "cancel", BroadcastStates.waiting_message, AdminFilter())
async def broadcast_cancel_message(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.clear()
    
    await safe_edit_text(
        callback.message,
        "🔧 <b>Админ-панель</b>\n\n"
        "Выберите раздел для управления:",
        reply_markup=admin_menu()
    )

