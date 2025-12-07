"""
Обработчики для оплаты через YooKassa
"""
from aiogram import F, Router, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from utils.keyboards.main_kb import main_menu
from utils.logger import logger
from utils.db import (
    get_user_by_tg_id,
    get_server_by_id,
    get_location_by_id,
    get_tariff_by_id,
    create_payment,
    update_payment_status,
    create_subscription,
    get_payment_by_yookassa_id,
    select_available_server_for_location,
    update_server_current_users,
    has_user_made_purchase,
    mark_user_used_discount,
    get_promo_code_by_code,
    can_use_promo_code,
    use_promo_code,
    get_subscription_identifier,
    utc_to_user_timezone,
    update_user_email
)
from aiogram.fsm.state import State, StatesGroup
from core.config import config
from services.yookassa_service import yookassa_service
from datetime import datetime, timedelta
from aiogram.utils.keyboard import InlineKeyboardBuilder
# asyncio больше не нужен для проверки платежей - используется APScheduler

router = Router()


def get_subscription_duration(tariff_duration_days: int) -> tuple[int, timedelta]:
    """
    Получить длительность подписки.
    
    Args:
        tariff_duration_days: Длительность тарифа в днях
    
    Returns:
        tuple: (days_for_api, timedelta_for_expire_date)
        - days_for_api: количество дней для передачи в API 3x-ui (0 = без ограничения)
        - timedelta_for_expire_date: timedelta для установки expire_date в БД
    """
    if config.TEST_MODE:
        # Тестовый режим: подписка на 1 минуту в БД, без ограничения в API
        days_for_api = 0  # 0 = без ограничения по времени в API
        timedelta_for_expire = timedelta(minutes=1)
        return days_for_api, timedelta_for_expire
    else:
        # Обычный режим: используем длительность из тарифа
        days_for_api = 0  # 0 = без ограничения по времени в API
        # Используем реальную длительность тарифа, а не хардкод 30 дней
        timedelta_for_expire = timedelta(days=tariff_duration_days)
        return days_for_api, timedelta_for_expire


def get_test_price(price: float) -> float:
    """
    Получить цену с учетом тестового режима.
    В TEST_MODE всегда возвращает 1 рубль.
    
    Args:
        price: Исходная цена
        
    Returns:
        float: Цена (1.0 в TEST_MODE, иначе исходная цена)
    """
    # Проверяем TEST_MODE напрямую из конфига
    if config.TEST_MODE:
        return 1.0
    # В обычном режиме возвращаем реальную цену
    return price


class PromoCodeStates(StatesGroup):
    waiting_promo_code = State()


class EmailStates(StatesGroup):
    waiting_email = State()


@router.callback_query(F.data.startswith("buy_location_"))
async def select_location_for_payment(callback: types.CallbackQuery, state: FSMContext):
    """Обработчик выбора локации для покупки - сразу создает платеж и перекидывает на страницу оплаты"""
    # Не вызываем callback.answer() здесь, так как для новых пользователей будем использовать callback.answer(url=...)
    location_id = int(callback.data.split("_")[-1])
    location = await get_location_by_id(location_id)
    
    if not location or not location.is_active:
        try:
            await callback.message.delete()
        except:
            pass
        await callback.message.answer("❌ Локация не найдена или неактивна", reply_markup=main_menu())
        return
    
    # Проверяем, есть ли доступные серверы
    available_server = await select_available_server_for_location(location_id)
    if not available_server:
        try:
            await callback.message.delete()
        except:
            pass
        await callback.message.answer(
            "❌ К сожалению, все серверы в этой локации переполнены.\n"
            "Попробуйте выбрать другую локацию или попробуйте позже.",
            reply_markup=main_menu()
        )
        return
    
    # Сохраняем выбранную локацию и ID предыдущего сообщения
    await state.update_data(location_id=location_id, previous_message_id=callback.message.message_id)
    
    # Удаляем предыдущее сообщение со списком локаций
    try:
        await callback.message.delete()
    except:
        pass
    
    # Проверяем, является ли пользователь новым и может ли получить скидку
    user = await get_user_by_tg_id(str(callback.from_user.id))
    if not user:
        await callback.message.answer("❌ Пользователь не найден. Используйте /start", reply_markup=main_menu())
        return
    
    is_new_user = False
    discount_percent = 0.0
    final_price = get_test_price(location.price)
    
    has_purchase = await has_user_made_purchase(user.id)
    if not has_purchase and not user.used_first_purchase_discount:
        is_new_user = True
        discount_percent = config.FIRST_PURCHASE_DISCOUNT_PERCENT
        # В TEST_MODE цена всегда 1, независимо от скидки
        final_price = get_test_price(location.price * (1 - discount_percent / 100))
    
    # Сохраняем информацию о скидке в state
    await state.update_data(
        original_price=get_test_price(location.price),
        final_price=final_price,
        discount_applied=is_new_user,
        discount_percent=discount_percent if is_new_user else 0.0,
        promo_code_id=None,
        promo_code_discount=0.0
    )
    
    # Если это не первая покупка, показываем возможность ввода промокода
    if not is_new_user:
        # Показываем информацию о локации с возможностью ввода промокода
        text = f"🚀 <b>Готовы к покупке?</b>\n\n"
        text += f"📍 <b>Локация:</b> {location.name}\n"
        if location.description:
            text += f"📋 {location.description}\n\n"
        text += f"💎 <b>Стоимость:</b> {get_test_price(location.price):.0f} ₽\n\n"
        text += "✨ После оплаты вы получите:\n"
        text += "   • Персональный ключ\n"
        text += "   • Высокую скорость соединения\n"
        text += "   • Защищенное подключение\n\n"
        
        kb = InlineKeyboardBuilder()
        kb.button(text="🎟️ Ввести промокод", callback_data=f"enter_promo_{location_id}")
        kb.button(text=f"💳 Оплатить {final_price:.0f} ₽", callback_data=f"pay_location_{location_id}")
        kb.button(text="❌ Отмена", callback_data="cancel_purchase")
        kb.adjust(1)
        
        new_message = await callback.message.answer(text, reply_markup=kb.as_markup(), parse_mode="HTML")
        await state.update_data(payment_message_id=new_message.message_id)
        return
    
    # Для новых пользователей проверяем email перед созданием платежа
    # Проверяем наличие email в БД
    if not user.email or not validate_email(user.email):
        # Запрашиваем email
        action_data = {
            "location_id": location_id,
            "final_price": final_price,
            "original_price": get_test_price(location.price),
            "discount_applied": is_new_user,
            "discount_percent": discount_percent if is_new_user else 0.0,
            "promo_code_id": None,
            "promo_code_discount": 0.0,
            "available_server_id": available_server.id
        }
        await check_and_request_email(user, callback, state, action_data)
        return
    
    # Для новых пользователей сразу создаем платеж
    try:
        # Формируем описание платежа
        description = f"Подписка на сервис для безопасного и стабильного интернет-доступа: {location.name}"
        if config.TEST_MODE:
            description += " (тестовый режим)"
        if is_new_user:
            description += f" (скидка {discount_percent:.0f}%)"
        
        # Создаем платеж в YooKassa
        try:
            # Используем email из БД
            customer_email = user.email
            customer_phone = getattr(callback.from_user, 'phone', None)
            
            # Формируем название товара для чека (обрезаем до 128 символов)
            receipt_item_description = description[:128] if len(description) > 128 else description
            
            payment_data = await yookassa_service.create_payment(
                amount=final_price,
                description=description,
                user_id=str(callback.from_user.id),
                customer_email=customer_email,
                customer_phone=customer_phone,
                receipt_item_description=receipt_item_description
            )
        except Exception as payment_error:
            # Обработка ошибок при создании платежа
            error_message = str(payment_error)
            
            # Формируем понятное сообщение для пользователя
            user_error_message = "❌ <b>Ошибка при создании платежа</b>\n\n"
            
            if ("ssl" in error_message.lower() or 
                "подключения" in error_message.lower() or 
                "сетевым" in error_message.lower() or
                "httpsconnectionpool" in error_message.lower() or
                "max retries exceeded" in error_message.lower() or
                "сетевым подключением" in error_message.lower() or
                "платежной системе" in error_message.lower()):
                user_error_message += "Произошла ошибка подключения к платежной системе.\n\n"
                user_error_message += "Возможные причины:\n"
                user_error_message += "• Проблемы с интернет-соединением\n"
                user_error_message += "• Временные проблемы на стороне платежной системы\n\n"
                user_error_message += "Попробуйте создать платеж еще раз через несколько секунд."
            elif "авторизации" in error_message.lower() or "authentication" in error_message.lower():
                user_error_message += "Произошла ошибка авторизации в платежной системе.\n"
                user_error_message += "Пожалуйста, попробуйте позже или свяжитесь с поддержкой."
            elif "некорректные данные" in error_message.lower() or "invalid" in error_message.lower():
                user_error_message += "Произошла ошибка при обработке данных платежа.\n"
                user_error_message += "Пожалуйста, попробуйте еще раз или свяжитесь с поддержкой."
            elif "недостаточно средств" in error_message.lower() or "insufficient" in error_message.lower():
                user_error_message += "Недостаточно средств на счете магазина.\n"
                user_error_message += "Пожалуйста, попробуйте позже или свяжитесь с поддержкой."
            else:
                user_error_message += f"Произошла ошибка: {error_message}\n\n"
                user_error_message += "Пожалуйста, попробуйте позже или свяжитесь с поддержкой."
            
            try:
                await callback.answer("❌ Ошибка при создании платежа")
            except:
                pass
            await callback.message.answer(
                user_error_message,
                reply_markup=main_menu(),
                parse_mode="HTML"
            )
            return
        
        # Сохраняем платеж в БД
        payment = await create_payment(
            tg_id=str(callback.from_user.id),
            amount=final_price,
            server_id=available_server.id,
            yookassa_payment_id=payment_data["id"],
            currency="RUB"
        )
        
        # Сохраняем payment_id в state
        await state.update_data(
            payment_id=payment.id,
            yookassa_payment_id=payment_data["id"]
        )
        
        # Немедленно перекидываем пользователя на страницу оплаты
        try:
            await callback.answer(url=payment_data["confirmation_url"])
        except:
            # Если не получилось через callback.answer, отправляем сообщение с URL-кнопкой
            text = "💳 <b>Переход к оплате</b>\n\n"
            if config.TEST_MODE:
                text += "⚠️ <b>Тестовый режим</b>\n\n"
            text += f"📍 <b>Локация:</b> {location.name}\n"
            if is_new_user:
                text += f"💰 <b>Цена:</b> <s>{get_test_price(location.price):.0f} ₽</s>\n"
                text += f"💎 <b>Ваша цена:</b> <b>{final_price:.0f} ₽</b>\n"
                text += f"🎁 <b>Скидка {discount_percent:.0f}% на первую покупку!</b>\n"
            
            kb = InlineKeyboardBuilder()
            kb.button(text=f"💳 Оплатить {final_price:.0f} ₽", url=payment_data["confirmation_url"])
            kb.button(text="❌ Отмена", callback_data="cancel_payment")
            kb.adjust(1)
            
            new_message = await callback.message.answer(text, reply_markup=kb.as_markup(), parse_mode="HTML")
            await state.update_data(payment_message_id=new_message.message_id)
        
        # Запускаем проверку статуса платежа через APScheduler
        from services.payment_checker import start_payment_check
        start_payment_check(
            yookassa_payment_id=payment_data["id"],
            payment_id=payment.id,
            user_id=callback.from_user.id,
            server_id=available_server.id,
            message_id=callback.message.message_id,  # Используем ID текущего сообщения
            subscription_id=None,
            is_renewal=False
        )
        
    except Exception as e:
        try:
            await callback.answer("❌ Ошибка при создании платежа")
        except:
            pass
        await callback.message.answer(
            f"❌ Ошибка при создании платежа: {str(e)}\n\n"
            "Попробуйте позже или свяжитесь с администратором.",
            reply_markup=main_menu()
        )


