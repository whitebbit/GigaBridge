from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile
from aiogram.utils.keyboard import InlineKeyboardBuilder
from utils.keyboards.main_kb import main_menu
from utils.db import (
    get_user_by_tg_id,
    get_user_subscriptions,
    get_server_by_id,
    get_subscription_by_id,
    get_tariff_by_id,
    get_active_locations,
    has_available_server_for_location,
    has_user_made_purchase,
    get_location_by_id,
    select_available_server_for_location,
    get_subscription_identifier,
    utc_to_user_timezone
)
from core.config import config
from datetime import datetime, timedelta
import qrcode
import io
import logging
from services.x3ui_api import get_x3ui_client

logger = logging.getLogger(__name__)

router = Router()


@router.message(F.text == "👤 Профиль")
async def profile_handler(message: types.Message):
    """Обработчик кнопки Профиль - показывает информацию о подписках пользователя"""
    try:
        await message.delete()
    except:
        pass
    
    user = await get_user_by_tg_id(str(message.from_user.id))
    
    if not user:
        await message.answer("❌ Пользователь не найден. Используйте /start", reply_markup=main_menu())
        return
    
    # Логируем вход пользователя в профиль
    logger.info("=" * 80)
    logger.info(f"👤 Пользователь зашел в профиль:")
    logger.info(f"   Telegram ID: {user.tg_id}")
    logger.info(f"   Username: {user.username}")
    logger.info(f"   User ID: {user.id}")
    logger.info(f"   Sub ID: {user.sub_id}")
    
    # Получаем все подписки пользователя из БД (с предзагрузкой серверов и локаций)
    subscriptions = await get_user_subscriptions(user.id)
    logger.info(f"   Подписок в БД: {len(subscriptions)}")
    
    text = "👤 <b>Ваш профиль</b>\n\n"
    
    if subscriptions:
        text += f"📦 <b>У вас подписок: {len(subscriptions)}</b>\n\n"
        text += "Выберите подписку для просмотра детальной информации:"
        
        # Создаем клавиатуру с кнопками подписок
        # Серверы и локации уже загружены через joinedload, не нужно делать дополнительные запросы
        kb = InlineKeyboardBuilder()
        for sub in subscriptions:
            # Используем загруженные данные (server и location уже доступны)
            server = sub.server if hasattr(sub, 'server') else None
            # Используем название локации вместо названия сервера
            if server and server.location:
                location_name = server.location.name
            else:
                location_name = f"Локация #{sub.server_id}"
            
            # Генерируем идентификатор подписки
            subscription_id = get_subscription_identifier(sub, location_name)
            
            status_emoji = {
                "active": "✅",
                "paused": "⏸️",
                "expired": "❌"
            }.get(sub.status, "❓")
            kb.button(
                text=f"{status_emoji} {location_name} ({subscription_id})",
                callback_data=f"subscription_detail_{sub.id}"
            )
        # Размещаем кнопки по 2 в ряд
        kb.adjust(2)
        
        try:
            await message.answer(text, reply_markup=kb.as_markup(), parse_mode="HTML")
        except Exception as e:
            logger.error(f"❌ Ошибка при отправке сообщения профиля: {type(e).__name__}: {e}")
            # Не пробрасываем ошибку дальше, чтобы не прерывать работу бота
    else:
        text += "📦 <b>У вас пока нет активных подписок</b>\n\n"
        text += "Приобретите подписку, чтобы начать пользоваться GigaBridge."
        
        # Кнопка для покупки
        kb = InlineKeyboardBuilder()
        kb.button(text="🛒 Приобрести", callback_data="profile_purchase")
        kb.adjust(1)
        
        try:
            await message.answer(text, reply_markup=kb.as_markup(), parse_mode="HTML")
        except Exception as e:
            logger.error(f"❌ Ошибка при отправке сообщения профиля: {type(e).__name__}: {e}")
            # Не пробрасываем ошибку дальше, чтобы не прерывать работу бота


