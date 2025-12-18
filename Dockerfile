# Используем официальный Python 3.11
FROM python:3.11-slim

# Устанавливаем PostgreSQL клиент для работы бэкапов
RUN apt-get update && \
    apt-get install -y postgresql-client && \
    rm -rf /var/lib/apt/lists/*

# Рабочая директория внутри контейнера
WORKDIR /app

# Копируем файлы зависимостей
COPY requirements.txt .

# Устанавливаем зависимости
RUN pip install --no-cache-dir -r requirements.txt

# Копируем весь проект
COPY . .

# Указываем переменные окружения (если хочешь можно подключить .env)
ENV PYTHONUNBUFFERED=1

# Запуск бота
CMD ["python", "main.py"]
