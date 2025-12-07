"""
Утилиты для работы с сообщениями с автоматическим сохранением ID
"""
from functools import wraps
from typing import Callable, Any
from aiogram.types import Message, CallbackQuery
from aiogram.exceptions import TelegramNetworkError
from aiohttp.client_exceptions import ClientConnectorError
from core.storage import redis_client
import asyncio
import logging

logger = logging.getLogger(__name__)


async def save_bot_message(chat_id: int, user_id: int, message_id: int):
    """
    Сохраняет ID сообщения бота для последующего удаления
    """
    try:
        redis_key = f"last_bot_message:{chat_id}:{user_id}"
        await redis_client.set(redis_key, str(message_id), ex=86400)  # TTL 24 часа
    except Exception:
        pass


async def safe_callback_answer(callback: CallbackQuery, text: str = None, show_alert: bool = False, **kwargs):
    """
    Безопасное ответ на callback с обработкой сетевых ошибок
    
    Args:
        callback: CallbackQuery объект
        text: Текст для ответа (опционально)
        show_alert: Показать алерт (опционально)
        **kwargs: Дополнительные параметры для callback.answer()
    
    Returns:
        bool: True если ответ был успешно отправлен, False если произошла ошибка
    """
    try:
        await callback.answer(text=text, show_alert=show_alert, **kwargs)
        return True
    except TelegramNetworkError as e:
        # Логируем сетевую ошибку, но не прерываем выполнение
        logger.warning(
            f"Network error while answering callback query: {e}. "
            f"Callback data: {callback.data if callback.data else 'N/A'}"
        )
        return False
    except Exception as e:
        # Для других ошибок тоже логируем, но не прерываем
        logger.error(
            f"Unexpected error while answering callback query: {e}. "
            f"Callback data: {callback.data if callback.data else 'N/A'}",
            exc_info=True
        )
        return False