@router.callback_query(F.data.startswith("enter_promo_"))
async def enter_promo_code_handler(callback: types.CallbackQuery, state: FSMContext):
    """Обработчик ввода промокода"""
    try:
        await callback.answer()
    except:
        pass
    
    location_id = int(callback.data.split("_")[-1])
    
    # Сохраняем ID сообщения об оплате перед удалением
    state_data = await state.get_data()
    payment_message_id = state_data.get("payment_message_id")
    
    # Удаляем сообщение об оплате, чтобы не было дублирования
    if payment_message_id:
        try:
            await callback.message.bot.delete_message(
                chat_id=callback.message.chat.id,
                message_id=payment_message_id
            )
        except:
            pass
    
    # Также удаляем само сообщение с кнопкой (которое вызвало callback)
    try:
        await callback.message.delete()
    except:
        pass
    
    # Сохраняем location_id в state
    await state.update_data(location_id=location_id)
    
    # Отправляем новое сообщение для ввода промокода
    await callback.message.bot.send_message(
        chat_id=callback.message.chat.id,
        text="🎟️ <b>Введите промокод</b>\n\n"
             "Введите код промокода для получения скидки:",
        reply_markup=cancel_keyboard(),
        parse_mode="HTML"
    )
    await state.set_state(PromoCodeStates.waiting_promo_code)


@router.message(PromoCodeStates.waiting_promo_code)
async def process_promo_code(message: types.Message, state: FSMContext):
    """Обработка введенного промокода"""
    promo_code_text = message.text.strip().upper()
    
    # Получаем данные из state
    state_data = await state.get_data()
    location_id = state_data.get("location_id")
    
    if not location_id:
        await message.answer("❌ Ошибка: данные не найдены. Начните заново.", reply_markup=main_menu())
        await state.clear()
        return
    
    location = await get_location_by_id(location_id)
    if not location or not location.is_active:
        await message.answer("❌ Локация не найдена или неактивна", reply_markup=main_menu())
        await state.clear()
        return
    
    # Проверяем промокод
    promo_code = await get_promo_code_by_code(promo_code_text)
    if not promo_code:
        await message.answer(
            "❌ Промокод не найден. Проверьте правильность ввода.\n\n"
            "Введите промокод еще раз или нажмите 'Отмена':",
            reply_markup=cancel_keyboard()
        )
        return
    
    # Проверяем, может ли пользователь использовать промокод
    user = await get_user_by_tg_id(str(message.from_user.id))
    if not user:
        await message.answer("❌ Пользователь не найден. Используйте /start", reply_markup=main_menu())
        await state.clear()
        return
    
    can_use, error_message = await can_use_promo_code(promo_code, user.id)
    if not can_use:
        await message.answer(
            f"❌ {error_message}\n\n"
            "Введите другой промокод или нажмите 'Отмена':",
            reply_markup=cancel_keyboard()
        )
        return
    
    # Вычисляем цену со скидкой промокода
    # Всегда используем реальную цену локации, а не сохраненное значение из state
    base_price = location.price
    promo_discount_percent = promo_code.discount_percent
    # Пересчитываем цену на основе реальной цены и текущего TEST_MODE
    calculated_price = base_price * (1 - promo_discount_percent / 100)
    final_price = get_test_price(calculated_price)
    original_price = get_test_price(base_price)
    
    # Сохраняем информацию о промокоде в state
    await state.update_data(
        promo_code_id=promo_code.id,
        promo_code_discount=promo_discount_percent,
        final_price=final_price,
        discount_applied=True,
        discount_percent=promo_discount_percent
    )
    
    # Удаляем сообщение о вводе промокода
    try:
        await message.delete()
    except:
        pass
    
    # Автоматически выбираем доступный сервер из локации
    server = await select_available_server_for_location(location_id)
    if not server:
        await message.answer(
            "❌ К сожалению, все серверы в этой локации переполнены.\n"
            "Попробуйте выбрать другую локацию или попробуйте позже.",
            reply_markup=main_menu()
        )
        await state.set_state(None)
        return
    
    # Проверяем наличие email в БД перед созданием платежа
    if not user.email or not validate_email(user.email):
        # Запрашиваем email
        action_data = {
            "location_id": location_id,
            "final_price": final_price,
            "original_price": original_price,
            "discount_applied": True,
            "discount_percent": promo_discount_percent,
            "promo_code_id": promo_code.id,
            "promo_code_discount": promo_discount_percent
        }
        await check_and_request_email(user, message, state, action_data)
        return
    
    # Сразу создаем платеж после применения промокода
    try:
        # Формируем описание платежа
        description = f"Подписка на сервис для безопасного и стабильного интернет-доступа: {location.name}"
        if config.TEST_MODE:
            description += " (тестовый режим)"
        description += f" (промокод: {promo_discount_percent:.0f}%)"
        
        # Создаем платеж в YooKassa
        try:
            # Используем email из БД
            customer_email = user.email
            customer_phone = getattr(message.from_user, 'phone', None)
            
            # Формируем название товара для чека (обрезаем до 128 символов)
            receipt_item_description = description[:128] if len(description) > 128 else description
            
            payment_data = await yookassa_service.create_payment(
                amount=final_price,
                description=description,
                user_id=str(message.from_user.id),
                customer_email=customer_email,
                customer_phone=customer_phone,
                receipt_item_description=receipt_item_description
            )
        except Exception as payment_error:
            # Обработка ошибок при создании платежа
            error_message = str(payment_error)
            
            # Формируем понятное сообщение для пользователя
            user_error_message = "❌ <b>Ошибка при создании платежа</b>\n\n"
            
            if ("ssl" in error_message.lower() or 
                "подключения" in error_message.lower() or 
                "сетевым" in error_message.lower() or
                "httpsconnectionpool" in error_message.lower() or
                "max retries exceeded" in error_message.lower() or
                "сетевым подключением" in error_message.lower() or
                "платежной системе" in error_message.lower()):
                user_error_message += "Произошла ошибка подключения к платежной системе.\n\n"
                user_error_message += "Возможные причины:\n"
                user_error_message += "• Проблемы с интернет-соединением\n"
                user_error_message += "• Временные проблемы на стороне платежной системы\n\n"
                user_error_message += "Попробуйте создать платеж еще раз через несколько секунд."
            elif "авторизации" in error_message.lower() or "authentication" in error_message.lower():
                user_error_message += "Произошла ошибка авторизации в платежной системе.\n"
                user_error_message += "Пожалуйста, попробуйте позже или свяжитесь с поддержкой."
            elif "некорректные данные" in error_message.lower() or "invalid" in error_message.lower():
                user_error_message += "Произошла ошибка при обработке данных платежа.\n"
                user_error_message += "Пожалуйста, попробуйте еще раз или свяжитесь с поддержкой."
            elif "недостаточно средств" in error_message.lower() or "insufficient" in error_message.lower():
                user_error_message += "Недостаточно средств на счете магазина.\n"
                user_error_message += "Пожалуйста, попробуйте позже или свяжитесь с поддержкой."
            else:
                user_error_message += f"Произошла ошибка: {error_message}\n\n"
                user_error_message += "Пожалуйста, попробуйте позже или свяжитесь с поддержкой."
            
            await message.answer(
                user_error_message,
                reply_markup=main_menu(),
                parse_mode="HTML"
            )
            await state.set_state(None)
            return
        
        # Сохраняем платеж в БД
        payment = await create_payment(
            tg_id=str(message.from_user.id),
            amount=final_price,
            server_id=server.id,
            yookassa_payment_id=payment_data["id"],
            currency="RUB"
        )
        
        # Если использован промокод, отмечаем его использование
        await use_promo_code(promo_code.id, user.id, payment.id)
        
        # Сохраняем payment_id в state
        await state.update_data(
            payment_id=payment.id,
            yookassa_payment_id=payment_data["id"]
        )
        
        # Отправляем сообщение с кнопкой оплаты (для message handler нельзя использовать callback.answer)
        text = "✅ <b>Промокод применен!</b>\n\n"
        text += f"🎟️ Промокод: <b>{promo_code.code}</b>\n"
        text += f"💰 Скидка: {promo_discount_percent:.0f}%\n\n"
        if config.TEST_MODE:
            text += "⚠️ <b>Тестовый режим</b>\n\n"
        text += f"📍 <b>Локация:</b> {location.name}\n"
        text += f"💰 <b>Цена:</b> <s>{original_price:.0f} ₽</s>\n"
        text += f"💎 <b>Ваша цена:</b> <b>{final_price:.0f} ₽</b>"
        
        kb = InlineKeyboardBuilder()
        kb.button(text=f"💳 Оплатить {final_price:.0f} ₽", url=payment_data["confirmation_url"])
        kb.button(text="❌ Отмена", callback_data="cancel_payment")
        kb.adjust(1)
        
        new_message = await message.answer(text, reply_markup=kb.as_markup(), parse_mode="HTML")
        # Сохраняем ID сообщения с оплатой
        await state.update_data(payment_message_id=new_message.message_id)
        
        # Запускаем проверку статуса платежа через APScheduler
        from services.payment_checker import start_payment_check
        start_payment_check(
            yookassa_payment_id=payment_data["id"],
            payment_id=payment.id,
            user_id=message.from_user.id,
            server_id=server.id,
            message_id=new_message.message_id,
            subscription_id=None,
            is_renewal=False
        )
        
        await state.set_state(None)  # Сбрасываем состояние
        
    except Exception as e:
        await message.answer(
            f"❌ Ошибка при создании платежа: {str(e)}\n\n"
            "Попробуйте позже или свяжитесь с администратором.",
            reply_markup=main_menu()
        )
        await state.set_state(None)


