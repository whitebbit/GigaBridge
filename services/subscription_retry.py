"""
Сервис для обработки неудачных попыток создания подписок
Включает механизм повторных попыток с экспоненциальной задержкой
"""
import logging
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
from database.base import async_session
from database.models import FailedSubscriptionAttempt, Payment, User, Server
from sqlalchemy import select
from handlers.buy.payment import handle_successful_payment
from services.yookassa_service import yookassa_service
from core.loader import bot
from utils.keyboards.main_kb import main_menu
import traceback

logger = logging.getLogger(__name__)

# Интервалы между попытками (экспоненциальная задержка в минутах)
RETRY_INTERVALS = [5, 15, 30, 60, 120]  # 5 мин, 15 мин, 30 мин, 1 час, 2 часа


async def create_failed_attempt(
    payment_id: int,
    user_id: int,
    server_id: int,
    error_message: str,
    error_type: str = "unknown",
    subscription_id: Optional[int] = None,
    is_renewal: bool = False
) -> Optional[FailedSubscriptionAttempt]:
    """
    Создает запись о неудачной попытке создания подписки
    Проверяет, нет ли уже активной попытки для этого платежа
    
    Args:
        payment_id: ID платежа
        user_id: ID пользователя
        server_id: ID сервера
        error_message: Сообщение об ошибке
        error_type: Тип ошибки (api_error, database_error, etc.)
        subscription_id: ID подписки (для продления)
        is_renewal: Это продление?
        
    Returns:
        Созданная запись FailedSubscriptionAttempt или существующая, если она уже есть
    """
    async with async_session() as session:
        # Проверяем, нет ли уже активной попытки для этого платежа
        result = await session.execute(
            select(FailedSubscriptionAttempt)
            .where(
                FailedSubscriptionAttempt.payment_id == payment_id,
                FailedSubscriptionAttempt.status.in_(["pending", "processing"])
            )
            .order_by(FailedSubscriptionAttempt.created_at.desc())
            .limit(1)
        )
        existing_attempt = result.scalar_one_or_none()
        
        if existing_attempt:
            logger.info(
                f"⚠️ Для платежа {payment_id} уже существует активная попытка "
                f"(attempt_id={existing_attempt.id}), не создаем дубликат"
            )
            # Обновляем сообщение об ошибке на более свежее
            existing_attempt.error_message = error_message
            existing_attempt.error_type = error_type
            await session.commit()
            return existing_attempt
        
        # Первая попытка повтора через 5 минут
        next_attempt = datetime.utcnow() + timedelta(minutes=RETRY_INTERVALS[0])
        
        attempt = FailedSubscriptionAttempt(
            payment_id=payment_id,
            user_id=user_id,
            server_id=server_id,
            subscription_id=subscription_id,
            is_renewal=is_renewal,
            error_message=error_message,
            error_type=error_type,
            attempt_count=0,
            max_attempts=len(RETRY_INTERVALS),
            next_attempt_at=next_attempt,
            status="pending"
        )
        
        session.add(attempt)
        await session.commit()
        await session.refresh(attempt)
        
        logger.info(
            f"📝 Создана запись о неудачной попытке создания подписки: "
            f"payment_id={payment_id}, user_id={user_id}, next_attempt={next_attempt}"
        )
        
        return attempt


async def get_pending_attempts(limit: int = 10) -> list[FailedSubscriptionAttempt]:
    """
    Получает список попыток, готовых к повторной обработке
    
    Args:
        limit: Максимальное количество попыток для обработки за раз
        
    Returns:
        Список FailedSubscriptionAttempt
    """
    async with async_session() as session:
        now = datetime.utcnow()
        result = await session.execute(
            select(FailedSubscriptionAttempt)
            .where(
                FailedSubscriptionAttempt.status == "pending",
                FailedSubscriptionAttempt.next_attempt_at <= now,
                FailedSubscriptionAttempt.attempt_count < FailedSubscriptionAttempt.max_attempts
            )
            .order_by(FailedSubscriptionAttempt.created_at)
            .limit(limit)
        )
        attempts = result.scalars().all()
        return list(attempts)


