"""
Сервис для проверки статуса платежей через APScheduler
"""
import json
from typing import Optional, Dict
from services.scheduler import add_job, remove_job
from services.yookassa_service import yookassa_service
from utils.db import (
    update_payment_status,
    get_payment_by_yookassa_id
)
from handlers.buy.payment import handle_successful_payment
from core.storage import redis_client
from core.loader import bot
from utils.keyboards.main_kb import main_menu
import logging

logger = logging.getLogger(__name__)

# Ключи для Redis
PAYMENT_DATA_KEY = "payment:check:{yookassa_payment_id}"
PAYMENT_CHECK_MAX_TIME = 300  # 5 минут в секундах


async def store_payment_check_data(
    yookassa_payment_id: str,
    payment_id: int,
    user_id: int,
    server_id: int,
    message_id: Optional[int] = None,
    subscription_id: Optional[int] = None,
    is_renewal: bool = False
):
    """Сохранить данные платежа для проверки в Redis"""
    data = {
        "payment_id": payment_id,
        "user_id": user_id,
        "server_id": server_id,
        "message_id": message_id,
        "subscription_id": subscription_id,
        "is_renewal": is_renewal,
        "attempts": 0,
        "max_attempts": 60  # 60 попыток по 5 секунд = 5 минут
    }
    
    key = PAYMENT_DATA_KEY.format(yookassa_payment_id=yookassa_payment_id)
    await redis_client.setex(
        key,
        PAYMENT_CHECK_MAX_TIME,
        json.dumps(data)
    )
    logger.debug(f"Данные платежа {yookassa_payment_id} сохранены в Redis")


async def get_payment_check_data(yookassa_payment_id: str) -> Optional[Dict]:
    """Получить данные платежа из Redis"""
    key = PAYMENT_DATA_KEY.format(yookassa_payment_id=yookassa_payment_id)
    data = await redis_client.get(key)
    if data:
        return json.loads(data)
    return None


async def delete_payment_check_data(yookassa_payment_id: str):
    """Удалить данные платежа из Redis"""
    key = PAYMENT_DATA_KEY.format(yookassa_payment_id=yookassa_payment_id)
    await redis_client.delete(key)
    logger.debug(f"Данные платежа {yookassa_payment_id} удалены из Redis")


