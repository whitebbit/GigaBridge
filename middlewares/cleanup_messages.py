"""
Middleware для автоматической очистки предыдущих сообщений бота
Оставляет в чате только одно активное сообщение
"""
from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery, TelegramObject
from core.storage import redis_client


class CleanupMessagesMiddleware(BaseMiddleware):
    """Middleware для удаления предыдущих сообщений бота"""
    
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        """
        Обрабатывает событие и удаляет предыдущее сообщение бота
        """
        user_id = None
        chat_id = None
        
        # Определяем user_id и chat_id в зависимости от типа события
        if isinstance(event, Message):
            user_id = event.from_user.id if event.from_user else None
            chat_id = event.chat.id
            # Удаляем сообщение пользователя (middleware сделает это автоматически)
            # Но мы также удаляем его здесь для надежности
            try:
                await event.delete()
            except Exception:
                pass
        elif isinstance(event, CallbackQuery):
            user_id = event.from_user.id if event.from_user else None
            if event.message:
                chat_id = event.message.chat.id
        
        if not user_id or not chat_id:
            # Если не можем определить пользователя, пропускаем
            return await handler(event, data)
        
        # Формируем ключи для Redis
        redis_key = f"last_bot_message:{chat_id}:{user_id}"
        menu_key = f"menu_message:{chat_id}:{user_id}"
        
        # УДАЛЯЕМ предыдущее сообщение бота ДО выполнения обработчика
        # Это важно, чтобы удалить сообщение бота, а не только сообщение пользователя
        try:
            # Получаем ID сообщения с кнопками управления для проверки
            menu_message_id_bytes = await redis_client.get(menu_key)
            menu_message_id = None
            if menu_message_id_bytes:
                menu_message_id = menu_message_id_bytes.decode('utf-8') if isinstance(menu_message_id_bytes, bytes) else str(menu_message_id_bytes)
            
            # Получаем ID последнего сообщения бота
            last_message_id_bytes = await redis_client.get(redis_key)
            
            # Удаляем предыдущее сообщение бота, если оно есть
            # НО: проверяем, не является ли это сообщение с кнопками управления
            if last_message_id_bytes:
                # Redis возвращает bytes, нужно декодировать
                last_message_id = last_message_id_bytes.decode('utf-8') if isinstance(last_message_id_bytes, bytes) else str(last_message_id_bytes)
                
                # Если это НЕ сообщение с кнопками управления, удаляем его
                # Сообщение с кнопками управления НЕ должно удаляться
                if menu_message_id != last_message_id:
                    try:
                        from core.loader import bot
                        await bot.delete_message(chat_id=chat_id, message_id=int(last_message_id))
                    except Exception:
                        # Игнорируем ошибки (сообщение могло быть уже удалено)
                        pass
        except Exception:
            # Игнорируем ошибки Redis
            pass
        
        # Выполняем обработчик
        # Патченный Message.answer() автоматически добавит кнопки управления и сохранит ID
        result = await handler(event, data)
        
        return result


async def save_bot_message(chat_id: int, user_id: int, message_id: int):
    """
    Сохраняет ID сообщения бота для последующего удаления
    Вызывается после отправки сообщения ботом
    """
    try:
        redis_key = f"last_bot_message:{chat_id}:{user_id}"
        # Сохраняем как строку для правильной работы с Redis
        await redis_client.set(redis_key, str(message_id), ex=86400)  # TTL 24 часа
    except Exception as e:
        # Логируем ошибки для отладки
        print(f"[SAVE_MESSAGE] Ошибка сохранения сообщения {message_id}: {e}")
        pass