async def update_attempt_status(
    attempt_id: int,
    status: str,
    error_message: Optional[str] = None,
    refund_id: Optional[str] = None
) -> None:
    """
    Обновляет статус попытки
    
    Args:
        attempt_id: ID попытки
        status: Новый статус (pending, processing, completed, failed, refunded)
        error_message: Обновленное сообщение об ошибке (опционально)
        refund_id: ID возврата средств (опционально)
    """
    async with async_session() as session:
        result = await session.execute(
            select(FailedSubscriptionAttempt).where(FailedSubscriptionAttempt.id == attempt_id)
        )
        attempt = result.scalar_one_or_none()
        
        if not attempt:
            logger.warning(f"⚠️ Попытка {attempt_id} не найдена")
            return
        
        attempt.status = status
        attempt.updated_at = datetime.utcnow()
        
        if error_message:
            attempt.error_message = error_message
        
        if refund_id:
            attempt.refund_id = refund_id
            attempt.refund_attempted = True
        
        if status in ["completed", "failed", "refunded"]:
            attempt.completed_at = datetime.utcnow()
        
        await session.commit()


async def increment_attempt_count(attempt_id: int) -> None:
    """
    Увеличивает счетчик попыток и устанавливает время следующей попытки
    
    Args:
        attempt_id: ID попытки
    """
    async with async_session() as session:
        result = await session.execute(
            select(FailedSubscriptionAttempt).where(FailedSubscriptionAttempt.id == attempt_id)
        )
        attempt = result.scalar_one_or_none()
        
        if not attempt:
            return
        
        attempt.attempt_count += 1
        
        # Определяем интервал для следующей попытки (экспоненциальная задержка)
        if attempt.attempt_count < len(RETRY_INTERVALS):
            minutes = RETRY_INTERVALS[attempt.attempt_count]
        else:
            # Если превысили максимальное количество интервалов, используем последний
            minutes = RETRY_INTERVALS[-1]
        
        attempt.next_attempt_at = datetime.utcnow() + timedelta(minutes=minutes)
        attempt.updated_at = datetime.utcnow()
        
        await session.commit()
        
        logger.info(
            f"🔄 Попытка {attempt_id}: счетчик увеличен до {attempt.attempt_count}, "
            f"следующая попытка через {minutes} минут"
        )


async def retry_subscription_creation(attempt: FailedSubscriptionAttempt) -> bool:
    """
    Повторно пытается создать/продлить подписку
    
    Args:
        attempt: Запись о неудачной попытке
        
    Returns:
        True если успешно, False если неудачно
    """
    try:
        # Получаем данные платежа
        async with async_session() as session:
            result = await session.execute(
                select(Payment).where(Payment.id == attempt.payment_id)
            )
            payment = result.scalar_one_or_none()
            
            if not payment:
                logger.error(f"❌ Платеж {attempt.payment_id} не найден")
                await update_attempt_status(
                    attempt.id,
                    "failed",
                    error_message="Платеж не найден"
                )
                return False
            
            # Проверяем, не создана ли уже подписка
            if attempt.subscription_id:
                from utils.db import get_subscription_by_id
                subscription = await get_subscription_by_id(attempt.subscription_id)
                if subscription and subscription.status == "active":
                    logger.info(
                        f"✅ Подписка {attempt.subscription_id} уже активна, "
                        f"помечаем попытку как завершенную"
                    )
                    await update_attempt_status(attempt.id, "completed")
                    return True
            
            # Обновляем статус на "processing"
            await update_attempt_status(attempt.id, "processing")
            
            # Пытаемся создать/продлить подписку
            # Используем ту же функцию, что и при успешной оплате
            # НО: передаем флаг, что это повторная попытка, чтобы избежать бесконечного цикла
            await handle_successful_payment(
                payment_id=attempt.payment_id,
                user_id=attempt.user_id,
                server_id=attempt.server_id,
                message_id=None,  # Не отправляем сообщения при повторных попытках
                subscription_id=attempt.subscription_id if attempt.is_renewal else None,
                is_renewal=attempt.is_renewal
            )
            
            # Если дошли сюда без исключения, считаем успешным
            await update_attempt_status(attempt.id, "completed")
            logger.info(f"✅ Успешно обработана повторная попытка {attempt.id}")
            return True
            
    except Exception as e:
        error_msg = str(e)
        logger.error(
            f"❌ Ошибка при повторной попытке создания подписки (attempt_id={attempt.id}): {error_msg}"
        )
        logger.error(traceback.format_exc())
        
        # Обновляем статус обратно на pending и увеличиваем счетчик
        await update_attempt_status(attempt.id, "pending", error_message=error_msg)
        await increment_attempt_count(attempt.id)
        
        return False