def cancel_keyboard():
    """Клавиатура отмены ввода промокода"""
    kb = InlineKeyboardBuilder()
    kb.button(text="❌ Отмена", callback_data="cancel_promo_code")
    return kb.as_markup()


def validate_email(email: str) -> bool:
    """Валидация email адреса"""
    import re
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email.strip()))


async def continue_payment_after_email(
    message_or_callback, state: FSMContext, location_id: int, final_price: float,
    original_price: float, discount_applied: bool, discount_percent: float,
    promo_code_id: int, promo_code_discount: float, user
):
    """Продолжает создание платежа после ввода email"""
    from services.payment_checker import start_payment_check
    
    # Получаем дополнительные данные из state (для продления подписки)
    state_data = await state.get_data()
    is_renewal = state_data.get("is_renewal", False)
    subscription_id = state_data.get("subscription_id")
    server_id = state_data.get("server_id")
    
    location = await get_location_by_id(location_id)
    if not location:
        if isinstance(message_or_callback, types.CallbackQuery):
            await message_or_callback.message.answer("❌ Локация не найдена", reply_markup=main_menu())
        else:
            await message_or_callback.answer("❌ Локация не найдена", reply_markup=main_menu())
        await state.clear()
        return
    
    # Для продления используем существующий сервер, для новой покупки - выбираем доступный
    if is_renewal and server_id:
        available_server = await get_server_by_id(server_id)
    else:
        available_server = await select_available_server_for_location(location_id)
    
    if not available_server:
        if isinstance(message_or_callback, types.CallbackQuery):
            await message_or_callback.message.answer(
                "❌ К сожалению, все серверы в этой локации переполнены.",
                reply_markup=main_menu()
            )
        else:
            await message_or_callback.answer(
                "❌ К сожалению, все серверы в этой локации переполнены.",
                reply_markup=main_menu()
            )
        await state.clear()
        return
    
    try:
        # Пересчитываем цену на основе текущего TEST_MODE, а не используем сохраненное значение
        # Получаем реальную цену локации и пересчитываем с учетом скидок
        base_price = location.price
        if discount_applied:
            if promo_code_id:
                calculated_price = base_price * (1 - discount_percent / 100)
            else:
                calculated_price = base_price * (1 - discount_percent / 100)
        else:
            calculated_price = base_price
        
        # Применяем TEST_MODE к пересчитанной цене
        final_price = get_test_price(calculated_price)
        
        # Формируем описание платежа
        description = f"Подписка на сервис для безопасного и стабильного интернет-доступа: {location.name}"
        if config.TEST_MODE:
            description += " (тестовый режим)"
        if discount_applied:
            if promo_code_id:
                description += f" (промокод: {discount_percent:.0f}%)"
            else:
                description += f" (скидка {discount_percent:.0f}%)"
        
        # Используем email из БД
        customer_email = user.email
        customer_phone = None
        if isinstance(message_or_callback, types.CallbackQuery):
            customer_phone = getattr(message_or_callback.from_user, 'phone', None)
        else:
            customer_phone = getattr(message_or_callback.from_user, 'phone', None)
        
        # Формируем название товара для чека
        receipt_item_description = description[:128] if len(description) > 128 else description
        
        payment_data = await yookassa_service.create_payment(
            amount=final_price,
            description=description,
            user_id=str(user.tg_id),
            customer_email=customer_email,
            customer_phone=customer_phone,
            receipt_item_description=receipt_item_description
        )
        
        # Сохраняем платеж в БД
        payment = await create_payment(
            tg_id=str(user.tg_id),
            amount=final_price,
            server_id=available_server.id,
            yookassa_payment_id=payment_data["id"],
            currency="RUB"
        )
        
        # Сохраняем payment_id в state
        await state.update_data(
            payment_id=payment.id,
            yookassa_payment_id=payment_data["id"]
        )
        
        # Перекидываем пользователя на страницу оплаты
        text = "💳 <b>Переход к оплате</b>\n\n"
        if config.TEST_MODE:
            text += "⚠️ <b>Тестовый режим</b>\n\n"
        text += f"📍 <b>Локация:</b> {location.name}\n"
        if discount_applied:
            text += f"💰 <b>Цена:</b> <s>{original_price:.0f} ₽</s>\n"
            text += f"💎 <b>Ваша цена:</b> <b>{final_price:.0f} ₽</b>\n"
            if promo_code_id:
                text += f"🎟️ <b>Скидка по промокоду: {discount_percent:.0f}%</b>\n"
            else:
                text += f"🎁 <b>Скидка {discount_percent:.0f}% на первую покупку!</b>\n"
        
        kb = InlineKeyboardBuilder()
        kb.button(text=f"💳 Оплатить {final_price:.0f} ₽", url=payment_data["confirmation_url"])
        kb.button(text="❌ Отмена", callback_data="cancel_payment")
        kb.adjust(1)
        
        if isinstance(message_or_callback, types.CallbackQuery):
            try:
                await message_or_callback.answer(url=payment_data["confirmation_url"])
            except:
                new_message = await message_or_callback.message.answer(text, reply_markup=kb.as_markup(), parse_mode="HTML")
                await state.update_data(payment_message_id=new_message.message_id)
        else:
            new_message = await message_or_callback.answer(text, reply_markup=kb.as_markup(), parse_mode="HTML")
            await state.update_data(payment_message_id=new_message.message_id)
        
        # Запускаем проверку статуса платежа
        message_id = None
        if isinstance(message_or_callback, types.CallbackQuery):
            message_id = message_or_callback.message.message_id
        else:
            message_id = new_message.message_id
        
        start_payment_check(
            yookassa_payment_id=payment_data["id"],
            payment_id=payment.id,
            user_id=int(user.tg_id),
            server_id=available_server.id,
            message_id=message_id,
            subscription_id=subscription_id if is_renewal else None,
            is_renewal=is_renewal
        )
        
    except Exception as e:
        error_message = str(e)
        user_error_message = "❌ <b>Ошибка при создании платежа</b>\n\n"
        user_error_message += f"Произошла ошибка: {error_message}\n\n"
        user_error_message += "Пожалуйста, попробуйте позже или свяжитесь с поддержкой."
        
        if isinstance(message_or_callback, types.CallbackQuery):
            await message_or_callback.message.answer(user_error_message, reply_markup=main_menu(), parse_mode="HTML")
        else:
            await message_or_callback.answer(user_error_message, reply_markup=main_menu(), parse_mode="HTML")
        await state.clear()


async def check_and_request_email(user, message_or_callback, state: FSMContext, action_data: dict) -> bool:
    """
    Проверяет наличие email у пользователя. Если email отсутствует, запрашивает его.
    
    Args:
        user: Объект User из БД
        message_or_callback: Message или CallbackQuery объект
        state: FSMContext
        action_data: Словарь с данными для сохранения в state (location_id, final_price и т.д.)
    
    Returns:
        True если email есть или был запрошен, False если пользователь отменил
    """
    # Проверяем наличие email в БД
    if user.email and validate_email(user.email):
        return True
    
    # Сохраняем данные действия в state для продолжения после ввода email
    await state.update_data(**action_data, waiting_for_email=True)
    
    # Запрашиваем email
    text = "📧 <b>Для отправки чека требуется ваш email</b>\n\n"
    text += "Пожалуйста, введите ваш email адрес:\n\n"
    text += "Пример: example@mail.ru"
    
    kb = InlineKeyboardBuilder()
    kb.button(text="❌ Отмена", callback_data="cancel_email_input")
    
    if isinstance(message_or_callback, types.CallbackQuery):
        await message_or_callback.message.answer(text, reply_markup=kb.as_markup(), parse_mode="HTML")
        await message_or_callback.answer()
    else:
        await message_or_callback.answer(text, reply_markup=kb.as_markup(), parse_mode="HTML")
    
    await state.set_state(EmailStates.waiting_email)
    return False


