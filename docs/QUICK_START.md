# ⚡ Быстрый старт

## Минимальные шаги для запуска

```bash
# 1. Установка Docker (Ubuntu/Debian)
sudo apt update && sudo apt install -y docker.io docker-compose-plugin
sudo usermod -aG docker $USER && newgrp docker

# 2. Клонирование репозитория
git clone <URL_РЕПОЗИТОРИЯ> GigaBridge
cd GigaBridge

# 3. Создание .env файла
cp docs/env.example .env
nano .env  # Заполните BOT_TOKEN и другие необходимые переменные

# 4. Запуск
docker compose build
docker compose up -d

# 5. Применение миграций
docker exec -it gigabridge_bot python scripts/migrate.py upgrade head

# 6. Проверка
docker compose logs -f bot
```

## Обязательные переменные в .env

```env
BOT_TOKEN=ваш_токен_от_BotFather
HIDDIFY_API_URL=http://ваш_сервер:порт
HIDDIFY_API_KEY=ваш_api_ключ
```

## Проверка работы

```bash
# Статус контейнеров
docker compose ps

# Логи бота
docker compose logs -f bot

# Отправьте /start боту в Telegram
```

**Полная инструкция:** [SERVER_SETUP.md](SERVER_SETUP.md)