def patch_bot_methods():
    """
    Патчит методы Message.answer() и Bot.send_message() для автоматического добавления кнопок главного меню
    Использует monkey patching через класс
    """
    from aiogram import Bot
    from aiogram.types import ReplyKeyboardMarkup, InlineKeyboardMarkup
    
    # Сохраняем оригинальные методы
    original_message_answer = Message.answer
    original_bot_send_message = Bot.send_message
    original_bot_send_photo = Bot.send_photo
    
    async def patched_message_answer(self: Message, text: str = None, **kwargs) -> Message:
        """Патченный метод Message.answer() с автоматическим добавлением кнопок управления и retry логикой"""
        # Проверяем, есть ли reply_markup в kwargs
        reply_markup = kwargs.get('reply_markup')
        
        # Определяем тип reply_markup
        is_reply_keyboard = isinstance(reply_markup, ReplyKeyboardMarkup) if reply_markup else False
        is_inline_keyboard = isinstance(reply_markup, InlineKeyboardMarkup) if reply_markup else False
        
        # Автоматически добавляем кнопки управления (ReplyKeyboardMarkup) к каждому сообщению
        # НО: только если в сообщении нет ReplyKeyboardMarkup И нет InlineKeyboardMarkup
        # ВАЖНО: В Telegram нельзя одновременно иметь ReplyKeyboardMarkup и InlineKeyboardMarkup
        if not is_reply_keyboard and not is_inline_keyboard:
            from utils.keyboards.main_kb import main_menu
            kwargs['reply_markup'] = main_menu()
        
        # Retry логика для сетевых ошибок
        max_retries = 3
        retry_delay = 2
        last_error = None
        
        for attempt in range(max_retries):
            try:
                # Вызываем оригинальный метод
                if text is None:
                    result = await original_message_answer(self, **kwargs)
                else:
                    result = await original_message_answer(self, text, **kwargs)
                return result
            except (TelegramNetworkError, ClientConnectorError, ConnectionError, TimeoutError, asyncio.TimeoutError) as network_error:
                last_error = network_error
                if attempt < max_retries - 1:
                    logger.warning(
                        f"⚠️ Сетевая ошибка при отправке сообщения через message.answer() "
                        f"(попытка {attempt + 1}/{max_retries}): {type(network_error).__name__}: {network_error}. "
                        f"Повтор через {retry_delay} сек..."
                    )
                    await asyncio.sleep(retry_delay)
                    retry_delay *= 2  # Экспоненциальная задержка
                else:
                    logger.error(
                        f"❌ Не удалось отправить сообщение через message.answer() после {max_retries} попыток: "
                        f"{type(network_error).__name__}: {network_error}"
                    )
                    # Пробрасываем ошибку дальше, чтобы обработчик мог её обработать
                    raise
        
        # Если дошли сюда, значит все попытки исчерпаны
        if last_error:
            raise last_error
    
    async def patched_bot_send_message(self: Bot, chat_id, text: str = None, **kwargs):
        """Патченный метод Bot.send_message() с автоматическим добавлением кнопок управления и retry логикой"""
        # Проверяем, есть ли reply_markup в kwargs
        reply_markup = kwargs.get('reply_markup')
        
        # Определяем тип reply_markup
        is_reply_keyboard = isinstance(reply_markup, ReplyKeyboardMarkup) if reply_markup else False
        is_inline_keyboard = isinstance(reply_markup, InlineKeyboardMarkup) if reply_markup else False
        
        # Автоматически добавляем кнопки управления, если их нет
        if not is_reply_keyboard and not is_inline_keyboard:
            from utils.keyboards.main_kb import main_menu
            kwargs['reply_markup'] = main_menu()
        
        # Retry логика для сетевых ошибок
        max_retries = 3
        retry_delay = 2
        last_error = None
        
        for attempt in range(max_retries):
            try:
                # Вызываем оригинальный метод
                if text is None:
                    return await original_bot_send_message(self, chat_id, **kwargs)
                else:
                    return await original_bot_send_message(self, chat_id, text, **kwargs)
            except (TelegramNetworkError, ClientConnectorError, ConnectionError, TimeoutError, asyncio.TimeoutError) as network_error:
                last_error = network_error
                if attempt < max_retries - 1:
                    logger.warning(
                        f"⚠️ Сетевая ошибка при отправке сообщения через bot.send_message() "
                        f"(попытка {attempt + 1}/{max_retries}): {type(network_error).__name__}: {network_error}. "
                        f"Повтор через {retry_delay} сек..."
                    )
                    await asyncio.sleep(retry_delay)
                    retry_delay *= 2  # Экспоненциальная задержка
                else:
                    logger.error(
                        f"❌ Не удалось отправить сообщение через bot.send_message() после {max_retries} попыток: "
                        f"{type(network_error).__name__}: {network_error}"
                    )
                    # Пробрасываем ошибку дальше, чтобы обработчик мог её обработать
                    raise
        
        # Если дошли сюда, значит все попытки исчерпаны
        if last_error:
            raise last_error
    
    async def patched_bot_send_photo(self: Bot, chat_id, photo, **kwargs):
        """Патченный метод Bot.send_photo() с автоматическим добавлением кнопок управления и retry логикой"""
        # Проверяем, есть ли reply_markup в kwargs
        reply_markup = kwargs.get('reply_markup')
        
        # Определяем тип reply_markup
        is_reply_keyboard = isinstance(reply_markup, ReplyKeyboardMarkup) if reply_markup else False
        is_inline_keyboard = isinstance(reply_markup, InlineKeyboardMarkup) if reply_markup else False
        
        # Автоматически добавляем кнопки управления, если их нет
        if not is_reply_keyboard and not is_inline_keyboard:
            from utils.keyboards.main_kb import main_menu
            kwargs['reply_markup'] = main_menu()
        
        # Retry логика для сетевых ошибок
        max_retries = 3
        retry_delay = 2
        last_error = None
        
        for attempt in range(max_retries):
            try:
                # Вызываем оригинальный метод
                return await original_bot_send_photo(self, chat_id, photo, **kwargs)
            except (TelegramNetworkError, ClientConnectorError, ConnectionError, TimeoutError, asyncio.TimeoutError) as network_error:
                last_error = network_error
                if attempt < max_retries - 1:
                    logger.warning(
                        f"⚠️ Сетевая ошибка при отправке фото через bot.send_photo() "
                        f"(попытка {attempt + 1}/{max_retries}): {type(network_error).__name__}: {network_error}. "
                        f"Повтор через {retry_delay} сек..."
                    )
                    await asyncio.sleep(retry_delay)
                    retry_delay *= 2  # Экспоненциальная задержка
                else:
                    logger.error(
                        f"❌ Не удалось отправить фото через bot.send_photo() после {max_retries} попыток: "
                        f"{type(network_error).__name__}: {network_error}"
                    )
                    # Пробрасываем ошибку дальше, чтобы обработчик мог её обработать
                    raise
        
        # Если дошли сюда, значит все попытки исчерпаны
        if last_error:
            raise last_error
    
    # Применяем патчи на уровне классов
    Message.answer = patched_message_answer
    Bot.send_message = patched_bot_send_message
    Bot.send_photo = patched_bot_send_photo


