# handlers/start.py
from aiogram import Router, types
from aiogram.filters import Command
from utils.keyboards.main_kb import main_menu, start_menu
from utils.texts.messages import START_MESSAGE
from database.base import async_session
from database.crud import get_user_by_tg_id, create_user
from utils.db import (
    get_location_by_name,
    get_user_by_tg_id as get_user_by_tg_id_db,
    select_available_server_for_location,
    create_subscription,
    get_tariff_by_id,
    update_server_current_users
)
from services.x3ui_api import get_x3ui_client
from handlers.buy.payment import get_subscription_duration
from datetime import datetime, timedelta
from core.config import config
import uuid as uuid_lib
import html
import logging

logger = logging.getLogger(__name__)

router = Router()

@router.message(Command("start"))
async def start_handler(message: types.Message):
    """Обработчик команды /start - добавляет пользователя в БД, если его еще нет"""
    async with async_session() as session:
        user = await get_user_by_tg_id(session, message.from_user.id)
        if not user:
            await create_user(session, message.from_user.id, message.from_user.username)
    
    # Отправляем стартовое сообщение с inline-кнопками
    # Кнопки управления (ReplyKeyboardMarkup) будут добавлены автоматически через патч
    await message.answer(START_MESSAGE, reply_markup=start_menu())