@router.callback_query(F.data.startswith("subscription_detail_"))
async def subscription_detail_handler(callback: types.CallbackQuery):
    """Обработчик детального просмотра подписки"""
    try:
        await callback.answer()
    except:
        pass
    
    subscription_id = int(callback.data.split("_")[-1])
    subscription = await get_subscription_by_id(subscription_id)
    
    if not subscription:
        try:
            await callback.message.delete()
        except:
            pass
        try:
            await callback.message.answer("❌ Подписка не найдена", reply_markup=main_menu())
        except Exception as e:
            logger.error(f"❌ Ошибка при отправке сообщения: {type(e).__name__}: {e}")
        return
    
    # Проверяем, что подписка принадлежит пользователю
    user = await get_user_by_tg_id(str(callback.from_user.id))
    if not user or subscription.user_id != user.id:
        try:
            await callback.message.delete()
        except:
            pass
        try:
            await callback.message.answer("❌ Доступ запрещен", reply_markup=main_menu())
        except Exception as e:
            logger.error(f"❌ Ошибка при отправке сообщения: {type(e).__name__}: {e}")
        return
    
    # Получаем информацию о сервере для локации
    server = await get_server_by_id(subscription.server_id)
    
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
    
    # Формируем текст с детальной информацией
    # Заголовок: Название локации - статус с эмоджи
    if server and server.location:
        location_name = server.location.name
    else:
        location_name = f"Локация #{subscription.server_id}"
    
    # Генерируем идентификатор подписки
    subscription_id = get_subscription_identifier(subscription, location_name)
    
    text = f"📦 <b>{location_name} ({subscription_id}) - {status_emoji} {status_text}</b>\n\n"
    
    # Ссылка на подписку
    if subscription.sub_id:
        # Получаем сервер для извлечения IP адреса
        server = await get_server_by_id(subscription.server_id)
        if server:
            from utils.db import generate_subscription_link
            subscription_link = generate_subscription_link(server, subscription.sub_id)
            text += f"🔗 <b>Ссылка на подписку:</b>\n"
            text += f"<code>{subscription_link}</code>\n\n"
    
    # Время действия (показываем только для подписок с ограниченным сроком, не для бессрочных)
    if not subscription.is_private and subscription.expire_date:
        from datetime import datetime as dt
        if isinstance(subscription.expire_date, dt):
            # Конвертируем UTC время в локальное время пользователя для отображения
            # Пытаемся получить language_code из Telegram, если доступен
            language_code = None
            try:
                from core.loader import bot
                chat = await bot.get_chat(int(user.tg_id))
                language_code = getattr(chat, 'language_code', None)
            except:
                pass
            local_expire_date = utc_to_user_timezone(subscription.expire_date, user=user, language_code=language_code)
            expire_str = local_expire_date.strftime("%d.%m.%Y в %H:%M")
        else:
            expire_str = str(subscription.expire_date)
        text += f"📅 <b>Окончание подписки:</b> {expire_str}\n"
        
        # Проверяем, сколько времени осталось (используем UTC для расчета)
        if isinstance(subscription.expire_date, dt):
            time_left = subscription.expire_date - dt.utcnow()
            if time_left.total_seconds() > 0:
                # Если используется тестовый режим (меньше 24 часов), показываем минуты/часы
                if config.TEST_MODE and time_left.total_seconds() < 86400:
                    hours_left = int(time_left.total_seconds() // 3600)
                    minutes_left = int((time_left.total_seconds() % 3600) // 60)
                    if hours_left > 0:
                        text += f"⏰ <b>Осталось:</b> {hours_left} ч. {minutes_left} мин.\n"
                    else:
                        text += f"⏰ <b>Осталось:</b> {minutes_left} мин.\n"
                else:
                    days_left = time_left.days
                    if days_left > 0:
                        text += f"⏰ <b>Осталось дней:</b> {days_left}\n"
                    else:
                        hours_left = int(time_left.total_seconds() // 3600)
                        minutes_left = int((time_left.total_seconds() % 3600) // 60)
                        if hours_left > 0:
                            text += f"⏰ <b>Осталось:</b> {hours_left} ч. {minutes_left} мин.\n"
                        elif minutes_left > 0:
                            text += f"⏰ <b>Осталось:</b> {minutes_left} мин.\n"
                        else:
                            text += f"⚠️ <b>Подписка истекла</b>\n"
            else:
                text += f"⚠️ <b>Подписка истекла</b>\n"
                
                # Показываем информацию о времени до удаления подписки (только для истекших подписок)
                if isinstance(subscription.expire_date, dt) and subscription.status == "expired":
                    # Определяем интервал удаления в зависимости от режима
                    if config.TEST_MODE:
                        delete_interval = timedelta(minutes=5)
                    else:
                        delete_interval = timedelta(days=30)
                    
                    # Вычисляем точную дату и время удаления
                    deletion_datetime = subscription.expire_date + delete_interval
                    local_deletion_datetime = utc_to_user_timezone(deletion_datetime, user=user, language_code=language_code)
                    deletion_datetime_str = local_deletion_datetime.strftime("%d.%m.%Y в %H:%M")
                    
                    # Вычисляем оставшееся время до удаления
                    time_since_expiry = dt.utcnow() - subscription.expire_date
                    time_until_deletion = delete_interval - time_since_expiry
                    
                    # Всегда показываем точную дату и время удаления
                    text += f"\n🗑️ <b>Подписка будет удалена:</b> {deletion_datetime_str}\n"
                    
                    # Показываем оставшееся время, если оно еще есть
                    if time_until_deletion.total_seconds() > 0:
                        if config.TEST_MODE:
                            # В тестовом режиме показываем минуты/секунды
                            minutes_left = int(time_until_deletion.total_seconds() // 60)
                            seconds_left = int(time_until_deletion.total_seconds() % 60)
                            if minutes_left > 0:
                                text += f"⏰ Осталось: {minutes_left} мин. {seconds_left} сек.\n"
                            else:
                                text += f"⏰ Осталось: {seconds_left} сек.\n"
                        else:
                            # В обычном режиме показываем дни
                            days_left = time_until_deletion.days
                            hours_left = int((time_until_deletion.total_seconds() % 86400) // 3600)
                            if days_left > 0:
                                text += f"⏰ Осталось: {days_left} дн. {hours_left} ч.\n"
                            elif hours_left > 0:
                                text += f"⏰ Осталось: {hours_left} ч.\n"
                            else:
                                minutes_left = int((time_until_deletion.total_seconds() % 3600) // 60)
                                text += f"⏰ Осталось: {minutes_left} мин.\n"
    
    # Генерируем QR-код для ссылки на подписку (если есть sub_id)
    photo = None
    if subscription.sub_id:
        
        try:
            # Получаем сервер для извлечения IP адреса (если еще не получен)
            if not server:
                server = await get_server_by_id(subscription.server_id)
            if server:
                from utils.db import generate_subscription_link
                subscription_link = generate_subscription_link(server, subscription.sub_id)
                
                import qrcode
                import io
                # Генерируем QR-код
                qr = qrcode.QRCode(version=1, box_size=10, border=5)
                qr.add_data(subscription_link)
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
        except Exception as e:
            print(f"Ошибка при генерации QR-кода: {e}")
            # Если не удалось сгенерировать, просто не отправляем фото
    
    # Кнопки управления подпиской
    kb = InlineKeyboardBuilder()
    # Не показываем кнопку "Продлить" для приватных подписок (они бессрочные)
    if not subscription.is_private:
        kb.button(text="🔄 Продлить", callback_data=f"renew_subscription_{subscription.id}")
    kb.button(text="🔙 Назад к профилю", callback_data="back_to_profile")
    kb.adjust(1)
    
    try:
        await callback.message.delete()
    except:
        pass
    
    # Отправляем сообщение с фото (если есть) или без
    from core.loader import bot
    try:
        if photo:
            await bot.send_photo(
                chat_id=callback.from_user.id,
                photo=photo,
                caption=text,
                reply_markup=kb.as_markup(),
                parse_mode="HTML"
            )
        else:
            await callback.message.answer(text, reply_markup=kb.as_markup(), parse_mode="HTML")
    except Exception as e:
        logger.error(f"❌ Ошибка при отправке деталей подписки: {type(e).__name__}: {e}")
        # Пытаемся отправить хотя бы текстовое сообщение
        try:
            await callback.message.answer(text, reply_markup=kb.as_markup(), parse_mode="HTML")
        except:
            pass
    
    # Отправляем сообщение с кнопками главного меню, чтобы они всегда были доступны
    # Это нужно после сообщений с inline-кнопками
    try:
        await bot.send_message(
            chat_id=callback.from_user.id,
            text="📱 <b>Главное меню</b>",
            reply_markup=main_menu(),
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"❌ Ошибка при отправке главного меню: {type(e).__name__}: {e}")


@router.callback_query(F.data == "back_to_profile")
async def back_to_profile_handler(callback: types.CallbackQuery):
    """Обработчик возврата к профилю"""
    try:
        await callback.answer()
    except:
        pass
    
    user = await get_user_by_tg_id(str(callback.from_user.id))
    
    if not user:
        try:
            await callback.message.delete()
        except:
            pass
        try:
            await callback.message.answer("❌ Пользователь не найден. Используйте /start", reply_markup=main_menu())
        except Exception as e:
            logger.error(f"❌ Ошибка при отправке сообщения: {type(e).__name__}: {e}")
        return
    
    # Логируем возврат к профилю
    logger.info(f"👤 Пользователь вернулся к профилю (Telegram ID: {user.tg_id}, Sub ID: {user.sub_id})")
    
    # Получаем все подписки пользователя
    subscriptions = await get_user_subscriptions(user.id)
    
    text = "👤 <b>Ваш профиль</b>\n\n"
    
    if subscriptions:
        text += f"📦 <b>У вас подписок: {len(subscriptions)}</b>\n\n"
        text += "Выберите подписку для просмотра детальной информации:"
        
        # Создаем клавиатуру с кнопками подписок
        # Серверы и локации уже загружены через joinedload в get_user_subscriptions
        kb = InlineKeyboardBuilder()
        for sub in subscriptions:
            # Используем загруженные данные (server и location уже доступны)
            server = sub.server if hasattr(sub, 'server') else None
            # Используем название локации вместо названия сервера
            if server and server.location:
                location_name = server.location.name
            else:
                location_name = f"Локация #{sub.server_id}"
            
            # Генерируем идентификатор подписки
            subscription_id = get_subscription_identifier(sub, location_name)
            
            status_emoji = {
                "active": "✅",
                "paused": "⏸️",
                "expired": "❌"
            }.get(sub.status, "❓")
            kb.button(
                text=f"{status_emoji} {location_name} ({subscription_id})",
                callback_data=f"subscription_detail_{sub.id}"
            )
        # Размещаем кнопки по 2 в ряд
        kb.adjust(2)
    else:
        text += "📦 <b>У вас пока нет активных подписок</b>\n\n"
        text += "Приобретите подписку, чтобы начать пользоваться GigaBridge."
        
        # Кнопка для покупки
        kb = InlineKeyboardBuilder()
        kb.button(text="🛒 Приобрести", callback_data="profile_purchase")
        kb.adjust(1)
    
    try:
        await callback.message.delete()
    except:
        pass
    
    try:
        await callback.message.answer(text, reply_markup=kb.as_markup(), parse_mode="HTML")
    except Exception as e:
        logger.error(f"❌ Ошибка при отправке сообщения профиля: {type(e).__name__}: {e}")
    
    # Отправляем сообщение с кнопками главного меню после inline-сообщения
    from core.loader import bot
    try:
        await bot.send_message(
            chat_id=callback.from_user.id,
            text="📱 <b>Главное меню</b>",
            parse_mode="HTML",
            reply_markup=main_menu()
        )
    except Exception as e:
        logger.error(f"❌ Ошибка при отправке главного меню: {type(e).__name__}: {e}")


@router.callback_query(F.data == "profile_purchase")
async def profile_purchase_handler(callback: types.CallbackQuery):
    """Обработчик кнопки покупки из профиля"""
    try:
        await callback.answer()
    except:
        pass
    
    try:
        await callback.message.delete()
    except:
        pass
    
    locations = await get_active_locations()
    
    if not locations:
        await callback.message.answer(
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
        await callback.message.answer(
            "❌ К сожалению, все серверы на доступных локациях заполнены.\n"
            "Попробуйте позже.",
            reply_markup=main_menu()
        )
        return
    
    kb.button(text="❌ Отмена", callback_data="cancel_purchase")
    kb.adjust(1)
    
    await callback.message.answer(text, reply_markup=kb.as_markup(), parse_mode="HTML")


@router.callback_query(F.data.startswith("renew_subscription_"))
async def renew_subscription_handler(callback: types.CallbackQuery, state: FSMContext):
    """Обработчик кнопки 'Продлить' - открывает форму оплаты для продления подписки"""
    try:
        await callback.answer()
    except:
        pass
    
    subscription_id = int(callback.data.split("_")[-1])
    subscription = await get_subscription_by_id(subscription_id)
    
    if not subscription:
        try:
            await callback.message.delete()
        except:
            pass
        try:
            await callback.message.answer("❌ Подписка не найдена", reply_markup=main_menu())
        except:
            pass
        return
    
    # Проверяем, что подписка принадлежит пользователю
    user = await get_user_by_tg_id(str(callback.from_user.id))
    if not user or subscription.user_id != user.id:
        try:
            await callback.message.delete()
        except:
            pass
        try:
            await callback.message.answer("❌ Доступ запрещен", reply_markup=main_menu())
        except:
            pass
        return
    
    # Получаем информацию о сервере и локации
    server = await get_server_by_id(subscription.server_id)
    if not server or not server.location:
        try:
            await callback.message.delete()
        except:
            pass
        try:
            await callback.message.answer("❌ Информация о локации не найдена", reply_markup=main_menu())
        except:
            pass
        return
    
    location = server.location
    
    # Проверяем, активна ли локация
    if not location.is_active:
        try:
            await callback.message.delete()
        except:
            pass
        try:
            await callback.message.answer(
                "❌ Локация неактивна. Пожалуйста, выберите другую локацию для продления.",
                reply_markup=main_menu()
            )
        except:
            pass
        return
    
    # Проверяем, есть ли доступные серверы в локации
    available_server = await select_available_server_for_location(location.id)
    if not available_server:
        try:
            await callback.message.delete()
        except:
            pass
        try:
            await callback.message.answer(
                "❌ К сожалению, все серверы в этой локации переполнены.\n"
                "Попробуйте позже.",
                reply_markup=main_menu()
            )
        except:
            pass
        return
    
    # Сохраняем subscription_id в state для продления
    await state.update_data(
        subscription_id=subscription_id,
        location_id=location.id,
        server_id=server.id,
        previous_message_id=callback.message.message_id,
        is_renewal=True
    )
    
    # Удаляем предыдущее сообщение
    try:
        await callback.message.delete()
    except:
        pass
    
    # Показываем информацию о продлении и кнопку оплаты
    # Получаем тариф для определения длительности
    tariff = await get_tariff_by_id(subscription.tariff_id) if subscription.tariff_id else None
    tariff_duration_days = tariff.duration_days if tariff else 30
    
    # Формируем текст о длительности продления
    if config.TEST_MODE:
        duration_text = "1 минуту"
    else:
        duration_text = f"{tariff_duration_days} дней"
    
    text = f"🔄 <b>Продление подписки</b>\n\n"
    text += f"📍 <b>Локация:</b> {location.name}\n"
    if location.description:
        text += f"📋 {location.description}\n\n"
    
    # В TEST_MODE цена всегда 1 рубль
    from handlers.buy.payment import get_test_price
    final_price = get_test_price(location.price)
    
    text += f"💎 <b>Стоимость продления:</b> {final_price:.0f} ₽\n\n"
    text += f"✨ После оплаты ваша подписка будет продлена на {duration_text}.\n\n"
    text += "💳 Нажмите кнопку ниже, чтобы перейти к оплате:"
    
    # Сохраняем информацию о цене в state
    await state.update_data(
        original_price=get_test_price(location.price),
        final_price=final_price,
        discount_applied=False,
        discount_percent=0.0
    )
    
    kb = InlineKeyboardBuilder()
    kb.button(text=f"💳 Оплатить {final_price:.0f} ₽", callback_data=f"pay_renew_{subscription_id}")
    kb.button(text="❌ Отмена", callback_data="cancel_purchase")
    kb.adjust(1)
    
    new_message = await callback.message.answer(text, reply_markup=kb.as_markup(), parse_mode="HTML")
    # Сохраняем ID нового сообщения
    await state.update_data(payment_message_id=new_message.message_id)
