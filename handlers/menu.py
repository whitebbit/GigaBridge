from aiogram import F, Router, types
from aiogram.filters import Command
from utils.keyboards.main_kb import main_menu
from utils.db import (
    get_active_platforms,
    get_platform_by_id,
    get_basic_tutorial_for_platform,
    get_additional_tutorials_for_platform
)
from aiogram.utils.keyboard import InlineKeyboardBuilder
from core.loader import bot

router = Router()


@router.message(Command("menu"))
async def menu_handler(message: types.Message):
    try:
        await message.delete()
    except:
        pass
    await message.answer(
        "Выберите действие:",
        reply_markup=main_menu()
    )


@router.callback_query(F.data == "menu")
async def menu_callback(callback: types.CallbackQuery):
    """Обработчик кнопки 'Назад' из админ-панели - возвращает в главное меню"""
    from utils.message_utils import callback_answer_and_save
    await callback_answer_and_save(
        callback,
        "Выберите действие:",
        reply_markup=main_menu()
    )


def instructions_platform_keyboard(platforms):
    """Клавиатура выбора платформы для инструкций"""
    kb = InlineKeyboardBuilder()
    for platform in platforms:
        kb.button(text=platform.display_name, callback_data=f"instructions_platform_{platform.id}")
    kb.adjust(1)
    return kb.as_markup()


@router.message(F.text == "📖 Инструкции")
async def instructions_handler(message: types.Message):
    """Обработчик кнопки Инструкции - показывает выбор платформы"""
    try:
        await message.delete()
    except:
        pass
    
    platforms = await get_active_platforms()
    
    if not platforms:
        await message.answer(
            "📖 <b>Инструкции по использованию</b>\n\n"
            "❌ Инструкции временно недоступны. Попробуйте позже.",
            reply_markup=main_menu(),
            parse_mode="HTML"
        )
        return
    
    await message.answer(
        "📖 <b>Инструкции по использованию</b>\n\n"
        "Выберите платформу:",
        reply_markup=instructions_platform_keyboard(platforms),
        parse_mode="HTML"
    )


async def send_tutorial_with_media(tutorial, chat_id: int, reply_markup=None):
    """Отправить туториал с видео и файлами"""
    text = tutorial.text or "📖 Инструкция"
    last_message = None
    
    # Отправляем видео, если есть
    if tutorial.video_file_id:
        try:
            last_message = await bot.send_video(
                chat_id=chat_id,
                video=tutorial.video_file_id,
                caption=text,
                parse_mode="HTML",
                reply_markup=reply_markup
            )
        except Exception as e:
            # Если видео не удалось отправить, отправляем текст отдельно
            last_message = await bot.send_message(
                chat_id=chat_id, 
                text=text, 
                parse_mode="HTML",
                reply_markup=reply_markup
            )
    elif tutorial.video_note_id:
        try:
            await bot.send_video_note(
                chat_id=chat_id,
                video_note=tutorial.video_note_id
            )
            # Отправляем текст отдельно для видеосообщения
            if text:
                last_message = await bot.send_message(
                    chat_id=chat_id, 
                    text=text, 
                    parse_mode="HTML",
                    reply_markup=reply_markup
                )
        except Exception as e:
            # Если видеосообщение не удалось отправить, отправляем текст
            if text:
                last_message = await bot.send_message(
                    chat_id=chat_id, 
                    text=text, 
                    parse_mode="HTML",
                    reply_markup=reply_markup
                )
    else:
        # Отправляем только текст, если нет видео
        if text:
            last_message = await bot.send_message(
                chat_id=chat_id, 
                text=text, 
                parse_mode="HTML",
                reply_markup=reply_markup
            )
    
    # Отправляем файлы
    from utils.db import get_tutorial_files
    files = await get_tutorial_files(tutorial.id)
    for file in files:
        try:
            await bot.send_document(
                chat_id=chat_id,
                document=file.file_id,
                caption=file.description if file.description else None
            )
        except Exception as e:
            # Пропускаем файл, если не удалось отправить
            pass
    
    return last_message


@router.callback_query(F.data.startswith("instructions_platform_"))
async def instructions_platform_callback(callback: types.CallbackQuery):
    """Инструкция для выбранной платформы"""
    try:
        await callback.answer()
    except:
        pass
    
    platform_id = int(callback.data.split("_")[-1])
    platform = await get_platform_by_id(platform_id)
    
    if not platform:
        await callback.message.answer(
            "❌ Платформа не найдена",
            reply_markup=main_menu()
        )
        return
    
    # Получаем базовый туториал
    basic_tutorial = await get_basic_tutorial_for_platform(platform_id)
    
    if not basic_tutorial:
        await callback.message.answer(
            f"📖 <b>Инструкции для {platform.display_name}</b>\n\n"
            "❌ Инструкции для этой платформы временно недоступны.",
            reply_markup=main_menu(),
            parse_mode="HTML"
        )
        return
    
    # Проверяем, есть ли дополнительные туториалы
    additional_tutorials = await get_additional_tutorials_for_platform(platform_id)
    
    # Создаем клавиатуру с кнопками для дополнительных туториалов
    kb = InlineKeyboardBuilder()
    if additional_tutorials:
        # Добавляем кнопку для каждого дополнительного туториала
        for tutorial in additional_tutorials:
            kb.button(
                text=f"📗 {tutorial.title[:30]}",
                callback_data=f"instructions_tutorial_{tutorial.id}"
            )
        kb.button(text="🔙 Назад к выбору", callback_data="instructions_back")
        kb.adjust(1)
    else:
        kb.button(text="🔙 Назад к выбору", callback_data="instructions_back")
        kb.adjust(1)
    
    # Отправляем базовый туториал с видео и файлами, прикрепляя клавиатуру к последнему сообщению
    await send_tutorial_with_media(basic_tutorial, callback.from_user.id, reply_markup=kb.as_markup())
    
    # Отправляем сообщение с кнопками главного меню
    await bot.send_message(
        chat_id=callback.from_user.id,
        text="📱 <b>Главное меню</b>",
        parse_mode="HTML",
        reply_markup=main_menu()
    )