@router.callback_query(F.data.startswith("pay_location_"))
async def create_payment_handler(callback: types.CallbackQuery, state: FSMContext):
    """Создание платежа через YooKassa - сразу перекидывает на страницу оплаты"""
    # Не вызываем callback.answer() здесь, так как будем использовать callback.answer(url=...)
    location_id = int(callback.data.split("_")[-1])
    
    user = await get_user_by_tg_id(str(callback.from_user.id))
    if not user:
        await callback.message.answer("❌ Пользователь не найден. Используйте /start", reply_markup=main_menu())
        return
    
    location = await get_location_by_id(location_id)
    if not location or not location.is_active:
        await callback.message.answer("❌ Локация не найдена или неактивна", reply_markup=main_menu())
        return
    
    # Автоматически выбираем доступный сервер из локации
    server = await select_available_server_for_location(location_id)
    if not server:
        await callback.message.answer(
            "❌ К сожалению, все серверы в этой локации переполнены.\n"
            "Попробуйте выбрать другую локацию или попробуйте позже.",
            reply_markup=main_menu()
        )
        return
    
    try:
        # Получаем данные о скидке из state
        state_data = await state.get_data()
        # Пересчитываем цену на основе текущего TEST_MODE, а не используем сохраненное значение
        # Всегда используем реальную цену локации как базовую
        base_price = location.price
        
        discount_applied = state_data.get("discount_applied", False)
        discount_percent = state_data.get("discount_percent", 0.0)
        promo_code_id = state_data.get("promo_code_id")
        promo_code_discount = state_data.get("promo_code_discount", 0.0)
        
        # Пересчитываем финальную цену на основе реальной цены и текущего TEST_MODE
        if discount_applied:
            calculated_price = base_price * (1 - discount_percent / 100)
        else:
            calculated_price = base_price
        
        # Применяем TEST_MODE к пересчитанной цене
        final_price = get_test_price(calculated_price)
        original_price = get_test_price(base_price)
        
        # Проверяем наличие email в БД
        if not user.email or not validate_email(user.email):
            # Запрашиваем email
            action_data = {
                "location_id": location_id,
                "final_price": final_price,
                "original_price": original_price,
                "discount_applied": discount_applied,
                "discount_percent": discount_percent,
                "promo_code_id": promo_code_id,
                "promo_code_discount": promo_code_discount
            }
            await check_and_request_email(user, callback, state, action_data)
            return
        
        # Удаляем предыдущее сообщение с информацией о локации
        try:
            await callback.message.delete()
        except:
            pass
        
        # Создаем платеж через YooKassa
        # Платеж будет тестовым или реальным в зависимости от ключей API
        # Если TEST_MODE=true, добавляем пометку в описание
        # Формируем описание платежа
        description = f"Подписка на сервис для безопасного и стабильного интернет-доступа: {location.name}"
        if config.TEST_MODE:
            description += " (тестовый режим)"
        if discount_applied:
            if promo_code_id:
                description += f" (промокод: {discount_percent:.0f}%)"
            else:
                description += f" (скидка {discount_percent:.0f}%)"
        
        # Создаем платеж в YooKassa
        try:
            # Используем email из БД
            customer_email = user.email
            customer_phone = getattr(callback.from_user, 'phone', None)
            
            # Формируем название товара для чека (обрезаем до 128 символов)
            receipt_item_description = description[:128] if len(description) > 128 else description
            
            payment_data = await yookassa_service.create_payment(
                amount=final_price,
                description=description,
                user_id=str(callback.from_user.id),
                customer_email=customer_email,
                customer_phone=customer_phone,
                receipt_item_description=receipt_item_description
            )
        except Exception as payment_error:
            # Обработка ошибок при создании платежа
            error_message = str(payment_error)
            
            # Формируем понятное сообщение для пользователя
            user_error_message = "❌ <b>Ошибка при создании платежа</b>\n\n"
            
            if ("ssl" in error_message.lower() or 
                "подключения" in error_message.lower() or 
                "сетевым" in error_message.lower() or
                "httpsconnectionpool" in error_message.lower() or
                "max retries exceeded" in error_message.lower() or
                "сетевым подключением" in error_message.lower() or
                "платежной системе" in error_message.lower()):
                user_error_message += "Произошла ошибка подключения к платежной системе.\n\n"
                user_error_message += "Возможные причины:\n"
                user_error_message += "• Проблемы с интернет-соединением\n"
                user_error_message += "• Временные проблемы на стороне платежной системы\n\n"
                user_error_message += "Попробуйте создать платеж еще раз через несколько секунд."
            elif "авторизации" in error_message.lower() or "authentication" in error_message.lower():
                user_error_message += "Произошла ошибка авторизации в платежной системе.\n"
                user_error_message += "Пожалуйста, попробуйте позже или свяжитесь с поддержкой."
            elif "некорректные данные" in error_message.lower() or "invalid" in error_message.lower():
                user_error_message += "Произошла ошибка при обработке данных платежа.\n"
                user_error_message += "Пожалуйста, попробуйте еще раз или свяжитесь с поддержкой."
            elif "недостаточно средств" in error_message.lower() or "insufficient" in error_message.lower():
                user_error_message += "Недостаточно средств на счете магазина.\n"
                user_error_message += "Пожалуйста, попробуйте позже или свяжитесь с поддержкой."
            else:
                user_error_message += f"Произошла ошибка: {error_message}\n\n"
                user_error_message += "Пожалуйста, попробуйте позже или свяжитесь с поддержкой."
            
            try:
                await callback.answer("❌ Ошибка при создании платежа")
            except:
                pass
            await callback.message.answer(
                user_error_message,
                reply_markup=main_menu(),
                parse_mode="HTML"
            )
            return
        
        # Сохраняем платеж в БД
        payment = await create_payment(
            tg_id=str(callback.from_user.id),
            amount=final_price,
            server_id=server.id,
            yookassa_payment_id=payment_data["id"],
            currency="RUB"
        )
        
        # Если использован промокод, отмечаем его использование
        if promo_code_id:
            await use_promo_code(promo_code_id, user.id, payment.id)
        
        # Сохраняем payment_id в state
        await state.update_data(
            payment_id=payment.id,
            yookassa_payment_id=payment_data["id"]
        )
        
        # Немедленно перекидываем пользователя на страницу оплаты
        try:
            await callback.answer(url=payment_data["confirmation_url"])
        except:
            # Если не получилось через callback.answer, отправляем сообщение с URL-кнопкой
            text = "💳 <b>Переход к оплате</b>\n\n"
            if config.TEST_MODE:
                text += "⚠️ <b>Тестовый режим</b>\n\n"
            text += f"📍 <b>Локация:</b> {location.name}\n"
            text += f"💎 <b>Сумма:</b> {final_price:.2f} ₽\n"
            
            kb = InlineKeyboardBuilder()
            kb.button(text=f"💳 Оплатить {final_price:.0f} ₽", url=payment_data["confirmation_url"])
            kb.button(text="❌ Отмена", callback_data="cancel_payment")
            kb.adjust(1)
            
            new_message = await callback.message.answer(text, reply_markup=kb.as_markup(), parse_mode="HTML")
            await state.update_data(payment_message_id=new_message.message_id)
        
        # Запускаем проверку статуса платежа через APScheduler
        from services.payment_checker import start_payment_check
        start_payment_check(
            yookassa_payment_id=payment_data["id"],
            payment_id=payment.id,
            user_id=callback.from_user.id,
            server_id=server.id,
            message_id=callback.message.message_id,  # Используем ID текущего сообщения
            subscription_id=None,
            is_renewal=False
        )
        
    except Exception as e:
        try:
            await callback.answer("❌ Ошибка при создании платежа")
        except:
            pass
        try:
            await callback.message.delete()
        except:
            pass
        await callback.message.answer(
            f"❌ Ошибка при создании платежа: {str(e)}\n\n"
            "Попробуйте позже или свяжитесь с администратором.",
            reply_markup=main_menu()
        )


# Функция check_payment_status удалена - теперь используется APScheduler через services/payment_checker.py