@router.message(Command("grant_unlimited"))
async def grant_unlimited_handler(message: types.Message):
    """Обработчик команды /grant_unlimited <пароль> <название> - выдача безграничной бессрочной подписки на локацию"""
    # Получаем или создаем пользователя
    user = await get_user_by_tg_id_db(str(message.from_user.id))
    if not user:
        async with async_session() as session:
            user = await create_user(session, message.from_user.id, message.from_user.username)
    
    # Парсим команду: /grant_unlimited <пароль> <название>
    parts = message.text.split(maxsplit=2)
    if len(parts) < 3:
        await message.answer(
            "❌ <b>Неверный формат команды</b>\n\n"
            "Использование: <code>/grant_unlimited &lt;пароль&gt; &lt;название&gt;</code>\n\n"
            "Пример: <code>/grant_unlimited mypassword123 Москва</code>",
            parse_mode="HTML"
        )
        return
    
    password = parts[1].strip()
    location_name = parts[2].strip()
    
    # Проверяем пароль
    if not config.GRANT_UNLIMITED_PASSWORD or config.GRANT_UNLIMITED_PASSWORD != password:
        await message.answer(
            "❌ Неверный пароль для выдачи безграничной подписки.",
            parse_mode="HTML"
        )
        return
    
    # Получаем локацию по названию
    location = await get_location_by_name(location_name)
    if not location:
        await message.answer(
            f"❌ Локация <b>{html.escape(location_name)}</b> не найдена.",
            parse_mode="HTML"
        )
        return
    
    # Проверяем, что локация активна
    if not location.is_active:
        await message.answer(
            f"❌ Локация <b>{html.escape(location_name)}</b> неактивна.",
            parse_mode="HTML"
        )
        return
    
    # Проверяем, есть ли у пользователя уже безграничная подписка на эту локацию
    from utils.db import get_user_subscriptions
    existing_subscriptions = await get_user_subscriptions(user.id)
    for sub in existing_subscriptions:
        if sub.server_id:
            from utils.db import get_server_by_id
            server = await get_server_by_id(sub.server_id)
            if server and server.location_id == location.id and sub.is_private:
                await message.answer(
                    f"✅ У вас уже есть безграничная подписка на локацию <b>{html.escape(location_name)}</b>.",
                    parse_mode="HTML",
                    reply_markup=main_menu()
                )
                return
    
    # Выбираем доступный сервер из локации
    server = await select_available_server_for_location(location.id)
    if not server:
        await message.answer(
            f"❌ К сожалению, все серверы в локации <b>{html.escape(location_name)}</b> переполнены.\n"
            f"Попробуйте позже.",
            parse_mode="HTML"
        )
        return
    
    # Получаем первый доступный тариф
    from database.models import Tariff
    from sqlalchemy import select
    async with async_session() as session:
        result = await session.execute(select(Tariff).order_by(Tariff.id).limit(1))
        tariff = result.scalar_one_or_none()
    
    if not tariff:
        await message.answer("❌ Нет доступных тарифов в системе.")
        return
    
    # Создаем подписку для приватной локации
    try:
        # Создаем клиента в 3x-ui
        x3ui_client = get_x3ui_client(server.api_url, server.api_username, server.api_password, server.ssl_certificate)
        
        # Генерируем уникальный subID для этой подписки
        subscription_sub_id = str(uuid_lib.uuid4())
        
        # Генерируем уникальное название локации
        from utils.db import generate_location_unique_name
        location_unique_name = generate_location_unique_name(location_name, seed=subscription_sub_id)
        
        # Извлекаем уникальный код из location_unique_name (убираем название локации и дефис)
        # Формат: {location_slug}-{unique_code}, нам нужен только unique_code
        unique_code = location_unique_name.split('-')[-1] if '-' in location_unique_name else location_unique_name
        
        # Подготавливаем username для использования в email (как при обычной покупке)
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
        
        # Создаем клиентов во всех инбаундах на основе первого клиента каждого инбаунда
        # Для каждого инбаунда берем первого клиента как шаблон, меняем только уникальные поля
        try:
            create_result = await x3ui_client.add_client_to_all_inbounds(
                location_name=location_slug,
                username=username,
                unique_code=unique_code,
                days=30,  # Для приватных подписок используем стандартную длительность
                tg_id=str(message.from_user.id),
                limit_ip=3,
                sub_id=subscription_sub_id
            )
            
            # Проверяем результат создания
            if not create_result:
                await x3ui_client.close()
                await message.answer("❌ API 3x-ui вернул пустой ответ")
                return
            
            if isinstance(create_result, dict) and create_result.get("error"):
                error_msg = create_result.get("message", "Неизвестная ошибка")
                # Если хотя бы один клиент создан, продолжаем, иначе выбрасываем ошибку
                if len(create_result.get("created", [])) == 0:
                    await x3ui_client.close()
                    await message.answer(f"❌ Ошибка при создании клиентов: {error_msg}")
                    return
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
                
        except Exception as e:
            logger.error(f"❌ Ошибка при создании клиентов: {e}")
            await x3ui_client.close()
            await message.answer(f"❌ Ошибка при создании клиента: {html.escape(str(e))}")
            return
        
        # Для приватных подписок формируем subscription link по sub_id
        from utils.db import generate_subscription_link
        subscription_link = generate_subscription_link(server, subscription_sub_id)
        
        # Сохраняем subscription link в формате JSON для совместимости
        import json
        x3ui_subscription_link = json.dumps([{"subscription_link": subscription_link, "client_email": client_email}], ensure_ascii=False)
        
        await x3ui_client.close()
        
        # Создаем подписку в БД (без expire_date для приватных подписок)
        subscription = await create_subscription(
            user_id=user.id,
            server_id=server.id,
            tariff_id=tariff.id,
            x3ui_client_id=x3ui_subscription_link,
            x3ui_client_email=client_email,
            sub_id=subscription_sub_id,
            location_unique_name=location_unique_name,
            status="active",
            expire_date=None,  # Приватные подписки бессрочные
            traffic_limit=tariff.traffic_limit,
            is_private=True  # Помечаем как приватную
        )
        
        # Обновляем счетчик пользователей на сервере
        await update_server_current_users(server.id)
        
        # Отправляем сообщение пользователю
        from utils.db import get_subscription_identifier
        subscription_id_display = get_subscription_identifier(subscription, location_name)
        
        # Формируем текст с детальной информацией о подписке (как при обычной покупке)
        user_message = f"✅ <b>Безграничная подписка успешно выдана!</b>\n\n"
        user_message += f"📦 <b>{location_name} ({subscription_id_display})</b>\n\n"
        
        # Ссылка на подписку (используем subscription_sub_id, который мы знаем)
        subscription_link = generate_subscription_link(server, subscription_sub_id)
        user_message += f"🔗 <b>Ссылка на подписку:</b>\n"
        user_message += f"<code>{subscription_link}</code>\n\n"
        
        user_message += "🎉 Подписка активна и не требует продления!"
        
        # Генерируем QR-код для ссылки на подписку (как при обычной покупке)
        photo = None
        try:
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
            logger.warning(f"⚠️ Ошибка при генерации QR-кода: {e}")
            # Если не удалось сгенерировать, просто не отправляем фото
        
        # Отправляем сообщение с фото (если есть) или без
        from core.loader import bot
        if photo:
            await bot.send_photo(
                chat_id=message.from_user.id,
                photo=photo,
                caption=user_message,
                reply_markup=main_menu(),
                parse_mode="HTML"
            )
        else:
            await message.answer(user_message, parse_mode="HTML", reply_markup=main_menu())
        
        logger.info(f"✅ Пользователь {user.tg_id} получил безграничную подписку на локацию {location_name}")
        
    except Exception as e:
        logger.error(f"❌ Ошибка при создании приватной подписки: {e}")
        import traceback
        logger.error(traceback.format_exc())
        await message.answer(
            f"❌ Произошла ошибка при создании подписки: {html.escape(str(e))}",
            parse_mode="HTML"
        )