@router.callback_query(F.data.startswith("instructions_tutorial_"))
async def instructions_tutorial_callback(callback: types.CallbackQuery):
    """Отправка конкретного туториала по ID"""
    try:
        await callback.answer()
    except:
        pass
    
    tutorial_id = int(callback.data.split("_")[-1])
    
    from utils.db import get_tutorial_by_id
    tutorial = await get_tutorial_by_id(tutorial_id)
    
    if not tutorial:
        await callback.message.answer(
            "❌ Туториал не найден",
            reply_markup=main_menu()
        )
        return
    
    # Отправляем туториал
    await send_tutorial_with_media(tutorial, callback.from_user.id)
    
    # Отправляем сообщение с кнопками главного меню после инструкций
    await bot.send_message(
        chat_id=callback.from_user.id,
        text="📱 <b>Главное меню</b>",
        parse_mode="HTML",
        reply_markup=main_menu()
    )


@router.callback_query(F.data == "instructions_back")
async def instructions_back_callback(callback: types.CallbackQuery):
    """Вернуться к выбору платформы"""
    try:
        await callback.answer()
    except:
        pass
    
    platforms = await get_active_platforms()
    
    if not platforms:
        await callback.message.answer(
            "📖 <b>Инструкции по использованию</b>\n\n"
            "❌ Инструкции временно недоступны. Попробуйте позже.",
            reply_markup=main_menu(),
            parse_mode="HTML"
        )
        return
    
    from utils.message_utils import callback_answer_and_save
    await callback_answer_and_save(
        callback,
        "📖 <b>Инструкции по использованию</b>\n\n"
        "Выберите платформу:",
        reply_markup=instructions_platform_keyboard(platforms),
        parse_mode="HTML"
    )


@router.callback_query(F.data == "show_instructions_after_purchase")
async def show_instructions_after_purchase_callback(callback: types.CallbackQuery):
    """Показать инструкции после покупки - НЕ удаляет сообщение с ключом"""
    # Отвечаем на callback без удаления сообщения
    try:
        await callback.answer()
    except:
        pass
    
    platforms = await get_active_platforms()
    
    if not platforms:
        await bot.send_message(
            chat_id=callback.from_user.id,
            text="📖 <b>Инструкции по использованию</b>\n\n"
                 "❌ Инструкции временно недоступны. Попробуйте позже.",
            reply_markup=main_menu(),
            parse_mode="HTML"
        )
        return
    
    # Отправляем новое сообщение с инструкциями, НЕ удаляя старое
    await bot.send_message(
        chat_id=callback.from_user.id,
        text="📖 <b>Инструкции по использованию</b>\n\n"
             "Выберите платформу:",
        reply_markup=instructions_platform_keyboard(platforms),
        parse_mode="HTML"
    )
    
    # Отправляем сообщение с кнопками главного меню после inline-сообщения
    await bot.send_message(
        chat_id=callback.from_user.id,
        text="📱 <b>Главное меню</b>",
        parse_mode="HTML",
        reply_markup=main_menu()
    )


@router.callback_query(F.data == "get_key")
async def get_key_callback(callback: types.CallbackQuery):
    """Обработчик кнопки 'Получить ключ' - открывает список локаций для покупки"""
    
    # Импортируем функции для покупки
    from utils.db import get_active_locations, has_available_server_for_location, get_user_by_tg_id, has_user_made_purchase
    from core.config import config
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    
    locations = await get_active_locations()
    
    if not locations:
        from utils.message_utils import callback_answer_and_save
        await callback_answer_and_save(
            callback,
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
        from utils.message_utils import callback_answer_and_save
        await callback_answer_and_save(
            callback,
            "❌ К сожалению, все серверы на доступных локациях заполнены.\n"
            "Попробуйте позже.",
            reply_markup=main_menu()
        )
        return
    
    kb.button(text="❌ Отмена", callback_data="cancel_purchase")
    kb.adjust(1)
    
    from utils.message_utils import callback_answer_and_save
    await callback_answer_and_save(callback, text, reply_markup=kb.as_markup(), parse_mode="HTML")


@router.callback_query(F.data == "help")
async def help_callback(callback: types.CallbackQuery):
    from utils.texts.messages import HELP_MESSAGE
    from utils.message_utils import callback_answer_and_save
    await callback_answer_and_save(callback, HELP_MESSAGE, parse_mode="HTML", reply_markup=main_menu())