async def handle_successful_payment(payment_id: int, user_id: int, server_id: int, message_id: int = None, subscription_id: int = None, is_renewal: bool = False):
    """Обработка успешного платежа - создание или продление подписки и выдача ключа
    
    ВАЖНО: Эта функция вызывается ТОЛЬКО после подтверждения успешной оплаты через YooKassa API.
    Ключ и инструкции отправляются ТОЛЬКО после успешной оплаты.
    """
    from utils.db import generate_test_key, update_subscription, get_subscription_by_id, get_payment_by_yookassa_id
    from core.loader import bot
    
    # Обновляем статус платежа на "paid" - это подтверждает успешную оплату
    # Функция update_payment_status возвращает обновленный платеж или None
    payment = await update_payment_status(payment_id, "paid")
    
    if not payment:
        logger.error(f"Payment {payment_id} not found or failed to update status")
        return
    
    # Дополнительная проверка: убеждаемся, что статус действительно "paid"
    if payment.status != "paid":
        logger.error(f"Payment {payment_id} status not set to 'paid' (current: {payment.status})")
        return
    
    user = await get_user_by_tg_id(str(user_id))
    if not user:
        return
    
    # Обновляем username пользователя, если он изменился (получаем из Telegram API)
    # Это нужно для того, чтобы всегда использовать актуальный username
    language_code = None
    try:
        from core.loader import bot
        chat = await bot.get_chat(user_id)
        if chat.username and chat.username != user.username:
            from utils.db import update_user
            await update_user(user.id, username=chat.username)
            user.username = chat.username
            logger.debug(f"User username updated: {chat.username}")
        # Получаем language_code из чата для определения часового пояса
        language_code = getattr(chat, 'language_code', None)
    except Exception as e:
        logger.warning(f"Failed to update user username: {e}")
    
    # Получаем информацию о сервере
    server = await get_server_by_id(server_id)
    if not server:
        return
    
    # Получаем или создаем дефолтный тариф
    from database.models import Tariff
    from database.base import async_session
    from sqlalchemy import select
    
    async with async_session() as session:
        result = await session.execute(select(Tariff).limit(1))
        tariff = result.scalar_one_or_none()
        
        if not tariff:
            # Создаем дефолтный тариф
            tariff = Tariff(
                name="Базовый",
                price=0.0,
                duration_days=30,
                traffic_limit=100.0  # 100 GB
            )
            session.add(tariff)
            await session.commit()
            await session.refresh(tariff)
    
    # Если это продление существующей подписки
    if is_renewal and subscription_id:
        subscription = await get_subscription_by_id(subscription_id)
        if subscription and subscription.user_id == user.id:
            # Получаем длительность подписки (для тестирования или обычный режим)
            days_for_api, duration_timedelta = get_subscription_duration(tariff.duration_days)
            
            # Продлеваем подписку (1 минута в тесте, 30 дней в обычном режиме)
            current_expire_date = subscription.expire_date if subscription.expire_date else datetime.utcnow()
            # Если подписка уже истекла, начинаем с текущей даты, иначе продлеваем от даты окончания
            if current_expire_date < datetime.utcnow():
                new_expire_date = datetime.utcnow() + duration_timedelta
            else:
                new_expire_date = current_expire_date + duration_timedelta
            
            # КРИТИЧЕСКИЙ БЛОК: Продление подписки
            # Если здесь произойдет ошибка после успешной оплаты, нужно вернуть средства
            try:
                await update_subscription(
                    subscription_id=subscription_id,
                    status="active",
                    expire_date=new_expire_date,  # Срок действия в БД (1 минута в тесте, 30 дней в обычном режиме)
                    traffic_limit=tariff.traffic_limit,
                    notification_3_days_sent=False,  # Сбрасываем флаги уведомлений при продлении
                    notification_1_day_sent=False
                )
            except Exception as renewal_error:
                # КРИТИЧЕСКАЯ ОШИБКА: Платеж прошел, но подписка не продлена
                error_msg = f"Ошибка при продлении подписки после успешной оплаты: {str(renewal_error)}"
                logger.error(f"{error_msg}")
                import traceback
                logger.error(traceback.format_exc())
                
                # Вместо немедленного возврата средств создаем запись для повторной попытки
                try:
                    from services.subscription_retry import create_failed_attempt
                    
                    # Определяем тип ошибки
                    error_type = "database_error"
                    if "api" in error_msg.lower() or "3x-ui" in error_msg.lower() or "x3ui" in error_msg.lower():
                        error_type = "api_error"
                    elif "database" in error_msg.lower() or "sql" in error_msg.lower():
                        error_type = "database_error"
                    else:
                        error_type = "unknown_error"
                    
                    # Создаем запись о неудачной попытке
                    failed_attempt = await create_failed_attempt(
                        payment_id=payment_id,
                        user_id=user.id,
                        server_id=server_id,
                        error_message=error_msg,
                        error_type=error_type,
                        subscription_id=subscription_id,
                        is_renewal=True
                    )
                    
                    logger.info(
                        f"📝 Создана запись о неудачной попытке продления подписки: "
                        f"attempt_id={failed_attempt.id}, будет повторная попытка через 5 минут"
                    )
                    
                    # Уведомляем пользователя
                    try:
                        await bot.send_message(
                            chat_id=user_id,
                            text=(
                                f"⚠️ <b>Техническая ошибка при продлении подписки</b>\n\n"
                                f"К сожалению, произошла техническая ошибка при продлении вашей подписки после успешной оплаты.\n\n"
                                f"<b>Не беспокойтесь:</b>\n"
                                f"• Платеж успешно обработан\n"
                                f"• Мы автоматически повторим попытку продления подписки\n"
                                f"• Вы получите уведомление, как только подписка будет продлена\n\n"
                                f"<b>Детали:</b>\n"
                                f"• Платеж: {payment.amount:.2f} ₽\n"
                                f"• ID платежа: {payment_id}\n"
                                f"• ID подписки: {subscription_id}\n\n"
                                f"Если подписка не будет продлена в течение 2 часов, "
                                f"средства будут автоматически возвращены на ваш счет."
                            ),
                            reply_markup=main_menu(),
                            parse_mode="HTML"
                        )
                    except Exception as notify_error:
                        logger.error(f"Failed to send notification to user: {notify_error}")
                    
                except Exception as retry_error:
                    # Если не удалось создать запись для повторной попытки,
                    # возвращаемся к старому поведению - пытаемся вернуть средства
                    logger.error(f"❌ Ошибка при создании записи о неудачной попытке: {retry_error}")
                    logger.error(traceback.format_exc())
                    
                    # Получаем yookassa_payment_id для возврата средств
                    yookassa_payment_id = payment.yookassa_payment_id if payment else None
                    
                    # Пытаемся вернуть средства пользователю
                    refund_success = False
                    refund_info = None
                    if yookassa_payment_id:
                        try:
                            refund_info = yookassa_service.refund_payment(
                                payment_id=yookassa_payment_id,
                                description=f"Возврат средств из-за ошибки продления подписки. Payment ID: {payment_id}, Subscription ID: {subscription_id}"
                            )
                            if refund_info:
                                refund_success = True
                                logger.info(f"Refund completed: refund_id={refund_info.get('id')}, amount={refund_info.get('amount')}")
                            else:
                                logger.warning(f"Failed to refund payment {yookassa_payment_id}")
                        except Exception as refund_error:
                            logger.error(f"Refund error: {refund_error}")
                            logger.error(traceback.format_exc())
                    
                    # Уведомляем пользователя
                    try:
                        refund_message = ""
                        if refund_success:
                            refund_message = "\n\n✅ <b>Средства будут возвращены на ваш счет в течение нескольких рабочих дней.</b>"
                        elif yookassa_payment_id:
                            refund_message = "\n\n⚠️ <b>Мы обработаем возврат средств вручную. Пожалуйста, свяжитесь с поддержкой.</b>"
                        
                        await bot.send_message(
                            chat_id=user_id,
                            text=f"❌ <b>Ошибка при продлении подписки</b>\n\n"
                                 f"К сожалению, произошла техническая ошибка при продлении вашей подписки после успешной оплаты.\n\n"
                                 f"<b>Детали:</b>\n"
                                 f"• Платеж: {payment.amount:.2f} ₽\n"
                                 f"• ID платежа: {payment_id}\n"
                                 f"• ID подписки: {subscription_id}\n"
                                 f"{refund_message}\n\n"
                                 f"Пожалуйста, свяжитесь с поддержкой для решения вопроса.",
                            reply_markup=main_menu(),
                            parse_mode="HTML"
                        )
                    except Exception as notify_error:
                        logger.error(f"Failed to send notification to user: {notify_error}")
                    
                    # Логируем ошибку для администратора
                    admin_log_message = (
                        f"🚨 КРИТИЧЕСКАЯ ОШИБКА: Платеж прошел, но подписка не продлена\n"
                        f"• User ID: {user_id}\n"
                        f"• Payment ID: {payment_id}\n"
                        f"• Subscription ID: {subscription_id}\n"
                        f"• YooKassa Payment ID: {yookassa_payment_id}\n"
                        f"• Amount: {payment.amount:.2f} ₽\n"
                        f"• Server ID: {server_id}\n"
                        f"• Ошибка: {error_msg}\n"
                        f"• Возврат средств: {'Успешно' if refund_success else 'Не удалось'}\n"
                        f"• Refund ID: {refund_info.get('id') if refund_info else 'N/A'}"
                    )
                    logger.error(f"\n{'='*80}\n{admin_log_message}\n{'='*80}\n")
                
                # НЕ обновляем статус платежа на "failed" - он остается "paid",
                # чтобы система повторных попыток могла обработать его
                
                # Прерываем выполнение функции
                return
            
            # Обновляем всех клиентов с этим subID на всех инбаундах через API при продлении
            if subscription.sub_id and subscription.server_id:
                renewal_server = await get_server_by_id(subscription.server_id)
                if renewal_server:
                    try:
                        from services.x3ui_api import get_x3ui_client
                        x3ui_client = get_x3ui_client(renewal_server.api_url, renewal_server.api_username, renewal_server.api_password, renewal_server.ssl_certificate)
                        # Обновляем всех клиентов с этим subID на всех инбаундах (включаем и продлеваем время)
                        result = await x3ui_client.update_all_clients_by_sub_id(
                            sub_id=subscription.sub_id,
                            enable=True,
                            days=days_for_api
                        )
                        await x3ui_client.close()
                        
                        if result and not result.get("error"):
                            updated_clients = result.get("updated", [])
                            logger.info(f"Updated {len(updated_clients)} clients with subID {subscription.sub_id} (enabled and extended for {days_for_api} days)")
                        else:
                            error_msg = result.get("message", "Unknown error") if result else "Update error"
                            logger.warning(f"Failed to update clients with subID {subscription.sub_id}: {error_msg}")
                    except Exception as e:
                        logger.warning(f"Error updating clients on server: {e}")
            
            # Удаляем сообщение с оплатой, если есть
            if message_id:
                try:
                    await bot.delete_message(chat_id=user_id, message_id=message_id)
                except:
                    pass
            
            # Отправляем уведомление пользователю
            try:
                location_name = server.location.name if server.location else "Неизвестно"
                
                # Генерируем идентификатор подписки
                subscription_id = get_subscription_identifier(subscription, location_name)
                
                # Формируем текст о длительности продления
                if config.TEST_MODE:
                    duration_text = "1 минуту"
                    date_format = "%d.%m.%Y %H:%M"
                else:
                    duration_text = "30 дней"
                    date_format = "%d.%m.%Y"
                
                # Конвертируем UTC время в локальное время пользователя для отображения
                moscow_expire_date = utc_to_user_timezone(new_expire_date, user=user, language_code=language_code)
                if date_format == "%d.%m.%Y %H:%M":
                    expire_str = moscow_expire_date.strftime("%d.%m.%Y в %H:%M")
                else:
                    expire_str = moscow_expire_date.strftime(date_format)
                
                text = "✅ <b>Подписка продлена!</b>\n\n"
                text += f"📍 Локация: {location_name} ({subscription_id})\n"
                text += f"🔄 Подписка продлена на {duration_text}\n"
                text += f"📅 Новый срок действия: {expire_str}\n\n"
                text += "Вы можете посмотреть детали подписки в разделе <b>Профиль</b>"
                
                await bot.send_message(
                    chat_id=user_id,
                    text=text,
                    reply_markup=main_menu(),
                    parse_mode="HTML"
                )
            except Exception as e:
                logger.error(f"Failed to send notification to user: {e}")
            
            return
    
    # Если это новая подписка
    # Создаем клиента в 3x-ui через API
    x3ui_subscription_link = None
    x3ui_client_email = None
    x3ui_client_id = None
    
    try:
        from services.x3ui_api import get_x3ui_client
        import uuid as uuid_lib
        
        # Сервер уже получен выше, используем его для API подключения
        # Создаем клиент 3x-ui API
        logger.debug(f"Connecting to 3x-ui API: {server.api_url}")
        x3ui_client = get_x3ui_client(server.api_url, server.api_username, server.api_password, server.ssl_certificate)
        
        # Создаем клиента в 3x-ui
        # Email будет использоваться в формате {username}@{location_unique_name}.gigabridge
        # Это позволяет одному пользователю иметь несколько подписок на одном сервере
        
        # Получаем название локации
        location_name = server.location.name if server.location else "Неизвестно"
        
        # Генерируем уникальный subID для этой подписки (будет использован как seed для детерминированной генерации)
        import uuid as uuid_lib
        subscription_sub_id = str(uuid_lib.uuid4())
        
        # Генерируем уникальное название локации (будет использовано для email и идентификатора подписки)
        # Используем subscription_sub_id как seed для детерминированной генерации
        from utils.db import generate_location_unique_name
        location_unique_name = generate_location_unique_name(location_name, seed=subscription_sub_id)
        
        # Извлекаем уникальный код из location_unique_name (убираем название локации и дефис)
        # Формат: {location_slug}-{unique_code}, нам нужен только unique_code
        unique_code = location_unique_name.split('-')[-1] if '-' in location_unique_name else location_unique_name
        
        # Подготавливаем username для использования в email
        if user.username:
            username = user.username
        else:
            username = f"user_{user.tg_id}"
        
        # Нормализуем название локации для использования в email (транслитерация в латиницу, lowercase)
        import re
        import unicodedata
        translit_map = {
            'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e', 'ё': 'yo',
            'ж': 'zh', 'з': 'z', 'и': 'i', 'й': 'y', 'к': 'k', 'л': 'l', 'м': 'm',
            'н': 'n', 'о': 'o', 'п': 'p', 'р': 'r', 'с': 's', 'т': 't', 'у': 'u',
            'ф': 'f', 'х': 'h', 'ц': 'ts', 'ч': 'ch', 'ш': 'sh', 'щ': 'sch',
            'ъ': '', 'ы': 'y', 'ь': '', 'э': 'e', 'ю': 'yu', 'я': 'ya'
        }
        normalized = unicodedata.normalize('NFKD', location_name)
        location_slug = ''.join(translit_map.get(char.lower(), char.lower()) for char in normalized)
        location_slug = re.sub(r'[^a-z0-9]', '', location_slug)
        
        logger.debug(f"Creating clients in 3x-ui: username={username}, tg_id={user.tg_id}, location={location_name}, sub_id={subscription_sub_id}")
        
        # Получаем длительность подписки (для тестирования или обычный режим)
        days_for_api, duration_timedelta = get_subscription_duration(tariff.duration_days)
        
        # Создаем клиентов во всех инбаундах на основе первого клиента каждого инбаунда
        # Для каждого инбаунда берем первого клиента как шаблон, меняем только уникальные поля
        # Формат email: {location_name}@{protocol}&{username}&{unique_code}
        create_result = await x3ui_client.add_client_to_all_inbounds(
            location_name=location_slug,
            username=username,
            unique_code=unique_code,
            days=days_for_api,
            tg_id=str(user.tg_id),
            limit_ip=3,
            sub_id=subscription_sub_id
        )
        
        # Проверяем результат создания
        if not create_result:
            raise Exception("API 3x-ui вернул пустой ответ")
        
        if isinstance(create_result, dict) and create_result.get("error"):
            error_msg = create_result.get("message", "Неизвестная ошибка")
            # Если хотя бы один клиент создан, продолжаем, иначе выбрасываем ошибку
            if len(create_result.get("created", [])) == 0:
                raise Exception(f"Ошибка при создании клиентов: {error_msg}")
            else:
                logger.warning(f"⚠️ Создано клиентов: {len(create_result.get('created', []))}, но были ошибки: {error_msg}")
        
        # Получаем email первого созданного клиента для сохранения в БД
        # Или используем формат для VLESS, если есть VLESS инбаунд
        created_clients = create_result.get("created", [])
        if created_clients:
            # Ищем VLESS клиента в первую очередь, если есть
            vless_client = next((c for c in created_clients if c.get("protocol") == "vless"), None)
            if vless_client:
                client_email = vless_client.get("email")
            else:
                # Берем первого созданного клиента
                client_email = created_clients[0].get("email")
        else:
            # Fallback: используем формат для VLESS
            client_email = f"{location_slug}@vless&{username}&{unique_code}"
        
        logger.info(f"✅ Создано клиентов во всех инбаундах: {len(created_clients)}/{create_result.get('total_inbounds', 0)}")
        for client_info in created_clients:
            network = client_info.get('network', 'N/A')
            protocol = client_info.get('protocol', 'N/A')
            logger.info(f"   - Inbound {client_info.get('inbound_id')} ({protocol}, network: {network}): {client_info.get('email')}")
        
        # Получаем ключи подписки по subID (это вернет список ключей для клиентов с этим subID)
        import json
        client_keys_list = await x3ui_client.get_client_keys_from_subscription(
            subscription_sub_id
        )
        
        # Преобразуем список ключей в JSON строку для сохранения в БД
        if client_keys_list:
            x3ui_subscription_link = json.dumps(client_keys_list, ensure_ascii=False)
            logger.info(f"Subscription keys received for {len(client_keys_list)} clients")
        else:
            logger.warning(f"Failed to get subscription keys by subID (inbound may be missing)")
            x3ui_subscription_link = None
        
        # Сохраняем данные для создания подписки
        x3ui_client_email = client_email
        
        # Закрываем сессию после использования
        try:
            await x3ui_client.close()
        except Exception as close_error:
            logger.warning(f"Error closing session: {close_error}")
            
    except Exception as e:
        error_msg = f"Ошибка при создании клиента в 3x-ui: {str(e)}"
        logger.error(f"{error_msg}")
        import traceback
        logger.error(traceback.format_exc())
        
        # Закрываем сессию в случае ошибки
        try:
            if 'x3ui_client' in locals():
                await x3ui_client.close()
        except:
            pass
        
        # Если это ошибка отсутствия инбаунда - это нормально, продолжаем без ключа
        if "инбаунд не найден" in error_msg.lower() or "missing_inbound" in error_msg.lower():
            logger.warning(f"Inbound missing - continuing subscription creation without key")
            x3ui_subscription_link = None
            x3ui_client_email = None
        else:
            # Для других ошибок создаем запись для повторной попытки вместо немедленного исключения
            try:
                from services.subscription_retry import create_failed_attempt
                
                # Определяем тип ошибки
                error_type = "api_error"
                if "connection" in error_msg.lower() or "timeout" in error_msg.lower():
                    error_type = "connection_error"
                elif "authentication" in error_msg.lower() or "auth" in error_msg.lower():
                    error_type = "authentication_error"
                
                # Создаем запись о неудачной попытке
                failed_attempt = await create_failed_attempt(
                    payment_id=payment_id,
                    user_id=user.id,
                    server_id=server_id,
                    error_message=error_msg,
                    error_type=error_type,
                    subscription_id=None,
                    is_renewal=False
                )
                
                logger.info(
                    f"📝 Создана запись о неудачной попытке создания подписки (API ошибка): "
                    f"attempt_id={failed_attempt.id}, будет повторная попытка через 5 минут"
                )
                
                # Уведомляем пользователя
                try:
                    await bot.send_message(
                        chat_id=user_id,
                        text=(
                            f"⚠️ <b>Техническая ошибка при создании подписки</b>\n\n"
                            f"Произошла ошибка при создании вашей подписки на сервере.\n\n"
                            f"<b>Не беспокойтесь:</b>\n"
                            f"• Платеж успешно обработан\n"
                            f"• Мы автоматически повторим попытку создания подписки\n"
                            f"• Вы получите уведомление, как только подписка будет активирована\n\n"
                            f"<b>Детали:</b>\n"
                            f"• Платеж: {payment.amount:.2f} ₽\n"
                            f"• ID платежа: {payment_id}\n\n"
                            f"Если подписка не будет активирована в течение 2 часов, "
                            f"средства будут автоматически возвращены на ваш счет."
                        ),
                        reply_markup=main_menu(),
                        parse_mode="HTML"
                    )
                except Exception as notify_error:
                    logger.error(f"Failed to send notification to user: {notify_error}")
                
                # Прерываем выполнение функции - подписка будет создана при повторной попытке
                return
                
            except Exception as retry_error:
                # Если не удалось создать запись для повторной попытки,
                # пробрасываем исключение дальше
                logger.error(f"❌ Ошибка при создании записи о неудачной попытке: {retry_error}")
                logger.error(traceback.format_exc())
                raise Exception(error_msg)
    
    # Убеждаемся, что переменные определены (на случай если был except блок)
    if 'x3ui_subscription_link' not in locals():
        x3ui_subscription_link = None
    if 'x3ui_client_email' not in locals():
        x3ui_client_email = None
    if 'subscription_sub_id' not in locals():
        import uuid as uuid_lib
        subscription_sub_id = str(uuid_lib.uuid4())
    if 'location_unique_name' not in locals():
        # Генерируем location_unique_name если его нет
        from utils.db import generate_location_unique_name
        location_unique_name = generate_location_unique_name(location_name, seed=subscription_sub_id)
    
    # Получаем длительность подписки (для тестирования или обычный режим)
    days_for_api, duration_timedelta = get_subscription_duration(tariff.duration_days)
    
    # Создаем подписку с сроком действия в БД (1 минута в тесте, 30 дней в обычном режиме)
    expire_date = datetime.utcnow() + duration_timedelta
    
    # КРИТИЧЕСКИЙ БЛОК: Создание подписки и связанных операций
    # Если здесь произойдет ошибка после успешной оплаты, нужно вернуть средства
    subscription = None
    try:
        # Создаем подписку (даже если ключа нет - это нормально, если инбаунд отсутствует)
        subscription = await create_subscription(
            user_id=user.id,
            server_id=server_id,
            tariff_id=tariff.id,
            x3ui_client_id=x3ui_subscription_link,  # Может быть None, если инбаунд отсутствует
            x3ui_client_email=x3ui_client_email,  # Может быть None, если инбаунд отсутствует
            sub_id=subscription_sub_id,  # Уникальный subID для этой подписки
            location_unique_name=location_unique_name,  # Сохраняем уникальное название локации
            status="active",
            expire_date=expire_date,  # Срок действия в БД (1 минута в тесте, 30 дней в обычном режиме)
            traffic_limit=tariff.traffic_limit
        )
        
        # Отмечаем, что пользователь использовал скидку на первую покупку
        await mark_user_used_discount(user.id)
        
        # Обновляем счетчик пользователей на сервере
        await update_server_current_users(server_id)
        
    except Exception as subscription_error:
        # КРИТИЧЕСКАЯ ОШИБКА: Платеж прошел, но подписка не создана
        error_msg = f"Ошибка при создании подписки после успешной оплаты: {str(subscription_error)}"
        logger.error(f"{error_msg}")
        import traceback
        logger.error(traceback.format_exc())
        
        # Вместо немедленного возврата средств создаем запись для повторной попытки
        try:
            from services.subscription_retry import create_failed_attempt
            
            # Определяем тип ошибки
            error_type = "database_error"
            if "3x-ui" in error_msg.lower() or "api" in error_msg.lower() or "x3ui" in error_msg.lower():
                error_type = "api_error"
            elif "database" in error_msg.lower() or "sql" in error_msg.lower():
                error_type = "database_error"
            else:
                error_type = "unknown_error"
            
            # Создаем запись о неудачной попытке
            failed_attempt = await create_failed_attempt(
                payment_id=payment_id,
                user_id=user.id,
                server_id=server_id,
                error_message=error_msg,
                error_type=error_type,
                subscription_id=None,
                is_renewal=False
            )
            
            logger.info(
                f"📝 Создана запись о неудачной попытке создания подписки: "
                f"attempt_id={failed_attempt.id}, будет повторная попытка через 5 минут"
            )
            
            # Уведомляем пользователя
            try:
                await bot.send_message(
                    chat_id=user_id,
                    text=(
                        f"⚠️ <b>Техническая ошибка при создании подписки</b>\n\n"
                        f"К сожалению, произошла техническая ошибка при создании вашей подписки после успешной оплаты.\n\n"
                        f"<b>Не беспокойтесь:</b>\n"
                        f"• Платеж успешно обработан\n"
                        f"• Мы автоматически повторим попытку создания подписки\n"
                        f"• Вы получите уведомление, как только подписка будет активирована\n\n"
                        f"<b>Детали:</b>\n"
                        f"• Платеж: {payment.amount:.2f} ₽\n"
                        f"• ID платежа: {payment_id}\n\n"
                        f"Если подписка не будет активирована в течение 2 часов, "
                        f"средства будут автоматически возвращены на ваш счет."
                    ),
                    reply_markup=main_menu(),
                    parse_mode="HTML"
                )
            except Exception as notify_error:
                logger.error(f"Failed to send notification to user: {notify_error}")
            
        except Exception as retry_error:
            # Если не удалось создать запись для повторной попытки,
            # возвращаемся к старому поведению - пытаемся вернуть средства
            logger.error(f"❌ Ошибка при создании записи о неудачной попытке: {retry_error}")
            logger.error(traceback.format_exc())
            
            # Получаем yookassa_payment_id для возврата средств
            yookassa_payment_id = payment.yookassa_payment_id if payment else None
            
            # Пытаемся вернуть средства пользователю
            refund_success = False
            refund_info = None
            if yookassa_payment_id:
                try:
                    refund_info = yookassa_service.refund_payment(
                        payment_id=yookassa_payment_id,
                        description=f"Возврат средств из-за ошибки создания подписки. Payment ID: {payment_id}"
                    )
                    if refund_info:
                        refund_success = True
                        logger.info(f"Refund completed: refund_id={refund_info.get('id')}, amount={refund_info.get('amount')}")
                    else:
                        logger.warning(f"Failed to refund payment {yookassa_payment_id}")
                except Exception as refund_error:
                    logger.error(f"Refund error: {refund_error}")
                    logger.error(traceback.format_exc())
            
            # Уведомляем пользователя
            try:
                refund_message = ""
                if refund_success:
                    refund_message = "\n\n✅ <b>Средства будут возвращены на ваш счет в течение нескольких рабочих дней.</b>"
                elif yookassa_payment_id:
                    refund_message = "\n\n⚠️ <b>Мы обработаем возврат средств вручную. Пожалуйста, свяжитесь с поддержкой.</b>"
                
                await bot.send_message(
                    chat_id=user_id,
                    text=f"❌ <b>Ошибка при создании подписки</b>\n\n"
                         f"К сожалению, произошла техническая ошибка при создании вашей подписки после успешной оплаты.\n\n"
                         f"<b>Детали:</b>\n"
                         f"• Платеж: {payment.amount:.2f} ₽\n"
                         f"• ID платежа: {payment_id}\n"
                         f"{refund_message}\n\n"
                         f"Пожалуйста, свяжитесь с поддержкой для решения вопроса.",
                    reply_markup=main_menu(),
                    parse_mode="HTML"
                )
            except Exception as notify_error:
                logger.error(f"Failed to send notification to user: {notify_error}")
            
            # Логируем ошибку для администратора
            admin_log_message = (
                f"🚨 КРИТИЧЕСКАЯ ОШИБКА: Платеж прошел, но подписка не создана\n"
                f"• User ID: {user_id}\n"
                f"• Payment ID: {payment_id}\n"
                f"• YooKassa Payment ID: {yookassa_payment_id}\n"
                f"• Amount: {payment.amount:.2f} ₽\n"
                f"• Server ID: {server_id}\n"
                f"• Ошибка: {error_msg}\n"
                f"• Возврат средств: {'Успешно' if refund_success else 'Не удалось'}\n"
                f"• Refund ID: {refund_info.get('id') if refund_info else 'N/A'}"
            )
            logger.error(f"\n{'='*80}\n{admin_log_message}\n{'='*80}\n")
        
        # НЕ обновляем статус платежа на "failed" - он остается "paid",
        # чтобы система повторных попыток могла обработать его
        
        # Прерываем выполнение функции
        return
    
    # Удаляем сообщение с оплатой, если есть
    if message_id:
        try:
            await bot.delete_message(chat_id=user_id, message_id=message_id)
        except:
            pass
    
    # КРИТИЧЕСКИ ВАЖНО: Отправляем кнопки главного меню ДО сообщения с ключом
    # Это гарантирует, что кнопки будут видны даже когда появится сообщение с inline-кнопками
    # Используем небольшой задержку перед отправкой сообщения с ключом
    import asyncio
    try:
        await bot.send_message(
            chat_id=user_id,
            text="✅ <b>Подписка успешно создана!</b>",
            reply_markup=main_menu(),
            parse_mode="HTML"
        )
        logger.debug(f"Main menu buttons sent before key message (chat_id: {user_id})")
        # Небольшая задержка, чтобы кнопки успели отобразиться
        await asyncio.sleep(0.3)
    except Exception as e:
        logger.warning(f"Error sending main menu buttons before key: {e}")
    
    # Отправляем уведомление пользователю с информацией о подписке (как из профиля)
    try:
        location_name = server.location.name if server.location else "Неизвестно"
        
        # Генерируем идентификатор подписки
        subscription_id = get_subscription_identifier(subscription, location_name)
        
        status_emoji = "✅"
        status_text = "Активна"
        
        # Формируем текст с детальной информацией о подписке (как в профиле)
        text = f"📦 <b>{location_name} ({subscription_id}) - {status_emoji} {status_text}</b>\n\n"
        
        # Ссылка на подписку
        if subscription.sub_id:
            # Извлекаем IP адрес из api_url сервера
            from utils.db import generate_subscription_link
            subscription_link = generate_subscription_link(server, subscription.sub_id)
            text += f"🔗 <b>Ссылка на подписку:</b>\n"
            text += f"<code>{subscription_link}</code>\n\n"
        
        # Время действия
        if subscription.expire_date:
            # Конвертируем UTC время в локальное время пользователя для отображения
            if isinstance(subscription.expire_date, datetime):
                # language_code уже получен выше из Telegram API
                local_expire_date = utc_to_user_timezone(subscription.expire_date, user=user, language_code=language_code)
                expire_str = local_expire_date.strftime("%d.%m.%Y в %H:%M")
            else:
                expire_str = str(subscription.expire_date)
            text += f"📅 <b>Окончание подписки:</b> {expire_str}\n"
            
            # Проверяем, сколько времени осталось (используем UTC для расчета)
            time_left = subscription.expire_date - datetime.utcnow()
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
        
        # Генерируем QR-код для ссылки на подписку (если есть sub_id)
        photo = None
        if subscription.sub_id:
            try:
                # Генерируем ссылку на подписку
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
                logger.warning(f"QR code generation error: {e}")
                # Если не удалось сгенерировать, просто не отправляем фото
        
        # Кнопки управления подпиской
        kb = InlineKeyboardBuilder()
        
        # Проверяем, является ли это продлением или первой покупкой
        # При первой покупке (is_renewal=False) не показываем кнопки "Продлить" и "Назад к профилю"
        # Также не показываем кнопку "Продлить" для приватных подписок (они бессрочные)
        if is_renewal and not subscription.is_private:
            kb.button(text="🔄 Продлить", callback_data=f"renew_subscription_{subscription.id}")
            kb.button(text="📖 Инструкции", callback_data="show_instructions_after_purchase")
            kb.button(text="🔙 Назад к профилю", callback_data="back_to_profile")
        else:
            # При первой покупке или для приватных подписок только кнопка инструкций
            kb.button(text="📖 Инструкции", callback_data="show_instructions_after_purchase")
        
        kb.adjust(1)
        
        # Отправляем сообщение с фото (если есть) или без
        if photo:
            sent_key_message = await bot.send_photo(
                chat_id=user_id,
                photo=photo,
                caption=text,
                reply_markup=kb.as_markup(),
                parse_mode="HTML"
            )
        else:
            sent_key_message = await bot.send_message(
                chat_id=user_id,
                text=text,
                reply_markup=kb.as_markup(),
                parse_mode="HTML"
            )
        
        # КРИТИЧЕСКИ ВАЖНО: Отправляем кнопки главного меню ПОСЛЕ сообщения с ключом
        # Telegram скрывает ReplyKeyboard когда показываются inline-кнопки
        # Отправляем новое сообщение с reply-кнопками, чтобы они снова стали видны
        await asyncio.sleep(0.5)  # Задержка для гарантии
        
        try:
            menu_message = await bot.send_message(
                chat_id=user_id,
                text="📱 <b>Главное меню</b>",
                parse_mode="HTML",
                reply_markup=main_menu()
            )
            logger.debug(f"Main menu buttons sent after key message (message_id: {menu_message.message_id})")
        except Exception as e:
            logger.warning(f"Error sending main menu buttons after key: {e}")
            import traceback
            logger.error(traceback.format_exc())
    except Exception as e:
        logger.error(f"Error sending notification to user: {e}")