async def process_retry_queue() -> Dict[str, int]:
    """
    Обрабатывает очередь повторных попыток
    
    Returns:
        Словарь со статистикой обработки
    """
    stats = {
        "processed": 0,
        "succeeded": 0,
        "failed": 0,
        "max_attempts_reached": 0
    }
    
    try:
        # Получаем готовые к обработке попытки
        attempts = await get_pending_attempts(limit=10)
        
        logger.info(f"🔄 Обработка очереди повторных попыток: найдено {len(attempts)} попыток")
        
        for attempt in attempts:
            stats["processed"] += 1
            
            # Проверяем, не превышен ли лимит попыток
            if attempt.attempt_count >= attempt.max_attempts:
                logger.warning(
                    f"⚠️ Попытка {attempt.id} достигла максимума попыток "
                    f"({attempt.attempt_count}/{attempt.max_attempts})"
                )
                stats["max_attempts_reached"] += 1
                
                # Помечаем как failed и пытаемся вернуть средства
                await handle_failed_after_max_attempts(attempt)
                continue
            
            # Пытаемся обработать
            success = await retry_subscription_creation(attempt)
            
            if success:
                stats["succeeded"] += 1
            else:
                stats["failed"] += 1
        
        if stats["processed"] > 0:
            logger.info(
                f"📊 Статистика обработки: обработано={stats['processed']}, "
                f"успешно={stats['succeeded']}, неудачно={stats['failed']}, "
                f"достигнут максимум={stats['max_attempts_reached']}"
            )
        
        return stats
        
    except Exception as e:
        logger.error(f"❌ Ошибка при обработке очереди повторных попыток: {e}")
        logger.error(traceback.format_exc())
        return stats


def start_subscription_retry_handler():
    """
    Запускает периодическую задачу для обработки очереди повторных попыток создания подписок
    """
    from services.scheduler import add_job
    
    # Добавляем задачу обработки очереди повторных попыток
    # Проверяем очередь каждые 5 минут
    add_job(
        process_retry_queue,
        trigger="interval",
        minutes=5,
        id="process_subscription_retry_queue"
    )
    logger.info("✅ Задача обработки повторных попыток создания подписок добавлена (каждые 5 минут)")


