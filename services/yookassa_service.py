"""
Сервис для работы с YooKassa API
"""
import uuid
from typing import Optional, Dict
from yookassa import Configuration, Payment
from core.config import config
import logging

logger = logging.getLogger(__name__)


class YooKassaService:
    """Сервис для создания и обработки платежей через YooKassa"""
    
    def __init__(self):
        """Инициализация YooKassa с настройками из конфига"""
        # ДИАГНОСТИКА: Проверяем, что реально приходит из config
        import os
        from dotenv import load_dotenv
        
        # Перезагружаем .env файл напрямую
        load_dotenv(override=True)
        
        # Читаем напрямую из окружения
        env_shop_id = os.getenv("YOOKASSA_SHOP_ID", "")
        env_secret_key = os.getenv("YOOKASSA_SECRET_KEY", "")
        
        print("=" * 80)
        print("🔍 ДИАГНОСТИКА ЧТЕНИЯ .env ФАЙЛА")
        print("=" * 80)
        print(f"📁 Чтение напрямую из os.getenv:")
        print(f"   YOOKASSA_SHOP_ID = '{env_shop_id}' (длина: {len(env_shop_id)})")
        print(f"   YOOKASSA_SECRET_KEY = '{env_secret_key}' (длина: {len(env_secret_key)})")
        print(f"")
        print(f"📁 Чтение из config:")
        print(f"   config.YOOKASSA_SHOP_ID = '{config.YOOKASSA_SHOP_ID}' (тип: {type(config.YOOKASSA_SHOP_ID).__name__})")
        print(f"   config.YOOKASSA_SECRET_KEY = '{config.YOOKASSA_SECRET_KEY}' (тип: {type(config.YOOKASSA_SECRET_KEY).__name__})")
        print("=" * 80)
        
        # Используем значения напрямую из окружения, если они есть
        if env_shop_id and env_shop_id != "your_shop_id":
            shop_id_str = str(env_shop_id).strip()
            print(f"✅ Используем shop_id из os.getenv: '{shop_id_str}'")
        else:
            shop_id_str = str(config.YOOKASSA_SHOP_ID).strip() if config.YOOKASSA_SHOP_ID else ""
            print(f"⚠️ Используем shop_id из config: '{shop_id_str}'")
        
        if env_secret_key and env_secret_key != "your_secret_key":
            secret_key = str(env_secret_key).strip()
            print(f"✅ Используем secret_key из os.getenv: '{secret_key[:20]}...' (длина: {len(secret_key)})")
        else:
            secret_key = str(config.YOOKASSA_SECRET_KEY).strip() if config.YOOKASSA_SECRET_KEY else ""
            print(f"⚠️ Используем secret_key из config: '{secret_key[:20] if secret_key else ''}...' (длина: {len(secret_key)})")
        
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
            logger.warning("Обнаружен префикс TEST: в secret_key, он был удален")
        elif secret_key.startswith("test_"):
            # Оставляем как есть - это правильный формат для тестовых ключей
            pass
        
        # Настраиваем Configuration для YooKassa SDK
        Configuration.account_id = shop_id  # account_id должен быть числом
        Configuration.secret_key = secret_key
        
        # Логируем информацию (без полного ключа для безопасности)
        logger.info(f"YooKassa инициализирован:")
        logger.info(f"  shop_id={shop_id} (тип: {type(shop_id).__name__})")
        logger.info(f"  secret_key начинается с: {secret_key[:10]}... (длина: {len(secret_key)})")
        logger.info(f"  test_mode={config.TEST_MODE}")
        
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
        return_url: Optional[str] = None
    ) -> Dict:
        """
        Создать платеж в YooKassa
        
        Args:
            amount: Сумма платежа в рублях
            description: Описание платежа
            user_id: ID пользователя (для идентификации)
            return_url: URL для возврата после оплаты (опционально)
        
        Returns:
            Dict с данными платежа (id, confirmation_url и т.д.)
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
        
        try:
            # Убеждаемся, что Configuration установлен перед каждым запросом
            # Явно преобразуем shop_id в int, чтобы гарантировать правильный тип
            Configuration.account_id = int(self.shop_id) if isinstance(self.shop_id, str) else self.shop_id
            Configuration.secret_key = self.secret_key
            
            # ДЕТАЛЬНОЕ ЛОГИРОВАНИЕ ДЛЯ ДЕБАГА
            print("=" * 80)
            print("🔍 ДЕТАЛЬНАЯ ИНФОРМАЦИЯ О ЗАПРОСЕ К YOOKASSA API")
            print("=" * 80)
            print(f"📋 Payment data:")
            print(f"   {payment_data}")
            print(f"")
            print(f"🔑 Configuration перед запросом:")
            print(f"   account_id = {Configuration.account_id} (тип: {type(Configuration.account_id).__name__})")
            print(f"   secret_key = '{Configuration.secret_key}' (тип: {type(Configuration.secret_key).__name__}, длина: {len(Configuration.secret_key)})")
            print(f"   secret_key первые 20 символов: '{Configuration.secret_key[:20]}'")
            print(f"   secret_key последние 10 символов: '{Configuration.secret_key[-10:]}'")
            print(f"")
            print(f"🔑 Исходные значения из config:")
            print(f"   self.shop_id = {self.shop_id} (тип: {type(self.shop_id).__name__})")
            print(f"   self.secret_key = '{self.secret_key}' (тип: {type(self.secret_key).__name__}, длина: {len(self.secret_key)})")
            print(f"")
            print(f"🔑 Значения из config (сырые):")
            print(f"   config.YOOKASSA_SHOP_ID = '{config.YOOKASSA_SHOP_ID}' (тип: {type(config.YOOKASSA_SHOP_ID).__name__})")
            print(f"   config.YOOKASSA_SECRET_KEY = '{config.YOOKASSA_SECRET_KEY}' (тип: {type(config.YOOKASSA_SECRET_KEY).__name__}, длина: {len(str(config.YOOKASSA_SECRET_KEY))})")
            print(f"")
            print(f"🔑 Idempotence key:")
            print(f"   {idempotence_key} (тип: {type(idempotence_key).__name__})")
            print(f"")
            print(f"📤 Отправка запроса к YooKassa API...")
            print("=" * 80)
            
            logger.info(f"Создание платежа через YooKassa API:")
            logger.info(f"  amount={amount} RUB")
            logger.info(f"  description={description[:50]}...")
            logger.info(f"  Configuration.account_id={Configuration.account_id}")
            logger.info(f"  Configuration.secret_key (полный для дебага): {Configuration.secret_key}")
            logger.info(f"  idempotence_key={idempotence_key} (тип: {type(idempotence_key).__name__})")
            logger.debug(f"  payment_data={payment_data}")
            
            # Создаем платеж через YooKassa SDK
            # Согласно документации: Payment.create(payment_data, uuid.uuid4())
            payment = Payment.create(payment_data, idempotence_key)
            
            logger.info(f"Платеж создан успешно: id={payment.id}, status={payment.status}")
            
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
            
            # ДЕТАЛЬНОЕ ЛОГИРОВАНИЕ ОШИБКИ
            print("=" * 80)
            print("❌ ОШИБКА ПРИ СОЗДАНИИ ПЛАТЕЖА")
            print("=" * 80)
            print(f"Ошибка: {error_msg}")
            if error_details_text != error_msg:
                print(f"Детали ошибки: {error_details_text}")
            print(f"")
            print(f"📋 Payment data:")
            print(f"   {payment_data}")
            print(f"")
            print(f"🔑 Configuration в момент ошибки:")
            print(f"   account_id = {Configuration.account_id} (тип: {type(Configuration.account_id).__name__})")
            print(f"   secret_key = '{Configuration.secret_key}' ({'SET, длина: ' + str(len(Configuration.secret_key)) if Configuration.secret_key else 'NOT SET'})")
            if Configuration.secret_key:
                print(f"   secret_key (полный): {Configuration.secret_key}")
            print(f"")
            print(f"🔑 Сохраненные значения:")
            print(f"   self.shop_id = {self.shop_id} (тип: {type(self.shop_id).__name__})")
            print(f"   self.secret_key = '{self.secret_key}'")
            print(f"")
            print(f"🔑 Исходные значения из config:")
            print(f"   config.YOOKASSA_SHOP_ID = '{config.YOOKASSA_SHOP_ID}'")
            print(f"   config.YOOKASSA_SECRET_KEY = '{config.YOOKASSA_SECRET_KEY}'")
            print("=" * 80)
            
            logger.error(f"Ошибка при создании платежа в YooKassa: {error_msg}")
            if error_details_text != error_msg:
                logger.error(f"Детали ошибки: {error_details_text}")
            logger.error(f"Payment data: {payment_data}")
            logger.error(f"Configuration check:")
            logger.error(f"  account_id={Configuration.account_id} (тип: {type(Configuration.account_id).__name__})")
            logger.error(f"  secret_key={'set (полный: ' + str(Configuration.secret_key) + ')' if Configuration.secret_key else 'NOT SET'}")
            logger.error(f"  Используемый shop_id из config: {self.shop_id} (тип: {type(self.shop_id).__name__})")
            logger.error(f"  Используемый secret_key (полный): {self.secret_key}")
            
            # Формируем понятное сообщение об ошибке
            if "401" in error_msg or "unauthorized" in error_msg.lower() or "authentication" in error_msg.lower():
                error_details = (
                    "Ошибка авторизации в платежной системе (401).\n\n"
                    "Возможные причины:\n"
                    "1. Неправильный YOOKASSA_SHOP_ID или YOOKASSA_SECRET_KEY\n"
                    "2. Ключи не соответствуют друг другу (тестовый shop_id с реальным secret_key или наоборот)\n"
                    "3. Ключи содержат лишние пробелы или символы\n"
                    "4. Используются неактуальные ключи\n\n"
                    "Что проверить:\n"
                    "- Убедитесь, что ключи скопированы полностью из личного кабинета YooKassa\n"
                    "- Проверьте, что используете правильные ключи (тестовые или реальные)\n"
                    "- Убедитесь, что shop_id и secret_key соответствуют друг другу\n"
                    "- Проверьте, нет ли лишних пробелов в начале или конце ключей в .env файле"
                )
                logger.error(error_details)
                raise Exception(error_details)
            elif "400" in error_msg or "invalid" in error_msg.lower() or "validation" in error_msg.lower():
                # Пытаемся извлечь детали из ответа API
                detailed_error = error_msg
                if error_details_text != error_msg:
                    detailed_error = f"{error_msg}\n\nДетали от YooKassa:\n{error_details_text}"
                
                # Проверяем, не связана ли ошибка с account_id
                if "account_id" in error_details_text.lower() or "shop_id" in error_details_text.lower():
                    detailed_error += f"\n\n⚠️ Возможная проблема: account_id должен быть числом, а не строкой.\n"
                    detailed_error += f"Текущий account_id: {Configuration.account_id} (тип: {type(Configuration.account_id).__name__})"
                
                raise Exception(f"Некорректные данные платежа (400). Проверьте формат данных:\n{detailed_error}")
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
            logger.debug(f"Статус платежа {payment_id}: {payment.status}, paid={status_data['paid']}")
            return status_data
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Ошибка при получении статуса платежа {payment_id}: {error_msg}")
            
            # Если платеж не найден, возвращаем None
            if "404" in error_msg or "not found" in error_msg.lower():
                logger.warning(f"Платеж {payment_id} не найден в YooKassa")
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
            logger.info(f"Платеж {payment_id} отменен: status={payment.status}")
            return payment.status == "canceled"
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Ошибка при отмене платежа {payment_id}: {error_msg}")
            return False


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