@router.callback_query(F.data.startswith("pay_renew_"))
async def pay_renew_handler(callback: types.CallbackQuery, state: FSMContext):
    """Обработчик оплаты продления подписки"""
    try:
        await callback.answer()
    except:
        pass
    
    subscription_id = int(callback.data.split("_")[-1])
    
    # Получаем данные из state
    state_data = await state.get_data()
    location_id = state_data.get("location_id")
    server_id = state_data.get("server_id")
    
    if not location_id or not server_id:
        try:
            await callback.message.delete()
        except:
            pass
        try:
            await callback.message.answer("❌ Ошибка: данные не найдены", reply_markup=main_menu())
        except:
            pass
        return
    
    user = await get_user_by_tg_id(str(callback.from_user.id))
    if not user:
        try:
            await callback.message.delete()
        except:
            pass
        try:
            await callback.message.answer("❌ Пользователь не найден. Используйте /start", reply_markup=main_menu())
        except:
            pass
        return
    
    location = await get_location_by_id(location_id)
    if not location or not location.is_active:
        try:
            await callback.message.delete()
        except:
            pass
        try:
            await callback.message.answer("❌ Локация не найдена или неактивна", reply_markup=main_menu())
        except:
            pass
        return
    
    server = await get_server_by_id(server_id)
    if not server:
        try:
            await callback.message.delete()
        except:
            pass
        try:
            await callback.message.answer("❌ Сервер не найден", reply_markup=main_menu())
        except:
            pass
        return
    
    try:
        # Пересчитываем цену на основе текущего TEST_MODE, а не используем сохраненное значение
        # Получаем реальную цену локации
        base_price = location.price
        # Применяем TEST_MODE к реальной цене
        final_price = get_test_price(base_price)
        
        # Проверяем наличие email в БД перед созданием платежа
        if not user.email or not validate_email(user.email):
            # Запрашиваем email
            action_data = {
                "location_id": location_id,
                "server_id": server_id,
                "final_price": final_price,
                "subscription_id": subscription_id,
                "is_renewal": True
            }
            await check_and_request_email(user, callback, state, action_data)
            return
        
        # Удаляем предыдущее сообщение
        try:
            await callback.message.delete()
        except:
            pass
        
        # Создаем платеж через YooKassa
        # Платеж будет тестовым или реальным в зависимости от ключей API
        # Если TEST_MODE=true, добавляем пометку в описание
        description = f"Продление подписки на сервис для безопасного и стабильного интернет-доступа: {location.name}"
        if config.TEST_MODE:
            description += " (тестовый режим)"
        
        try:
            # Используем email из БД
            customer_email = user.email
            customer_phone = getattr(callback.from_user, 'phone', None)
            
            # Формируем название товара для чека (обрезаем до 128 символов)
            receipt_item_description = description[:128] if len(description) > 128 else description
            
            payment_data = await yookassa_service.create_payment(
                amount=final_price,
                description=description,
                user_id=str(callback.from_user.id),
                customer_email=customer_email,
                customer_phone=customer_phone,
                receipt_item_description=receipt_item_description
            )
        except Exception as payment_error:
                # Обработка ошибок при создании платежа
                error_message = str(payment_error)
                
                # Формируем понятное сообщение для пользователя
                user_error_message = "❌ <b>Ошибка при создании платежа</b>\n\n"
                
                if ("ssl" in error_message.lower() or 
                "подключения" in error_message.lower() or 
                "сетевым" in error_message.lower() or
                "httpsconnectionpool" in error_message.lower() or
                "max retries exceeded" in error_message.lower() or
                "сетевым подключением" in error_message.lower() or
                "платежной системе" in error_message.lower()):
                    user_error_message += "Произошла ошибка подключения к платежной системе.\n\n"
                    user_error_message += "Возможные причины:\n"
                    user_error_message += "• Проблемы с интернет-соединением\n"
                    user_error_message += "• Временные проблемы на стороне платежной системы\n\n"
                    user_error_message += "Попробуйте создать платеж еще раз через несколько секунд."
                elif "авторизации" in error_message.lower() or "authentication" in error_message.lower():
                    user_error_message += "Произошла ошибка авторизации в платежной системе.\n"
                    user_error_message += "Пожалуйста, попробуйте позже или свяжитесь с поддержкой."
                elif "некорректные данные" in error_message.lower() or "invalid" in error_message.lower():
                    user_error_message += "Произошла ошибка при обработке данных платежа.\n"
                    user_error_message += "Пожалуйста, попробуйте еще раз или свяжитесь с поддержкой."
                elif "недостаточно средств" in error_message.lower() or "insufficient" in error_message.lower():
                    user_error_message += "Недостаточно средств на счете магазина.\n"
                    user_error_message += "Пожалуйста, попробуйте позже или свяжитесь с поддержкой."
                else:
                    user_error_message += f"Произошла ошибка: {error_message}\n\n"
                    user_error_message += "Пожалуйста, попробуйте позже или свяжитесь с поддержкой."
                
                try:
                    await callback.message.delete()
                except:
                    pass
                await callback.message.answer(
                    user_error_message,
                    reply_markup=main_menu(),
                    parse_mode="HTML"
                )
                return
        
        # Сохраняем платеж в БД
        payment = await create_payment(
            tg_id=str(callback.from_user.id),
            amount=final_price,
            server_id=server_id,
            yookassa_payment_id=payment_data["id"],
            currency="RUB"
        )
        
        # Сохраняем payment_id в state
        await state.update_data(
            payment_id=payment.id,
            yookassa_payment_id=payment_data["id"]
        )
        
        # Отправляем ссылку на оплату
        text = "💳 <b>Оплата продления</b>\n\n"
        if config.TEST_MODE:
            text += "⚠️ <b>Тестовый режим</b>\n"
            text += "Платеж будет создан через YooKassa в тестовом режиме.\n\n"
        text += f"Сумма: {final_price:.2f} ₽\n"
        text += f"Локация: {location.name}\n\n"
        text += "Нажмите на кнопку ниже для перехода к оплате:"
        
        kb = InlineKeyboardBuilder()
        kb.button(text=f"💳 Оплатить {final_price:.0f} ₽", url=payment_data["confirmation_url"])
        kb.button(text="❌ Отмена", callback_data="cancel_payment")
        kb.adjust(1)
        
        new_message = await callback.message.answer(text, reply_markup=kb.as_markup(), parse_mode="HTML")
        # Сохраняем ID сообщения с оплатой
        await state.update_data(payment_message_id=new_message.message_id)
        
        # Запускаем проверку статуса платежа через APScheduler
        from services.payment_checker import start_payment_check
        start_payment_check(
            yookassa_payment_id=payment_data["id"],
            payment_id=payment.id,
            user_id=callback.from_user.id,
            server_id=server_id,
            message_id=new_message.message_id,
            subscription_id=subscription_id,
            is_renewal=True
        )
        
    except Exception as e:
        try:
            await callback.message.delete()
        except:
            pass
        try:
            await callback.message.answer(
                f"❌ Ошибка при создании платежа: {str(e)}\n\n"
                "Попробуйте позже или свяжитесь с администратором.",
                reply_markup=main_menu()
            )
        except:
            pass


