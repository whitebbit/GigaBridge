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
            await update_payment_status(data["payment_id"], "failed")
            
            # Отправляем сообщение пользователю
            try:
                error_message = "❌ <b>Платеж не был завершен</b>\n\n"
                if payment_status["status"] == "canceled":
                    error_message += "Платеж был отменен.\n\n"
                    error_message += "Если вы хотите попробовать снова, нажмите кнопку <b>Покупка</b> в главном меню."
                else:
                    error_message += "Произошла ошибка при обработке платежа.\n\n"
                    error_message += "Возможные причины:\n"
                    error_message += "• Недостаточно средств на карте\n"
                    error_message += "• Банк отклонил транзакцию\n"
                    error_message += "• Превышен лимит операции\n\n"
                    error_message += "Попробуйте:\n"
                    error_message += "• Проверить баланс карты\n"
                    error_message += "• Связаться с банком\n"
                    error_message += "• Попробовать другую карту\n\n"
                    error_message += "Если проблема сохраняется, свяжитесь с поддержкой."
                
                # Удаляем сообщение с оплатой, если есть
                if data.get("message_id"):
                    try:
                        await bot.delete_message(chat_id=data["user_id"], message_id=data["message_id"])
                    except:
                        pass
                
                await bot.send_message(
                    chat_id=data["user_id"],
                    text=error_message,
                    reply_markup=main_menu(),
                    parse_mode="HTML"
                )
            except Exception as e:
                logger.error(f"Ошибка при отправке сообщения об ошибке платежа пользователю {data['user_id']}: {e}")
            
            await delete_payment_check_data(yookassa_payment_id)
            remove_job(f"check_payment_{yookassa_payment_id}")
            logger.info(f"Платеж {yookassa_payment_id} отменен или провален")
            
        else:
            # Платеж еще в процессе, увеличиваем счетчик попыток
            data["attempts"] += 1
            if data["attempts"] >= data["max_attempts"]:
                # Превышено максимальное количество попыток
                await update_payment_status(data["payment_id"], "failed")
                
                # Отправляем сообщение пользователю о таймауте
                try:
                    error_message = "⏱️ <b>Время ожидания платежа истекло</b>\n\n"
                    error_message += "Платеж не был завершен в течение 5 минут.\n\n"
                    error_message += "Возможные причины:\n"
                    error_message += "• Вы не завершили оплату на странице ЮKassa\n"
                    error_message += "• Произошла техническая ошибка\n\n"
                    error_message += "Если вы уже оплатили, но не получили ключ:\n"
                    error_message += "• Подождите несколько минут - платеж может обрабатываться\n"
                    error_message += "• Проверьте историю платежей в вашем банке\n"
                    error_message += "• Свяжитесь с поддержкой, указав номер платежа\n\n"
                    error_message += "Если вы хотите попробовать снова, нажмите кнопку <b>Покупка</b> в главном меню."
                    
                    # Удаляем сообщение с оплатой, если есть
                    if data.get("message_id"):
                        try:
                            await bot.delete_message(chat_id=data["user_id"], message_id=data["message_id"])
                        except:
                            pass
                    
                    await bot.send_message(
                        chat_id=data["user_id"],
                        text=error_message,
                        reply_markup=main_menu(),
                        parse_mode="HTML"
                    )
                except Exception as e:
                    logger.error(f"Ошибка при отправке сообщения о таймауте пользователю {data['user_id']}: {e}")
                
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
                error_message = "⚠️ <b>Произошла техническая ошибка</b>\n\n"
                error_message += "При проверке статуса платежа возникла проблема.\n\n"
                error_message += "Пожалуйста, свяжитесь с поддержкой, указав:\n"
                error_message += f"• ID платежа: <code>{yookassa_payment_id[:20]}...</code>\n\n"
                error_message += "Мы обязательно разберемся с проблемой."
                
                # Удаляем сообщение с оплатой, если есть
                if data.get("message_id"):
                    try:
                        await bot.delete_message(chat_id=data["user_id"], message_id=data["message_id"])
                    except:
                        pass
                
                await bot.send_message(
                    chat_id=data["user_id"],
                    text=error_message,
                    reply_markup=main_menu(),
                    parse_mode="HTML"
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

