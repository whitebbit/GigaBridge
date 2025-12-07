import uuid
import time
import requests
from yookassa import Configuration, Payment

# Настройка YooKassa
Configuration.account_id = 1218211
Configuration.secret_key = "test_VWfSLEpLv-YHWCCXYQSP-M1dNrvdcWf_Ic3HLWdltvU"

print("=" * 80)
print("🔍 ДИАГНОСТИКА ПОДКЛЮЧЕНИЯ К YOOKASSA API")
print("=" * 80)
print(f"Account ID: {Configuration.account_id}")
print(f"Secret Key: {Configuration.secret_key[:20]}...")
print()

# Проверка доступности API
print("📡 Проверка доступности YooKassa API...")
try:
    response = requests.get("https://api.yookassa.ru", timeout=10)
    print(f"✅ API доступен (статус: {response.status_code})")
except requests.exceptions.ConnectionError as e:
    print(f"❌ Ошибка подключения: {e}")
    print("⚠️  Возможные причины:")
    print("   - Проблемы с интернет-соединением")
    print("   - Брандмауэр блокирует подключение")
    print("   - Прокси-сервер требует настройки")
except requests.exceptions.Timeout:
    print("❌ Таймаут подключения (API не отвечает)")
except Exception as e:
    print(f"❌ Неожиданная ошибка: {e}")

print()

# Попытка создания платежа с повторными попытками
print("💳 Попытка создания платежа...")
max_retries = 3
retry_delay = 2

for attempt in range(1, max_retries + 1):
    try:
        print(f"Попытка {attempt}/{max_retries}...")
        
        payment = Payment.create({
            "amount": {
                "value": "100.00",
                "currency": "RUB"
            },
            "confirmation": {
                "type": "redirect",
                "return_url": "https://www.example.com/return_url"
            },
            "capture": True,
            "description": "Заказ №1"
        }, uuid.uuid4())
        
        print("✅ Платеж создан успешно!")
        print(f"   Payment ID: {payment.id}")
        print(f"   Status: {payment.status}")
        if payment.confirmation and payment.confirmation.confirmation_url:
            print(f"   Confirmation URL: {payment.confirmation.confirmation_url}")
        break
        
    except requests.exceptions.ConnectionError as e:
        error_msg = str(e)
        print(f"❌ Ошибка подключения (попытка {attempt}/{max_retries}):")
        print(f"   {error_msg}")
        
        if "Connection aborted" in error_msg or "ConnectionResetError" in error_msg:
            print("   ⚠️  Сервер принудительно разорвал соединение")
            print("   Возможные причины:")
            print("      - IP-адрес заблокирован YooKassa")
            print("      - Неправильные учетные данные")
            print("      - Проблемы с SSL/TLS сертификатом")
            print("      - Слишком частые запросы (rate limiting)")
        
        if attempt < max_retries:
            print(f"   ⏳ Повтор через {retry_delay} секунд...")
            time.sleep(retry_delay)
            retry_delay *= 2  # Экспоненциальная задержка
        else:
            print("   ❌ Все попытки исчерпаны")
            print()
            print("💡 Рекомендации:")
            print("   1. Проверьте интернет-соединение")
            print("   2. Убедитесь, что учетные данные правильные")
            print("   3. Проверьте настройки брандмауэра/прокси")
            print("   4. Попробуйте с другого IP-адреса или сети")
            print("   5. Проверьте, не заблокирован ли ваш IP в YooKassa")
            
    except Exception as e:
        error_msg = str(e)
        print(f"❌ Ошибка (попытка {attempt}/{max_retries}):")
        print(f"   Тип: {type(e).__name__}")
        print(f"   Сообщение: {error_msg}")
        
        if "401" in error_msg or "unauthorized" in error_msg.lower():
            print("   ⚠️  Ошибка авторизации - проверьте учетные данные")
        elif "400" in error_msg or "invalid" in error_msg.lower():
            print("   ⚠️  Некорректные данные запроса")
        elif "403" in error_msg or "forbidden" in error_msg.lower():
            print("   ⚠️  Доступ запрещен - проверьте права API ключей")
        
        if attempt < max_retries:
            print(f"   ⏳ Повтор через {retry_delay} секунд...")
            time.sleep(retry_delay)
            retry_delay *= 2
        else:
            print("   ❌ Все попытки исчерпаны")
        break

print("=" * 80)