@router.callback_query(F.data == "cancel_payment")
async def cancel_payment_handler(callback: types.CallbackQuery, state: FSMContext):
    """Отмена платежа"""
    try:
        await callback.answer()
    except:
        pass
    
    data = await state.get_data()
    yookassa_payment_id = data.get("yookassa_payment_id")
    
    if yookassa_payment_id:
        try:
            yookassa_service.cancel_payment(yookassa_payment_id)
        except:
            pass
    
    await state.clear()
    try:
        await callback.message.delete()
    except:
        pass
    try:
        from utils.message_utils import callback_answer_and_save
        await callback_answer_and_save(callback, "❌ Платеж отменен", reply_markup=main_menu())
    except:
        pass


@router.callback_query(F.data == "cancel_purchase")
async def cancel_purchase_handler(callback: types.CallbackQuery, state: FSMContext):
    """Отмена покупки"""
    await state.clear()
    try:
        await callback.answer()
    except:
        pass
    try:
        await callback.message.delete()
    except:
        pass
    try:
        await callback.message.answer("❌ Покупка отменена", reply_markup=main_menu())
    except:
        pass


async def restore_payment_message(user_id: int, state: FSMContext):
    """Восстановление сообщения об оплате после отмены ввода промокода"""
    from core.loader import bot
    
    state_data = await state.get_data()
    location_id = state_data.get("location_id")
    
    if not location_id:
        return
    
    location = await get_location_by_id(location_id)
    if not location:
        return
    
    # Получаем информацию о пользователе для проверки скидки на первую покупку
    user = await get_user_by_tg_id(str(user_id))
    is_new_user = False
    discount_percent = 0.0
    final_price = get_test_price(location.price)
    
    if user:
        has_purchase = await has_user_made_purchase(user.id)
        if not has_purchase and not user.used_first_purchase_discount:
            is_new_user = True
            discount_percent = config.FIRST_PURCHASE_DISCOUNT_PERCENT
            final_price = get_test_price(location.price * (1 - discount_percent / 100))
    
    # Сбрасываем данные промокода в state
    await state.update_data(
        original_price=get_test_price(location.price),
        final_price=final_price,
        discount_applied=is_new_user,
        discount_percent=discount_percent,
        promo_code_id=None,
        promo_code_discount=0.0
    )
    
    # Формируем текст сообщения об оплате (как при первоначальном показе)
    text = f"🚀 <b>Готовы к покупке?</b>\n\n"
    text += f"📍 <b>Локация:</b> {location.name}\n"
    if location.description:
        text += f"📋 {location.description}\n\n"
    
    if is_new_user:
        text += f"🎉 <b>Специальное предложение для новых пользователей!</b>\n\n"
        text += f"💰 <b>Цена:</b> <s>{get_test_price(location.price):.0f} ₽</s>\n"
        text += f"💎 <b>Ваша цена:</b> <b>{final_price:.0f} ₽</b>\n"
        text += f"🎁 <b>Скидка {discount_percent:.0f}% на первую покупку!</b>\n\n"
    else:
        text += f"💎 <b>Стоимость:</b> {get_test_price(location.price):.0f} ₽\n\n"
    
    text += "✨ После оплаты вы получите:\n"
    text += "   • Персональный ключ\n"
    text += "   • Высокую скорость соединения\n"
    text += "   • Защищенное подключение\n\n"
    
    # Формируем клавиатуру как при первоначальном показе
    kb = InlineKeyboardBuilder()
    # Если это не первая покупка, показываем кнопку ввода промокода
    if not is_new_user and user:
        kb.button(text="🎟️ Ввести промокод", callback_data=f"enter_promo_{location_id}")
    kb.button(text=f"💳 Оплатить {final_price:.0f} ₽", callback_data=f"pay_location_{location_id}")
    kb.button(text="❌ Отмена", callback_data="cancel_purchase")
    kb.adjust(1)
    
    # Отправляем сообщение об оплате
    payment_message = await bot.send_message(
        chat_id=user_id,
        text=text,
        reply_markup=kb.as_markup(),
        parse_mode="HTML"
    )
    
    # Сохраняем ID сообщения об оплате в state
    await state.update_data(payment_message_id=payment_message.message_id)
    
    return payment_message


