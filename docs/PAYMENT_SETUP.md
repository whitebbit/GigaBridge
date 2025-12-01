# Настройка оплаты через YooKassa

Данная документация описывает процесс настройки и использования системы оплаты через YooKassa в боте GigaBridge.

## Содержание

1. [Требования](#требования)
2. [Настройка YooKassa](#настройка-yookassa)
3. [Конфигурация бота](#конфигурация-бота)
4. [Миграции базы данных](#миграции-базы-данных)
5. [Тестирование](#тестирование)
6. [Архитектура](#архитектура)
7. [Масштабирование](#масштабирование)

## Требования

- Аккаунт в YooKassa (личный кабинет или магазин)
- Shop ID и Secret Key от YooKassa
- Настроенный бот с базой данных PostgreSQL
- Python 3.11+

## Настройка YooKassa

### 1. Регистрация в YooKassa

1. Перейдите на [yookassa.ru](https://yookassa.ru)
2. Зарегистрируйте аккаунт или войдите в существующий
3. Создайте магазин (если еще не создан)

### 2. Получение ключей

1. В личном кабинете YooKassa перейдите в раздел **Настройки** → **API**
2. Скопируйте **Shop ID** и **Secret Key**
3. Для тестирования используйте тестовые ключи (доступны в разделе "Тестовые данные")

### 3. Настройка Webhook (опционально)

Для получения уведомлений о статусе платежей:

1. В настройках магазина перейдите в раздел **Webhook**
2. Укажите URL вашего бота (например: `https://your-domain.com/webhook/yookassa`)
3. Выберите события: `payment.succeeded`, `payment.canceled`

**Примечание:** В текущей реализации используется polling для проверки статуса платежей, webhook можно добавить позже.

## Конфигурация бота

### 1. Переменные окружения

Добавьте следующие переменные в файл `.env`:

```env
# YooKassa настройки
YOOKASSA_SHOP_ID=your_shop_id
YOOKASSA_SECRET_KEY=your_secret_key
YOOKASSA_TEST_MODE=true  # true для тестирования, false для продакшена
WEBHOOK_URL=https://your-domain.com/webhook/yookassa  # опционально
```

### 2. Пример .env файла

```env
# Telegram Bot
BOT_TOKEN=your_bot_token

# Database
DB_HOST=db
DB_PORT=5432
DB_NAME=gigabridge_db
DB_USER=postgres
DB_PASSWORD=your_password

# Hiddify (опционально)
HIDDIFY_API_URL=https://your-hiddify-server.com
HIDDIFY_API_KEY=your_hiddify_api_key

# YooKassa
YOOKASSA_SHOP_ID=123456
YOOKASSA_SECRET_KEY=test_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
YOOKASSA_TEST_MODE=true
```

## Миграции базы данных

Система автоматически применяет миграции при запуске бота. Если нужно применить вручную:

```bash
# В контейнере
docker exec gigabridge_bot python scripts/migrate.py upgrade head

# Или локально
python scripts/migrate.py upgrade head
```

### Изменения в модели Payment

Миграция `3a1b2c3d4e5f_update_payments_for_yookassa.py` добавляет:

- `server_id` - связь с сервером
- `yookassa_payment_id` - ID платежа в YooKassa (уникальный)
- `paid_at` - дата оплаты
- Изменение валюты по умолчанию с USD на RUB

## Тестирование

### 1. Тестовые карты YooKassa

Для тестирования используйте следующие карты:

- **Успешная оплата:** `5555 5555 5555 4444`
- **Отклоненная оплата:** `5555 5555 5555 4477`
- **3-D Secure:** `5555 5555 5555 4477` (с кодом 123)

### 2. Проверка работы

1. Запустите бота: `docker compose up -d`
2. Откройте бота в Telegram
3. Нажмите кнопку **Покупка**
4. Выберите сервер
5. Нажмите **Оплатить**
6. Используйте тестовую карту для оплаты
7. После успешной оплаты вы получите тестовый ключ

### 3. Проверка логов

```bash
# Просмотр логов бота
docker logs gigabridge_bot -f

# Проверка статуса платежей в БД
docker exec -it gigabridge_db psql -U postgres -d gigabridge_db -c "SELECT * FROM payments ORDER BY created_at DESC LIMIT 5;"
```

## Архитектура

### Структура файлов

```
services/
  └── yookassa_service.py    # Сервис для работы с YooKassa API

handlers/buy/
  ├── select_plan.py          # Выбор сервера для покупки
  └── payment.py              # Обработка оплаты

utils/db.py                   # Функции для работы с платежами в БД
```

### Поток оплаты

1. **Выбор сервера** → Пользователь выбирает сервер из списка
2. **Создание платежа** → Бот создает платеж в YooKassa через API
3. **Сохранение в БД** → Платеж сохраняется в базе данных со статусом `pending`
4. **Перенаправление** → Пользователь переходит на страницу оплаты YooKassa
5. **Проверка статуса** → Бот периодически проверяет статус платежа (каждые 5 секунд)
6. **Обработка успеха** → При успешной оплате:
   - Обновляется статус платежа на `paid`
   - Создается подписка
   - Генерируется тестовый ключ
   - Пользователь получает уведомление с ключом

### Ключевые компоненты

#### YooKassaService

Класс для работы с YooKassa API:

- `create_payment()` - создание платежа
- `get_payment_status()` - получение статуса платежа
- `cancel_payment()` - отмена платежа

#### Обработчики

- `select_server_for_payment()` - выбор сервера
- `create_payment_handler()` - создание платежа
- `check_payment_status()` - проверка статуса (фоновая задача)
- `handle_successful_payment()` - обработка успешной оплаты

## Масштабирование

### 1. Webhook вместо Polling

Для продакшена рекомендуется использовать webhook вместо polling:

1. Создайте endpoint для приема webhook от YooKassa
2. Добавьте обработчик в `handlers/buy/payment.py`
3. Настройте webhook URL в YooKassa

Пример обработчика webhook:

```python
@router.post("/webhook/yookassa")
async def yookassa_webhook(request: Request):
    data = await request.json()
    payment_id = data.get("object", {}).get("id")
    status = data.get("object", {}).get("status")
    
    if status == "succeeded":
        # Обработка успешной оплаты
        pass
```

### 2. Очередь задач

Для обработки большого количества платежей используйте очередь задач (например, Celery или RQ):

```python
from celery import Celery

celery_app = Celery('gigabridge')

@celery_app.task
def process_payment(payment_id):
    # Обработка платежа
    pass
```

### 3. Кэширование

Для уменьшения нагрузки на БД используйте кэширование:

```python
from functools import lru_cache

@lru_cache(maxsize=100)
async def get_server_cached(server_id: int):
    return await get_server_by_id(server_id)
```

### 4. Мониторинг

Добавьте мониторинг платежей:

- Логирование всех операций
- Метрики успешных/неуспешных платежей
- Алерты при ошибках

## Безопасность

### Рекомендации

1. **Храните ключи в секретах** - никогда не коммитьте `.env` файл
2. **Используйте HTTPS** - для webhook обязательно используйте HTTPS
3. **Проверяйте подписи** - при использовании webhook проверяйте подпись запросов
4. **Логируйте операции** - ведите логи всех платежных операций
5. **Ограничьте доступ** - ограничьте доступ к админ-панели

## Устранение неполадок

### Платеж не создается

1. Проверьте правильность Shop ID и Secret Key
2. Убедитесь, что `YOOKASSA_TEST_MODE=true` для тестирования
3. Проверьте логи: `docker logs gigabridge_bot`

### Платеж не обрабатывается

1. Проверьте, что бот запущен и работает
2. Проверьте статус платежа в личном кабинете YooKassa
3. Проверьте логи на наличие ошибок

### Ключ не выдается

1. Проверьте, что подписка создается в БД
2. Проверьте логи функции `handle_successful_payment()`
3. Убедитесь, что пользователь существует в БД

## Дополнительные ресурсы

- [Документация YooKassa](https://yookassa.ru/developers/api)
- [Python SDK YooKassa](https://github.com/yoomoney/yookassa-sdk-python)
- [Документация бота](docs/README.md)

## Поддержка

При возникновении проблем:

1. Проверьте логи бота
2. Проверьте документацию YooKassa
3. Создайте issue в репозитории проекта