async def handle_canceled_payment(
    payment_id: int,
    user_id: int,
    message_id: Optional[int],
    yookassa_payment_id: str,
    status: str,
    reason: Optional[str] = None
):
    """Обработка отмененного или проваленного платежа"""
    from utils.db import update_payment_status
    
    # Обновляем статус платежа в БД
    await update_payment_status(payment_id, "failed")
    
    # Формируем сообщение для пользователя
    try:
        error_message = "❌ <b>Платеж не был завершен</b>\n\n"
        
        if status == "canceled":
            error_message += "Платеж был отменен.\n\n"
            error_message += "<b>Возможные причины:</b>\n"
            error_message += "• Вы отменили оплату на странице ЮKassa\n"
            error_message += "• Прервано подключение к интернету во время оплаты\n"
            error_message += "• Закрыта страница оплаты до завершения транзакции\n\n"
            error_message += "💡 <b>Что делать:</b>\n"
            error_message += "• Если вы хотите попробовать снова, нажмите кнопку <b>Покупка</b> в главном меню\n"
            error_message += "• Убедитесь, что у вас стабильное интернет-соединение\n"
            error_message += "• Не закрывайте страницу оплаты до завершения транзакции\n"
            
        elif status == "failed":
            error_message += "Произошла ошибка при обработке платежа.\n\n"
            error_message += "<b>Возможные причины:</b>\n"
            error_message += "• Недостаточно средств на карте\n"
            error_message += "• Банк отклонил транзакцию\n"
            error_message += "• Превышен лимит операции\n"
            error_message += "• Карта заблокирована или истек срок действия\n\n"
            error_message += "💡 <b>Что делать:</b>\n"
            error_message += "• Проверьте баланс карты\n"
            error_message += "• Свяжитесь с банком для уточнения причины отклонения\n"
            error_message += "• Попробуйте другую карту\n"
            error_message += "• Убедитесь, что карта не заблокирована\n\n"
            error_message += "Если проблема сохраняется, свяжитесь с поддержкой."
            
        elif status == "not_found":
            error_message += reason or "Платеж не найден в системе оплаты.\n\n"
            error_message += "<b>Возможные причины:</b>\n"
            error_message += "• Платеж был отменен\n"
            error_message += "• Прервано подключение к интернету во время создания платежа\n"
            error_message += "• Истекло время ожидания платежа\n\n"
            error_message += "💡 <b>Что делать:</b>\n"
            error_message += "• Если вы хотите попробовать снова, нажмите кнопку <b>Покупка</b> в главном меню\n"
            error_message += "• Убедитесь, что у вас стабильное интернет-соединение\n"
            error_message += "• Если вы уже оплатили, но не получили ключ, свяжитесь с поддержкой\n"
            
        elif status == "timeout":
            error_message += "⏱️ " + (reason or "Время ожидания платежа истекло.\n\n")
            error_message += "<b>Возможные причины:</b>\n"
            error_message += "• Вы не завершили оплату на странице ЮKassa\n"
            error_message += "• Прервано подключение к интернету во время оплаты\n"
            error_message += "• Закрыта страница оплаты до завершения транзакции\n"
            error_message += "• Произошла техническая ошибка\n\n"
            error_message += "💡 <b>Если вы уже оплатили, но не получили ключ:</b>\n"
            error_message += "• Подождите несколько минут - платеж может обрабатываться\n"
            error_message += "• Проверьте историю платежей в вашем банке\n"
            error_message += "• Свяжитесь с поддержкой, указав номер платежа\n\n"
            error_message += "💡 <b>Если вы хотите попробовать снова:</b>\n"
            error_message += "• Нажмите кнопку <b>Покупка</b> в главном меню\n"
            error_message += "• Убедитесь, что у вас стабильное интернет-соединение\n"
            error_message += "• Не закрывайте страницу оплаты до завершения транзакции\n"
            
        elif status == "error":
            error_message += "⚠️ " + (reason or "Произошла техническая ошибка.\n\n")
            if not reason or "техническая ошибка" in reason.lower():
                error_message += "<b>Что произошло:</b>\n"
                error_message += "При проверке статуса платежа возникла проблема.\n\n"
            error_message += "💡 <b>Что делать:</b>\n"
            error_message += "• Пожалуйста, свяжитесь с поддержкой\n"
            if reason and "ID платежа" in reason:
                # ID уже есть в reason
                pass
            else:
                error_message += f"• Укажите ID платежа: <code>{yookassa_payment_id[:20]}...</code>\n"
            error_message += "• Мы обязательно разберемся с проблемой\n\n"
            error_message += "Если вы хотите попробовать снова, нажмите кнопку <b>Покупка</b> в главном меню.\n"
        else:
            error_message += "Платеж не был завершен по неизвестной причине.\n\n"
            error_message += "💡 <b>Что делать:</b>\n"
            error_message += "• Если вы хотите попробовать снова, нажмите кнопку <b>Покупка</b> в главном меню\n"
            error_message += "• Если вы уже оплатили, но не получили ключ, свяжитесь с поддержкой\n"
        
        # Удаляем сообщение с оплатой, если есть
        if message_id:
            try:
                await bot.delete_message(chat_id=user_id, message_id=message_id)
            except Exception as e:
                logger.debug(f"Не удалось удалить сообщение {message_id}: {e}")
        
        # Отправляем сообщение пользователю
        await bot.send_message(
            chat_id=user_id,
            text=error_message,
            reply_markup=main_menu(),
            parse_mode="HTML"
        )
        
    except Exception as e:
        logger.error(f"Ошибка при отправке сообщения об отмене платежа пользователю {user_id}: {e}")