async def save_bot_message(chat_id: int, user_id: int, message_id: int):
    """
    Сохраняет ID сообщения бота для последующего удаления
    """
    try:
        redis_key = f"last_bot_message:{chat_id}:{user_id}"
        await redis_client.set(redis_key, str(message_id), ex=86400)  # TTL 24 часа
    except Exception:
        pass


async def answer_and_save(message: Message, text: str = None, **kwargs) -> Message:
    """
    Отправляет сообщение и автоматически сохраняет его ID для последующего удаления
    """
    if text is None:
        # Если текст не передан, используем стандартный answer
        sent_message = await message.answer(**kwargs)
    else:
        sent_message = await message.answer(text, **kwargs)
    
    if sent_message:
        await save_bot_message(
            chat_id=sent_message.chat.id,
            user_id=sent_message.from_user.id if sent_message.from_user else message.from_user.id,
            message_id=sent_message.message_id
        )
    return sent_message


async def callback_answer_and_save(callback: CallbackQuery, text: str = None, **kwargs) -> Message:
    """
    Отвечает на callback и автоматически сохраняет ID сообщения для последующего удаления
    Удаляет старое сообщение перед отправкой нового
    
    Если в kwargs нет inline-кнопок, автоматически добавляются кнопки главного меню.
    """
    from aiogram.types import InlineKeyboardMarkup, ReplyKeyboardMarkup
    
    if text:
        # Проверяем, какие клавиатуры уже есть
        reply_markup = kwargs.get('reply_markup')
        has_inline_markup = isinstance(reply_markup, InlineKeyboardMarkup)
        has_reply_keyboard = isinstance(reply_markup, ReplyKeyboardMarkup)
        
        # Если нет никаких клавиатур, добавляем главное меню
        if not has_inline_markup and not has_reply_keyboard:
            from utils.keyboards.main_kb import main_menu
            kwargs['reply_markup'] = main_menu()
        
        # Удаляем старое сообщение перед отправкой нового
        try:
            await callback.message.delete()
        except Exception:
            pass
        
        # Отправляем новое сообщение
        sent_message = await callback.message.answer(text, **kwargs)
        if sent_message:
            await save_bot_message(
                chat_id=sent_message.chat.id,
                user_id=callback.from_user.id,
                message_id=sent_message.message_id
            )
        
        # Отвечаем на callback
        await safe_callback_answer(callback)
        return sent_message
    else:
        # Просто отвечаем на callback без нового сообщения
        await safe_callback_answer(callback)
        return None


def auto_save_message(func: Callable) -> Callable:
    """
    Декоратор для автоматического сохранения ID сообщений, отправленных обработчиком
    Перехватывает вызовы message.answer() и callback.message.answer()
    """
    @wraps(func)
    async def wrapper(*args, **kwargs):
        # Сохраняем оригинальные методы
        message_obj = None
        callback_obj = None
        
        # Ищем Message или CallbackQuery в аргументах
        for arg in args:
            if isinstance(arg, Message):
                message_obj = arg
                # Сохраняем оригинальный метод answer
                original_answer = arg.answer
                
                # Создаем обертку для answer
                async def wrapped_answer(text: str = None, **answer_kwargs):
                    result = await original_answer(text, **answer_kwargs) if text else await original_answer(**answer_kwargs)
                    if result:
                        await save_bot_message(
                            chat_id=result.chat.id,
                            user_id=result.from_user.id if result.from_user else message_obj.from_user.id,
                            message_id=result.message_id
                        )
                    return result
                
                # Заменяем метод answer на обертку
                arg.answer = wrapped_answer
                break
            elif isinstance(arg, CallbackQuery):
                callback_obj = arg
                if arg.message:
                    # Сохраняем оригинальный метод answer
                    original_answer = arg.message.answer
                    
                    # Создаем обертку для answer
                    async def wrapped_answer(text: str = None, **answer_kwargs):
                        result = await original_answer(text, **answer_kwargs) if text else await original_answer(**answer_kwargs)
                        if result:
                            await save_bot_message(
                                chat_id=result.chat.id,
                                user_id=callback_obj.from_user.id,
                                message_id=result.message_id
                            )
                        return result
                    
                    # Заменяем метод answer на обертку
                    arg.message.answer = wrapped_answer
                break
        
        # Выполняем обработчик
        try:
            return await func(*args, **kwargs)
        finally:
            # Восстанавливаем оригинальные методы (опционально, для безопасности)
            pass
    
    return wrapper

