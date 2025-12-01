"""
Обработчики для оплаты через YooKassa
"""
from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext
from utils.keyboards.main_kb import main_menu, instructions_platform_keyboard
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
    utc_to_user_timezone
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
        # Обычный режим: 30 дней в БД, без ограничения в API
        days_for_api = 0  # 0 = без ограничения по времени в API
        timedelta_for_expire = timedelta(days=30)
        return days_for_api, timedelta_for_expire


class PromoCodeStates(StatesGroup):
    waiting_promo_code = State()


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
    final_price = location.price
    
    has_purchase = await has_user_made_purchase(user.id)
    if not has_purchase and not user.used_first_purchase_discount:
        is_new_user = True
        discount_percent = config.FIRST_PURCHASE_DISCOUNT_PERCENT
        final_price = location.price * (1 - discount_percent / 100)
    
    # Сохраняем информацию о скидке в state
    await state.update_data(
        original_price=location.price,
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
        text += f"💎 <b>Стоимость:</b> {location.price:.0f} ₽\n\n"
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
            payment_data = await yookassa_service.create_payment(
                amount=final_price,
                description=description,
                user_id=str(callback.from_user.id)
            )
        except Exception as payment_error:
            # Обработка ошибок при создании платежа
            error_message = str(payment_error)
            
            # Формируем понятное сообщение для пользователя
            user_error_message = "❌ <b>Ошибка при создании платежа</b>\n\n"
            
            if "авторизации" in error_message.lower() or "authentication" in error_message.lower():
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
                text += f"💰 <b>Цена:</b> <s>{location.price:.0f} ₽</s>\n"
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
    original_price = state_data.get("original_price", location.price)
    promo_discount_percent = promo_code.discount_percent
    final_price = original_price * (1 - promo_discount_percent / 100)
    
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
    
    # Сразу создаем платеж после применения промокода
    try:
        # Формируем описание платежа
        description = f"Подписка на сервис для безопасного и стабильного интернет-доступа: {location.name}"
        if config.TEST_MODE:
            description += " (тестовый режим)"
        description += f" (промокод: {promo_discount_percent:.0f}%)"
        
        # Создаем платеж в YooKassa
        try:
            payment_data = await yookassa_service.create_payment(
                amount=final_price,
                description=description,
                user_id=str(message.from_user.id)
            )
        except Exception as payment_error:
            # Обработка ошибок при создании платежа
            error_message = str(payment_error)
            
            # Формируем понятное сообщение для пользователя
            user_error_message = "❌ <b>Ошибка при создании платежа</b>\n\n"
            
            if "авторизации" in error_message.lower() or "authentication" in error_message.lower():
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
        final_price = state_data.get("final_price", location.price)
        discount_applied = state_data.get("discount_applied", False)
        discount_percent = state_data.get("discount_percent", 0.0)
        promo_code_id = state_data.get("promo_code_id")
        
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
            payment_data = await yookassa_service.create_payment(
                amount=final_price,
                description=description,
                user_id=str(callback.from_user.id)
            )
        except Exception as payment_error:
            # Обработка ошибок при создании платежа
            error_message = str(payment_error)
            
            # Формируем понятное сообщение для пользователя
            user_error_message = "❌ <b>Ошибка при создании платежа</b>\n\n"
            
            if "авторизации" in error_message.lower() or "authentication" in error_message.lower():
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
        print(f"Ошибка: платеж {payment_id} не найден или не удалось обновить статус")
        return
    
    # Дополнительная проверка: убеждаемся, что статус действительно "paid"
    if payment.status != "paid":
        print(f"Ошибка: статус платежа {payment_id} не был установлен как 'paid' (текущий статус: {payment.status})")
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
            print(f"📝 Обновлен username пользователя: {chat.username}")
        # Получаем language_code из чата для определения часового пояса
        language_code = getattr(chat, 'language_code', None)
    except Exception as e:
        print(f"⚠️ Не удалось обновить username пользователя: {e}")
    
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
            
            await update_subscription(
                subscription_id=subscription_id,
                status="active",
                expire_date=new_expire_date,  # Срок действия в БД (1 минута в тесте, 30 дней в обычном режиме)
                traffic_limit=tariff.traffic_limit,
                notification_3_days_sent=False,  # Сбрасываем флаги уведомлений при продлении
                notification_1_day_sent=False
            )
            
            # Включаем клиента на сервере через API при продлении
            if subscription.x3ui_client_email and subscription.server_id:
                renewal_server = await get_server_by_id(subscription.server_id)
                if renewal_server:
                    try:
                        from services.x3ui_api import get_x3ui_client
                        x3ui_client = get_x3ui_client(renewal_server.api_url, renewal_server.api_username, renewal_server.api_password)
                        # Включаем клиента и продлеваем время (если нужно)
                        result = await x3ui_client.update_client(
                            client_email=subscription.x3ui_client_email,
                            enable=True,
                            days=days_for_api
                        )
                        await x3ui_client.close()
                        
                        if result and not result.get("error"):
                            print(f"✅ Клиент {subscription.x3ui_client_email} включен (без ограничения по времени в API)")
                        else:
                            print(f"⚠️ Не удалось обновить клиента {subscription.x3ui_client_email} на сервере")
                    except Exception as e:
                        print(f"⚠️ Ошибка при обновлении клиента на сервере: {e}")
            
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
                print(f"Ошибка при отправке уведомления пользователю: {e}")
            
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
        print(f"🔗 Подключение к 3x-ui API: {server.api_url}")
        x3ui_client = get_x3ui_client(server.api_url, server.api_username, server.api_password)
        
        # Создаем клиента в 3x-ui
        # Email будет использоваться как Telegram username (тег пользователя) + уникальный ID
        # Это позволяет одному пользователю иметь несколько подписок на одном сервере
        import uuid as uuid_lib
        unique_id = str(uuid_lib.uuid4())[:8]  # Берем первые 8 символов UUID для краткости
        
        if user.username:
            # Используем Telegram username + уникальный ID
            client_email = f"{user.username}_{unique_id}"
        else:
            # Fallback: если username нет, используем формат с tg_id + уникальный ID
            client_email = f"user_{user.tg_id}_{unique_id}"
        
        print(f"📝 Создание клиента в 3x-ui:")
        print(f"   Email: {client_email}")
        print(f"   Telegram ID: {user.tg_id}")
        print(f"   Уникальный ID: {unique_id}")
        
        # Получаем длительность подписки (для тестирования или обычный режим)
        days_for_api, duration_timedelta = get_subscription_duration(tariff.duration_days)
        
        # Добавляем клиента (используем метод как в test.py - автоматически использует первый inbound)
        # В tgId отправляем Telegram ID, в email - Telegram username
        # Не передаем total_gb, чтобы не было ограничения по трафику
        add_result = await x3ui_client.add_client(
            email=client_email,
            days=days_for_api,
            tg_id=str(user.tg_id),  # Telegram ID отправляется в поле tgId
            limit_ip=3
            # total_gb не передаем - без ограничения по трафику
        )
        
        # Проверяем, есть ли ошибка в ответе
        if not add_result:
            raise Exception("API 3x-ui вернул пустой ответ")
        
        if isinstance(add_result, dict) and add_result.get("error"):
            error_msg = add_result.get("message", "Неизвестная ошибка")
            status_code = add_result.get("status_code", "?")
            error_type = add_result.get("error_type", "unknown")
            available_ids = add_result.get("available_ids", [])
            
            if error_type == "connection":
                raise Exception(f"Ошибка подключения к 3x-ui API: {error_msg}")
            elif error_type == "inbound_not_found":
                full_error_msg = f"Ошибка API 3x-ui: {error_msg}"
                if available_ids:
                    full_error_msg += f"\n\n💡 Проверьте настройки сервера в админ-панели. Убедитесь, что Inbound ID указан правильно."
                raise Exception(full_error_msg)
            else:
                raise Exception(f"Ошибка API 3x-ui ({status_code}): {error_msg}")
        
        print(f"✅ Клиент успешно создан в 3x-ui: {add_result}")
        
        # Получаем ID клиента из ответа
        # Для VLESS/VMESS это UUID, для TROJAN это password, для Shadowsocks это email
        x3ui_client_id = None
        if isinstance(add_result, dict):
            # Сначала пробуем получить client_id из ответа (UUID, который мы создали)
            x3ui_client_id = add_result.get("client_id") or add_result.get("id") or add_result.get("uuid") or add_result.get("password")
        
        # Если ID не найден в ответе, получаем клиента по email для получения UUID
        if not x3ui_client_id:
            print(f"🔍 UUID не найден в ответе, получаем клиента по email: {client_email}")
            try:
                client_info = await x3ui_client.get_client_by_email(client_email)
                if client_info:
                    # В get_client_by_email возвращается client из settings, где id - это UUID клиента
                    # Для VLESS/VMESS используем id (UUID), для TROJAN - password, для Shadowsocks - email
                    x3ui_client_id = client_info.get("id") or client_info.get("uuid") or client_info.get("password") or client_email
                    print(f"✅ Получен UUID клиента из API: {x3ui_client_id}")
            except Exception as e:
                print(f"⚠️ Ошибка при получении клиента по email: {e}")
        
        # Если все еще не найден, используем email как fallback
        if not x3ui_client_id:
            x3ui_client_id = client_email
            print(f"⚠️ Используем email как ID клиента: {x3ui_client_id}")
        
        print(f"🆔 ID клиента 3x-ui: {x3ui_client_id}")
        print(f"📧 Email клиента: {client_email}")
        
        # Получаем VLESS ключ для клиента
        # Используем уникальный client_email для отображения в конце ссылки (уже содержит уникальный ID)
        x3ui_subscription_link = await x3ui_client.get_client_vless_link(
            client_email=client_email,
            client_username=client_email,  # Используем уникальный email вместо username
            server_pbk=server.pbk
        )
        
        if not x3ui_subscription_link:
            print(f"⚠️ Не удалось сгенерировать VLESS ключ для клиента")
            # Пробуем использовать старый метод как fallback
            x3ui_subscription_link = await x3ui_client.get_client_subscription_link(
                client_email=client_email
            )
            if not x3ui_subscription_link:
                # Если и это не сработало, формируем базовую ссылку
                client_info = await x3ui_client.get_client_by_email(client_email)
                if client_info and client_info.get("inbound_id"):
                    inbound_id = client_info["inbound_id"]
                    base_url = server.api_url.rstrip('/')
                    x3ui_subscription_link = f"{base_url}/sub/{inbound_id}/{x3ui_client_id}"
                    print(f"⚠️ Использована базовая ссылка подписки: {x3ui_subscription_link}")
        else:
            print(f"✅ Получен VLESS ключ: {x3ui_subscription_link[:100]}...")
        
        # Сохраняем данные для создания подписки
        x3ui_client_email = client_email
        
        # Если ссылка все еще не получена, выбрасываем ошибку
        if not x3ui_subscription_link:
            error_msg = f"Не удалось получить ссылку подписки для клиента. Email: {client_email}, ID: {x3ui_client_id}"
            print(f"❌ {error_msg}")
            raise Exception(error_msg)
        
        # Закрываем сессию после использования
        try:
            await x3ui_client.close()
        except Exception as close_error:
            print(f"⚠️ Ошибка при закрытии сессии: {close_error}")
            
    except Exception as e:
        error_msg = f"Ошибка при создании клиента в 3x-ui: {str(e)}"
        print(f"❌ {error_msg}")
        import traceback
        traceback.print_exc()
        
        # Закрываем сессию в случае ошибки
        try:
            if 'x3ui_client' in locals():
                await x3ui_client.close()
        except:
            pass
        
        # Отправляем ошибку пользователю
        try:
            await bot.send_message(
                chat_id=user_id,
                text=f"❌ <b>Ошибка при создании подписки</b>\n\n"
                     f"Произошла ошибка при создании вашей подписки.\n"
                     f"Пожалуйста, свяжитесь с администратором.\n\n"
                     f"<code>{error_msg}</code>",
                reply_markup=main_menu(),
                parse_mode="HTML"
            )
        except:
            pass
        
        # Прерываем выполнение - не создаем подписку без ключа
        raise Exception(error_msg)
    
    # Получаем длительность подписки (для тестирования или обычный режим)
    days_for_api, duration_timedelta = get_subscription_duration(tariff.duration_days)
    
    # Создаем подписку с сроком действия в БД (1 минута в тесте, 30 дней в обычном режиме)
    expire_date = datetime.utcnow() + duration_timedelta
    subscription = await create_subscription(
        user_id=user.id,
        server_id=server_id,
        tariff_id=tariff.id,
        x3ui_client_id=x3ui_subscription_link,  # Сохраняем ссылку подписки
        x3ui_client_email=x3ui_client_email,
        status="active",
        expire_date=expire_date,  # Срок действия в БД (1 минута в тесте, 30 дней в обычном режиме)
        traffic_limit=tariff.traffic_limit
    )
    
    # Отмечаем, что пользователь использовал скидку на первую покупку
    await mark_user_used_discount(user.id)
    
    # Обновляем счетчик пользователей на сервере
    await update_server_current_users(server_id)
    
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
        print(f"✅ Кнопки главного меню отправлены ДО сообщения с ключом (chat_id: {user_id})")
        # Небольшая задержка, чтобы кнопки успели отобразиться
        await asyncio.sleep(0.3)
    except Exception as e:
        print(f"⚠️ Ошибка при отправке кнопок главного меню перед ключом: {e}")
    
    # Отправляем уведомление пользователю с информацией о подписке (как из профиля)
    try:
        location_name = server.location.name if server.location else "Неизвестно"
        
        # Генерируем идентификатор подписки
        subscription_id = get_subscription_identifier(subscription, location_name)
        
        status_emoji = "✅"
        status_text = "Активна"
        
        # Формируем текст с детальной информацией о подписке (как в профиле)
        text = f"📦 <b>{location_name} ({subscription_id}) - {status_emoji} {status_text}</b>\n\n"
        
        # Ключ
        if subscription.x3ui_client_id:
            text += f"🔑 <b>Ваш ключ:</b>\n"
            text += f"<code>{subscription.x3ui_client_id}</code>\n\n"
        
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
            except Exception as e:
                print(f"Ошибка при генерации QR-кода: {e}")
                # Если не удалось сгенерировать, просто не отправляем фото
        
        # Кнопки управления подпиской
        kb = InlineKeyboardBuilder()
        
        # Проверяем, является ли это продлением или первой покупкой
        # При первой покупке (is_renewal=False) не показываем кнопки "Продлить" и "Назад к профилю"
        if is_renewal:
            kb.button(text="🔄 Продлить", callback_data=f"renew_subscription_{subscription.id}")
            kb.button(text="📖 Инструкции", callback_data="show_instructions_after_purchase")
            kb.button(text="🔙 Назад к профилю", callback_data="back_to_profile")
        else:
            # При первой покупке только кнопка инструкций
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
                text=" ",  # Минимальный текст (пробел)
                reply_markup=main_menu()
            )
            print(f"✅ Кнопки главного меню отправлены ПОСЛЕ сообщения с ключом (message_id: {menu_message.message_id})")
        except Exception as e:
            print(f"⚠️ Ошибка при отправке кнопок главного меню после ключа: {e}")
            import traceback
            traceback.print_exc()
    except Exception as e:
        print(f"Ошибка при отправке уведомления пользователю: {e}")


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
        final_price = state_data.get("final_price", location.price)
        
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
            payment_data = await yookassa_service.create_payment(
                amount=final_price,
                description=description,
                user_id=str(callback.from_user.id)
            )
        except Exception as payment_error:
                # Обработка ошибок при создании платежа
                error_message = str(payment_error)
                
                # Формируем понятное сообщение для пользователя
                user_error_message = "❌ <b>Ошибка при создании платежа</b>\n\n"
                
                if "авторизации" in error_message.lower() or "authentication" in error_message.lower():
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
    final_price = location.price
    
    if user:
        has_purchase = await has_user_made_purchase(user.id)
        if not has_purchase and not user.used_first_purchase_discount:
            is_new_user = True
            discount_percent = config.FIRST_PURCHASE_DISCOUNT_PERCENT
            final_price = location.price * (1 - discount_percent / 100)
    
    # Сбрасываем данные промокода в state
    await state.update_data(
        original_price=location.price,
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
        text += f"💰 <b>Цена:</b> <s>{location.price:.0f} ₽</s>\n"
        text += f"💎 <b>Ваша цена:</b> <b>{final_price:.0f} ₽</b>\n"
        text += f"🎁 <b>Скидка {discount_percent:.0f}% на первую покупку!</b>\n\n"
    else:
        text += f"💎 <b>Стоимость:</b> {location.price:.0f} ₽\n\n"
    
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