async def check_payment_job(yookassa_payment_id: str):
    """Задача для проверки статуса платежа"""
    try:
        # Получаем данные из Redis
        data = await get_payment_check_data(yookassa_payment_id)
        if not data:
            # Данные истекли или были удалены, удаляем задачу
            remove_job(f"check_payment_{yookassa_payment_id}")
            logger.debug(f"Данные платежа {yookassa_payment_id} не найдены, задача удалена")
            return
        
        # Проверяем статус платежа
        payment_status = yookassa_service.get_payment_status(yookassa_payment_id)
        
        if payment_status and payment_status["status"] == "succeeded":
            # Платеж успешен
            await handle_successful_payment(
                payment_id=data["payment_id"],
                user_id=data["user_id"],
                server_id=data["server_id"],
                message_id=data.get("message_id"),
                subscription_id=data.get("subscription_id"),
                is_renewal=data.get("is_renewal", False)
            )
            # Удаляем данные и задачу
            await delete_payment_check_data(yookassa_payment_id)
            remove_job(f"check_payment_{yookassa_payment_id}")
            logger.info(f"Платеж {yookassa_payment_id} успешно обработан")
            
        elif payment_status and payment_status["status"] in ["canceled", "failed"]:
            # Платеж отменен или провален
            await handle_canceled_payment(
                payment_id=data["payment_id"],
                user_id=data["user_id"],
                message_id=data.get("message_id"),
                yookassa_payment_id=yookassa_payment_id,
                status=payment_status["status"]
            )
            await delete_payment_check_data(yookassa_payment_id)
            remove_job(f"check_payment_{yookassa_payment_id}")
            logger.info(f"Платеж {yookassa_payment_id} отменен или провален (статус: {payment_status['status']})")
            
        elif payment_status is None:
            # Платеж не найден в YooKassa - возможно был отменен или удален
            # Проверяем, сколько попыток уже было
            if data["attempts"] >= 3:  # Даем 3 попытки на случай временных проблем с API
                await handle_canceled_payment(
                    payment_id=data["payment_id"],
                    user_id=data["user_id"],
                    message_id=data.get("message_id"),
                    yookassa_payment_id=yookassa_payment_id,
                    status="not_found",
                    reason="Платеж не найден в системе оплаты. Возможно, он был отменен или удален."
                )
                await delete_payment_check_data(yookassa_payment_id)
                remove_job(f"check_payment_{yookassa_payment_id}")
                logger.warning(f"Платеж {yookassa_payment_id} не найден после {data['attempts']} попыток")
            else:
                # Увеличиваем счетчик попыток и продолжаем проверку
                data["attempts"] += 1
                key = PAYMENT_DATA_KEY.format(yookassa_payment_id=yookassa_payment_id)
                ttl = await redis_client.ttl(key)
                await redis_client.setex(
                    key,
                    ttl if ttl > 0 else PAYMENT_CHECK_MAX_TIME,
                    json.dumps(data)
                )
            
        else:
            # Платеж еще в процессе, увеличиваем счетчик попыток
            data["attempts"] += 1
            if data["attempts"] >= data["max_attempts"]:
                # Превышено максимальное количество попыток - таймаут
                await handle_canceled_payment(
                    payment_id=data["payment_id"],
                    user_id=data["user_id"],
                    message_id=data.get("message_id"),
                    yookassa_payment_id=yookassa_payment_id,
                    status="timeout",
                    reason="Время ожидания платежа истекло. Платеж не был завершен в течение 5 минут."
                )
                await delete_payment_check_data(yookassa_payment_id)
                remove_job(f"check_payment_{yookassa_payment_id}")
                logger.warning(f"Превышено максимальное количество попыток для платежа {yookassa_payment_id}")
            else:
                # Обновляем данные в Redis
                key = PAYMENT_DATA_KEY.format(yookassa_payment_id=yookassa_payment_id)
                ttl = await redis_client.ttl(key)
                await redis_client.setex(
                    key,
                    ttl if ttl > 0 else PAYMENT_CHECK_MAX_TIME,
                    json.dumps(data)
                )
                
    except Exception as e:
        logger.error(f"Ошибка при проверке платежа {yookassa_payment_id}: {e}")
        
        # Если произошла критическая ошибка, отправляем сообщение пользователю
        try:
            data = await get_payment_check_data(yookassa_payment_id)
            if data:
                await handle_canceled_payment(
                    payment_id=data["payment_id"],
                    user_id=data["user_id"],
                    message_id=data.get("message_id"),
                    yookassa_payment_id=yookassa_payment_id,
                    status="error",
                    reason=f"Произошла техническая ошибка при проверке статуса платежа.\n\nПожалуйста, свяжитесь с поддержкой, указав ID платежа: <code>{yookassa_payment_id[:20]}...</code>"
                )
                
                # Удаляем данные и задачу
                await delete_payment_check_data(yookassa_payment_id)
                remove_job(f"check_payment_{yookassa_payment_id}")
        except Exception as send_error:
            logger.error(f"Ошибка при отправке сообщения об ошибке: {send_error}")


def start_payment_check(
    yookassa_payment_id: str,
    payment_id: int,
    user_id: int,
    server_id: int,
    message_id: Optional[int] = None,
    subscription_id: Optional[int] = None,
    is_renewal: bool = False
):
    """Запустить проверку платежа через APScheduler"""
    # Сохраняем данные в Redis
    import asyncio
    asyncio.create_task(store_payment_check_data(
        yookassa_payment_id,
        payment_id,
        user_id,
        server_id,
        message_id,
        subscription_id,
        is_renewal
    ))
    
    # Добавляем задачу в планировщик (проверка каждые 10 секунд)
    add_job(
        check_payment_job,
        trigger="interval",
        seconds=10,
        id=f"check_payment_{yookassa_payment_id}",
        args=[yookassa_payment_id],
        max_instances=1
    )
    logger.info(f"Запущена проверка платежа {yookassa_payment_id}")

