"""
Сервис для работы с YooKassa API
"""
import uuid
import json
from typing import Optional, Dict
from yookassa import Configuration, Payment, Refund
from core.config import config
import logging

logger = logging.getLogger(__name__)


class YooKassaService:
    """Сервис для создания и обработки платежей через YooKassa"""
    
    def __init__(self):
        """Инициализация YooKassa с настройками из конфига"""
        # Читаем настройки из config
        shop_id_str = str(config.YOOKASSA_SHOP_ID).strip() if config.YOOKASSA_SHOP_ID else ""
        secret_key = str(config.YOOKASSA_SECRET_KEY).strip() if config.YOOKASSA_SECRET_KEY else ""
        
        if config.TEST_MODE:
            logger.debug(f"YooKassa init: shop_id={shop_id_str[:10]}..., secret_key length={len(secret_key)}")
        
        # Проверяем только, что значения не пустые
        if not shop_id_str or shop_id_str == "your_shop_id":
            raise ValueError(
                f"YOOKASSA_SHOP_ID не установлен или содержит placeholder.\n"
                f"Текущее значение: '{shop_id_str}'\n"
                f"Установите реальное значение в .env файле: YOOKASSA_SHOP_ID=1216074"
            )
        
        if not secret_key or secret_key == "your_secret_key":
            raise ValueError(
                f"YOOKASSA_SECRET_KEY не установлен или содержит placeholder.\n"
                f"Текущее значение начинается с: '{secret_key[:20] if secret_key else 'пусто'}...'\n"
                f"Установите реальное значение в .env файле: YOOKASSA_SECRET_KEY=live_..."
            )
        
        # Преобразуем shop_id в число
        try:
            shop_id = int(shop_id_str)
        except ValueError:
            raise ValueError(
                f"YOOKASSA_SHOP_ID должен быть числом, получено: '{shop_id_str}'\n"
                f"Установите правильное значение в .env файле: YOOKASSA_SHOP_ID=1216074"
            )
        
        # Проверяем формат secret_key - может быть с префиксом TEST: или test_
        # YooKassa SDK ожидает ключ без префикса или с правильным форматом
        if secret_key.startswith("TEST:"):
            # Убираем префикс TEST: если есть
            secret_key = secret_key[5:].strip()
            if config.TEST_MODE:
                logger.warning("TEST: prefix removed from secret_key")
        elif secret_key.startswith("test_"):
            # Оставляем как есть - это правильный формат для тестовых ключей
            pass
        
        # Настраиваем Configuration для YooKassa SDK
        Configuration.account_id = shop_id  # account_id должен быть числом
        Configuration.secret_key = secret_key
        
        # Логируем только в test_mode
        if config.TEST_MODE:
            logger.info(f"YooKassa init: shop_id={shop_id}, test_mode=True")
        
        # Сохраняем очищенные значения для использования
        self.shop_id = shop_id  # Сохраняем как число
        self.secret_key = secret_key
    
    def _ensure_config(self):
        """Убедиться, что Configuration правильно настроен"""
        if not Configuration.account_id or not Configuration.secret_key:
            # Используем сохраненные очищенные значения
            # Явно преобразуем shop_id в int, чтобы гарантировать правильный тип
            Configuration.account_id = int(self.shop_id) if isinstance(self.shop_id, str) else self.shop_id
            Configuration.secret_key = self.secret_key
            logger.debug("Configuration переустановлен")
    
    async def create_payment(
        self,
        amount: float,
        description: str,
        user_id: str,
        return_url: Optional[str] = None,
        customer_email: Optional[str] = None,
        customer_phone: Optional[str] = None,
        receipt_item_description: Optional[str] = None
    ) -> Dict:
        """
        Создать платеж в YooKassa
        
        Args:
            amount: Сумма платежа в рублях
            description: Описание платежа
            user_id: ID пользователя (для идентификации)
            return_url: URL для возврата после оплаты (опционально)
            customer_email: Email покупателя для чека (опционально)
            customer_phone: Телефон покупателя для чека в формате ITU-T E.164 (опционально)
            receipt_item_description: Описание товара для чека (опционально, используется description если не указано)
        
        Returns:
            Dict с данными платежа (id, confirmation_url и т.д.)
        
        Note:
            Если указаны customer_email или customer_phone, автоматически создается чек
            для самозанятых согласно документации YooKassa.
        """
        # Убеждаемся, что Configuration правильно настроен
        self._ensure_config()
        
        # Проверяем обязательные параметры
        if not config.YOOKASSA_SHOP_ID or not config.YOOKASSA_SECRET_KEY:
            raise ValueError("YOOKASSA_SHOP_ID и YOOKASSA_SECRET_KEY должны быть установлены")
        
        # Генерируем уникальный idempotence_key для предотвращения дублирования платежей
        # Согласно документации YooKassa, нужно передавать UUID объект, а не строку
        idempotence_key = uuid.uuid4()
        
        # Формируем return_url - если не указан, получаем username бота через Bot API
        if not return_url:
            try:
                from core.loader import bot
                bot_info = await bot.get_me()
                bot_username = bot_info.username
                if bot_username:
                    return_url = f"https://t.me/{bot_username}"
                else:
                    return_url = "https://t.me"
            except Exception as e:
                logger.warning(f"Не удалось получить username бота: {e}, используем дефолтный URL")
                return_url = "https://t.me"
        
        # Формируем данные для создания платежа согласно документации YooKassa
        payment_data = {
            "amount": {
                "value": f"{amount:.2f}",
                "currency": "RUB"
            },
            "confirmation": {
                "type": "redirect",
                "return_url": return_url
            },
            "capture": True,
            "description": description[:128] if len(description) > 128 else description,  # Максимум 128 символов
            "metadata": {
                "user_id": str(user_id)[:200]  # Ограничение длины
            }
        }
        
        # Добавляем информацию о чеке (обязательно для всех платежей в России согласно 54-ФЗ)
        # Сохраняем оригинальные данные без receipt для fallback
        payment_data_with_receipt = payment_data.copy()
        receipt_added = False
        
        try:
            # Всегда создаем receipt с товарами (обязательно для YooKassa)
            receipt = {
                "items": [
                    {
                        "description": (receipt_item_description or description)[:128],  # Максимум 128 символов
                        "quantity": "1.00",
                        "amount": {
                            "value": f"{amount:.2f}",
                            "currency": "RUB"
                        },
                        "vat_code": 1  # НДС не облагается (для самозанятых)
                    }
                ],
                "tax_system_code": 1  # Общая система налогообложения
            }
            
            # Добавляем данные покупателя (обязательно для receipt в YooKassa)
            # Если email не валидный, используем его как Telegram username и форматируем как email
            customer_data_added = False
            receipt["customer"] = {}
            
            # Обработка email покупателя
            if customer_email:
                email = customer_email.strip()
                # Простая валидация email: должен содержать @ и точку после @
                if "@" in email and "." in email.split("@")[1] and len(email.split("@")[0]) > 0:
                    # Валидный email
                    receipt["customer"]["email"] = email
                    customer_data_added = True
                    if config.TEST_MODE:
                        logger.debug(f"Receipt email: {email}")
                else:
                    # Невалидный email - используем как Telegram username и форматируем как валидный email
                    username = email.replace("@", "").replace(" ", "_").replace(".", "_")[:64]
                    formatted_email = f"{username}@telegram.local"
                    receipt["customer"]["email"] = formatted_email
                    customer_data_added = True
                    if config.TEST_MODE:
                        logger.debug(f"Receipt email formatted: {formatted_email}")
            
            # Обработка телефона покупателя (если указан)
            if customer_phone:
                # Форматируем телефон в формат ITU-T E.164 если нужно
                phone = customer_phone.strip()
                if not phone.startswith("+"):
                    # Если телефон начинается с 8, заменяем на +7
                    if phone.startswith("8"):
                        phone = "+7" + phone[1:]
                    elif phone.startswith("7"):
                        phone = "+" + phone
                    else:
                        phone = "+7" + phone
                
                # Простая валидация телефона: должен начинаться с + и содержать только цифры после +
                if phone.startswith("+") and phone[1:].replace(" ", "").isdigit() and len(phone.replace(" ", "")) >= 10:
                    receipt["customer"]["phone"] = phone.replace(" ", "")
                    customer_data_added = True
                    if config.TEST_MODE:
                        logger.debug(f"Receipt phone: {phone.replace(' ', '')}")
                else:
                    if config.TEST_MODE:
                        logger.warning(f"Invalid phone format: {customer_phone}")
            
            # Если нет ни email, ни phone, используем дефолтный email на основе user_id
            if not customer_data_added:
                default_email = f"user_{user_id}@telegram.local"
                receipt["customer"]["email"] = default_email
                customer_data_added = True
                if config.TEST_MODE:
                    logger.debug(f"Receipt default email: {default_email}")
            
            # Всегда добавляем receipt (обязательно для YooKassa)
            payment_data_with_receipt["receipt"] = receipt
            receipt_added = True
        except Exception as receipt_error:
            logger.error(f"Receipt creation error: {receipt_error}")
            # Receipt обязателен, поэтому пробуем создать минимальный вариант
            try:
                receipt = {
                    "items": [
                        {
                            "description": (receipt_item_description or description)[:128],
                            "quantity": "1.00",
                            "amount": {
                                "value": f"{amount:.2f}",
                                "currency": "RUB"
                            },
                            "vat_code": 1
                        }
                    ],
                    "tax_system_code": 1
                }
                payment_data_with_receipt["receipt"] = receipt
                receipt_added = True
                if config.TEST_MODE:
                    logger.warning(f"Minimal receipt created after error")
            except Exception as fallback_error:
                logger.error(f"Failed to create minimal receipt: {fallback_error}")
                receipt_added = False
        
        try:
            # Убеждаемся, что Configuration установлен перед каждым запросом
            # Явно преобразуем shop_id в int, чтобы гарантировать правильный тип
            Configuration.account_id = int(self.shop_id) if isinstance(self.shop_id, str) else self.shop_id
            Configuration.secret_key = self.secret_key
            
            # Компактное логирование только в test_mode
            if config.TEST_MODE:
                logger.info(f"YooKassa payment: amount={amount} RUB, user_id={user_id}")
            
            # Создаем платеж через YooKassa SDK
            # Receipt обязателен для всех платежей в России (54-ФЗ)
            if not receipt_added:
                raise ValueError("Не удалось создать receipt - это обязательное поле для платежей в России")
            
            # Всегда используем payment_data_with_receipt
            payment = Payment.create(payment_data_with_receipt, idempotence_key)
            
            if config.TEST_MODE:
                logger.info(f"YooKassa payment created: id={payment.id}, status={payment.status}")
            
            # Формируем ответ
            result = {
                "id": payment.id,
                "status": payment.status,
                "confirmation_url": payment.confirmation.confirmation_url if payment.confirmation else None,
                "amount": float(payment.amount.value) if payment.amount else amount,
                "currency": payment.amount.currency if payment.amount else "RUB",
                "created_at": payment.created_at,
                "metadata": payment.metadata if payment.metadata else {}
            }
            
            return result
            
        except Exception as e:
            error_msg = str(e)
            
            # Пытаемся получить детальную информацию об ошибке из ответа API
            error_details_text = error_msg
            if hasattr(e, 'response') and e.response is not None:
                try:
                    if hasattr(e.response, 'text'):
                        error_details_text = e.response.text
                    elif hasattr(e.response, 'json'):
                        error_json = e.response.json()
                        error_details_text = str(error_json)
                except:
                    pass
            
            # Компактное логирование ошибки
            logger.error(f"YooKassa payment error: {type(e).__name__}: {error_msg[:200]}")
            if config.TEST_MODE and error_details_text != error_msg:
                logger.debug(f"YooKassa error details: {error_details_text[:500]}")
            
            # Формируем понятное сообщение об ошибке
            if "401" in error_msg or "unauthorized" in error_msg.lower() or "authentication" in error_msg.lower():
                error_details = "Ошибка авторизации в платежной системе. Проверьте YOOKASSA_SHOP_ID и YOOKASSA_SECRET_KEY"
                if config.TEST_MODE:
                    logger.error(f"YooKassa auth error: check credentials")
                raise Exception(error_details)
            elif "400" in error_msg or "invalid" in error_msg.lower() or "validation" in error_msg.lower():
                detailed_error = f"Некорректные данные платежа: {error_msg[:200]}"
                if config.TEST_MODE and error_details_text != error_msg:
                    detailed_error += f"\nДетали: {error_details_text[:300]}"
                raise Exception(detailed_error)
            elif "403" in error_msg or "forbidden" in error_msg.lower():
                raise Exception("Доступ запрещен (403). Проверьте права доступа API ключей.")
            elif "insufficient" in error_msg.lower() or "balance" in error_msg.lower():
                raise Exception("Недостаточно средств на счете магазина.")
            else:
                raise Exception(f"Не удалось создать платеж: {error_msg}")
    
    def get_payment_status(self, payment_id: str) -> Optional[Dict]:
        """
        Получить статус платежа
        
        Args:
            payment_id: ID платежа в YooKassa
        
        Returns:
            Dict с данными платежа или None если не найден
        """
        # Убеждаемся, что Configuration правильно настроен
        self._ensure_config()
        
        try:
            payment = Payment.find_one(payment_id)
            
            status_data = {
                "id": payment.id,
                "status": payment.status,
                "paid": payment.paid if hasattr(payment, 'paid') else False,
                "amount": float(payment.amount.value) if payment.amount and payment.amount.value else None,
                "currency": payment.amount.currency if payment.amount else None,
                "created_at": payment.created_at,
                "captured_at": payment.captured_at if hasattr(payment, 'captured_at') else None,
                "metadata": payment.metadata if hasattr(payment, 'metadata') else {}
            }
            if config.TEST_MODE:
                logger.debug(f"Payment status {payment_id}: {payment.status}, paid={status_data['paid']}")
            return status_data
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Ошибка при получении статуса платежа {payment_id}: {error_msg}")
            
            # Если платеж не найден, возвращаем None
            if "404" in error_msg or "not found" in error_msg.lower():
                if config.TEST_MODE:
                    logger.warning(f"Payment {payment_id} not found in YooKassa")
                return None
            
            # Для других ошибок логируем и возвращаем None
            return None
    
    def cancel_payment(self, payment_id: str) -> bool:
        """
        Отменить платеж
        
        Args:
            payment_id: ID платежа в YooKassa
        
        Returns:
            True если успешно отменен, False в противном случае
        """
        # Убеждаемся, что Configuration правильно настроен
        self._ensure_config()
        
        try:
            payment = Payment.cancel(payment_id)
            if config.TEST_MODE:
                logger.info(f"Payment {payment_id} canceled: status={payment.status}")
            return payment.status == "canceled"
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Ошибка при отмене платежа {payment_id}: {error_msg}")
            return False
    
    def refund_payment(self, payment_id: str, amount: Optional[float] = None, description: Optional[str] = None) -> Optional[Dict]:
        """
        Вернуть средства по платежу (полный или частичный возврат)
        
        Args:
            payment_id: ID платежа в YooKassa
            amount: Сумма возврата (если None, возвращается полная сумма)
            description: Описание возврата
        
        Returns:
            Dict с данными возврата или None в случае ошибки
        """
        # Убеждаемся, что Configuration правильно настроен
        self._ensure_config()
        
        try:
            # Получаем информацию о платеже для определения суммы возврата
            payment = Payment.find_one(payment_id)
            if not payment:
                logger.error(f"Платеж {payment_id} не найден для возврата")
                return None
            
            # Если сумма не указана, возвращаем полную сумму платежа
            if amount is None:
                amount = float(payment.amount.value) if payment.amount and payment.amount.value else None
                if amount is None:
                    logger.error(f"Не удалось определить сумму платежа {payment_id} для возврата")
                    return None
            
            # Формируем данные для возврата
            refund_data = {
                "amount": {
                    "value": f"{amount:.2f}",
                    "currency": payment.amount.currency if payment.amount else "RUB"
                },
                "payment_id": payment_id
            }
            
            if description:
                refund_data["description"] = description[:128] if len(description) > 128 else description
            
            # Генерируем уникальный idempotence_key для предотвращения дублирования возвратов
            idempotence_key = uuid.uuid4()
            
            # Создаем возврат
            refund = Refund.create(refund_data, idempotence_key)
            
            refund_info = {
                "id": refund.id,
                "status": refund.status,
                "amount": float(refund.amount.value) if refund.amount and refund.amount.value else None,
                "currency": refund.amount.currency if refund.amount else None,
                "created_at": refund.created_at,
                "payment_id": payment_id
            }
            
            if config.TEST_MODE:
                logger.info(f"Refund {payment_id}: refund_id={refund.id}, amount={amount:.2f}, status={refund.status}")
            return refund_info
            
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Ошибка при возврате средств по платежу {payment_id}: {error_msg}")
            return None


# Глобальный экземпляр сервиса (создается лениво при первом использовании)
_yookassa_service_instance = None

def get_yookassa_service() -> YooKassaService:
    """Получить экземпляр YooKassaService (ленивая инициализация)"""
    global _yookassa_service_instance
    if _yookassa_service_instance is None:
        _yookassa_service_instance = YooKassaService()
    return _yookassa_service_instance

# Создаем объект-прокси для обратной совместимости с существующим кодом
class YooKassaServiceProxy:
    """Прокси для обратной совместимости с yookassa_service"""
    def __getattr__(self, name):
        service = get_yookassa_service()
        return getattr(service, name)
    
    def __call__(self, *args, **kwargs):
        # Если кто-то пытается вызвать yookassa_service как функцию
        return get_yookassa_service()

yookassa_service = YooKassaServiceProxy()