@router.callback_query(F.data == "cancel_promo_code")
async def cancel_promo_code_callback(callback: types.CallbackQuery, state: FSMContext):
    """Отмена ввода промокода через callback - возвращаемся к сообщению об оплате"""
    try:
        await callback.answer()
    except:
        pass
    
    # Удаляем сообщение о вводе промокода
    try:
        await callback.message.delete()
    except:
        pass
    
    # Сбрасываем состояние ввода промокода
    await state.set_state(None)
    
    # Восстанавливаем сообщение об оплате
    await restore_payment_message(callback.from_user.id, state)


@router.message(PromoCodeStates.waiting_promo_code, F.text == "❌ Отмена")
async def cancel_promo_code_message(message: types.Message, state: FSMContext):
    """Отмена ввода промокода через сообщение - возвращаемся к сообщению об оплате"""
    # Удаляем сообщение о вводе промокода
    try:
        await message.delete()
    except:
        pass
    
    # Сбрасываем состояние ввода промокода
    await state.set_state(None)
    
    # Восстанавливаем сообщение об оплате
    await restore_payment_message(message.from_user.id, state)


@router.message(EmailStates.waiting_email, F.text.startswith("/"))
async def clear_email_state_on_command(message: types.Message, state: FSMContext):
    """Очищаем состояние ожидания email при получении команды"""
    await state.clear()
    # Команда будет обработана соответствующим обработчиком


@router.message(EmailStates.waiting_email, ~F.text.startswith("/"))
async def process_email_input(message: types.Message, state: FSMContext):
    """Обработка введенного email"""
    if not message.text:
        return
    
    email = message.text.strip()
    
    # Валидация email
    if not validate_email(email):
        await message.answer(
            "❌ <b>Неверный формат email</b>\n\n"
            "Пожалуйста, введите корректный email адрес.\n"
            "Пример: example@mail.ru",
            parse_mode="HTML"
        )
        return
    
    # Сохраняем email в БД
    user = await get_user_by_tg_id(str(message.from_user.id))
    if not user:
        await message.answer("❌ Пользователь не найден. Используйте /start", reply_markup=main_menu())
        await state.clear()
        return
    
    await update_user_email(str(message.from_user.id), email)
    user.email = email
    
    await message.answer(f"✅ Email сохранен: {email}\n\nТеперь можно продолжить оплату.")
    
    # Получаем сохраненные данные из state
    state_data = await state.get_data()
    waiting_for_email = state_data.get("waiting_for_email", False)
    
    if not waiting_for_email:
        await state.clear()
        return
    
    # Продолжаем процесс оплаты
    location_id = state_data.get("location_id")
    final_price = state_data.get("final_price")
    original_price = state_data.get("original_price", final_price)
    discount_applied = state_data.get("discount_applied", False)
    discount_percent = state_data.get("discount_percent", 0.0)
    promo_code_id = state_data.get("promo_code_id")
    promo_code_discount = state_data.get("promo_code_discount", 0.0)
    is_renewal = state_data.get("is_renewal", False)
    subscription_id = state_data.get("subscription_id")
    server_id = state_data.get("server_id")
    
    if not location_id or not final_price:
        await message.answer("❌ Ошибка: данные платежа не найдены. Попробуйте начать заново.", reply_markup=main_menu())
        await state.clear()
        return
    
    # Удаляем флаг ожидания email, но сохраняем данные для продления
    await state.update_data(waiting_for_email=False)
    
    # Продолжаем создание платежа
    await continue_payment_after_email(
        message, state, location_id, final_price, original_price,
        discount_applied, discount_percent, promo_code_id, promo_code_discount, user
    )


@router.callback_query(F.data == "cancel_email_input")
async def cancel_email_input_handler(callback: types.CallbackQuery, state: FSMContext):
    """Отмена ввода email"""
    await callback.answer("❌ Ввод email отменен")
    await state.clear()
    await callback.message.answer("❌ Ввод email отменен", reply_markup=main_menu())