async def handle_failed_after_max_attempts(attempt: FailedSubscriptionAttempt) -> None:
    """
    Обрабатывает случай, когда достигнут максимум попыток
    Пытается вернуть средства пользователю
    
    Args:
        attempt: Запись о неудачной попытке
    """
    try:
        # Получаем данные платежа
        async with async_session() as session:
            result = await session.execute(
                select(Payment).where(Payment.id == attempt.payment_id)
            )
            payment = result.scalar_one_or_none()
            
            if not payment:
                logger.error(f"❌ Платеж {attempt.payment_id} не найден")
                await update_attempt_status(attempt.id, "failed")
                return
            
            # Получаем пользователя
            result = await session.execute(
                select(User).where(User.id == attempt.user_id)
            )
            user = result.scalar_one_or_none()
            
            if not user:
                logger.error(f"❌ Пользователь {attempt.user_id} не найден")
                await update_attempt_status(attempt.id, "failed")
                return
            
            # Пытаемся вернуть средства
            refund_success = False
            refund_info = None
            
            if payment.yookassa_payment_id and not attempt.refund_attempted:
                try:
                    refund_info = yookassa_service.refund_payment(
                        payment_id=payment.yookassa_payment_id,
                        description=(
                            f"Возврат средств из-за ошибки создания подписки после "
                            f"{attempt.max_attempts} попыток. Payment ID: {attempt.payment_id}, "
                            f"Attempt ID: {attempt.id}"
                        )
                    )
                    
                    if refund_info:
                        refund_success = True
                        refund_id = refund_info.get('id')
                        logger.info(
                            f"✅ Возврат средств выполнен: refund_id={refund_id}, "
                            f"amount={refund_info.get('amount')}"
                        )
                    else:
                        logger.warning(f"⚠️ Не удалось вернуть средства для платежа {payment.yookassa_payment_id}")
                except Exception as refund_error:
                    logger.error(f"❌ Ошибка при возврате средств: {refund_error}")
                    logger.error(traceback.format_exc())
            
            # Обновляем статус попытки
            status = "refunded" if refund_success else "failed"
            await update_attempt_status(
                attempt.id,
                status,
                refund_id=refund_info.get('id') if refund_info else None
            )
            
            # Уведомляем пользователя
            try:
                refund_message = ""
                if refund_success:
                    refund_message = (
                        "\n\n✅ <b>Средства будут возвращены на ваш счет "
                        "в течение нескольких рабочих дней.</b>"
                    )
                else:
                    refund_message = (
                        "\n\n⚠️ <b>Мы обработаем возврат средств вручную. "
                        "Пожалуйста, свяжитесь с поддержкой.</b>"
                    )
                
                await bot.send_message(
                    chat_id=int(user.tg_id),
                    text=(
                        f"❌ <b>К сожалению, не удалось создать подписку</b>\n\n"
                        f"После успешной оплаты произошли технические ошибки при создании подписки, "
                        f"и мы не смогли автоматически восстановить процесс после нескольких попыток.\n\n"
                        f"<b>Детали:</b>\n"
                        f"• Платеж: {payment.amount:.2f} ₽\n"
                        f"• ID платежа: {attempt.payment_id}\n"
                        f"• Количество попыток: {attempt.attempt_count}\n"
                        f"{refund_message}\n\n"
                        f"Пожалуйста, свяжитесь с поддержкой для решения вопроса."
                    ),
                    reply_markup=main_menu(),
                    parse_mode="HTML"
                )
            except Exception as notify_error:
                logger.error(f"❌ Ошибка при отправке уведомления пользователю: {notify_error}")
            
            # Логируем для администратора
            admin_log_message = (
                f"🚨 КРИТИЧЕСКАЯ ОШИБКА: Не удалось создать подписку после {attempt.max_attempts} попыток\n"
                f"• User ID: {attempt.user_id}\n"
                f"• Payment ID: {attempt.payment_id}\n"
                f"• Subscription ID: {attempt.subscription_id}\n"
                f"• YooKassa Payment ID: {payment.yookassa_payment_id}\n"
                f"• Amount: {payment.amount:.2f} ₽\n"
                f"• Server ID: {attempt.server_id}\n"
                f"• Attempt ID: {attempt.id}\n"
                f"• Ошибка: {attempt.error_message}\n"
                f"• Возврат средств: {'Успешно' if refund_success else 'Не удалось'}\n"
                f"• Refund ID: {refund_info.get('id') if refund_info else 'N/A'}"
            )
            logger.error(f"\n{'='*80}\n{admin_log_message}\n{'='*80}\n")
            
    except Exception as e:
        logger.error(f"❌ Ошибка при обработке failed attempt: {e}")
        logger.error(traceback.format_exc())
        await update_attempt_status(attempt.id, "failed")

