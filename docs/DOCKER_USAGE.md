# Использование Docker

## Основные команды

### Запуск контейнеров

```bash
docker compose up -d
```

### Остановка контейнеров

```bash
# Остановить контейнеры БЕЗ удаления данных
docker compose down

# Остановить контейнеры И УДАЛИТЬ ВСЕ ДАННЫЕ (volumes)
docker compose down -v
```

### Перезапуск контейнеров

```bash
# Перезапустить контейнеры (данные сохраняются)
docker compose restart

# Или остановить и запустить заново
docker compose down
docker compose up -d
```

## ⚠️ ВАЖНО: Сохранение данных

### ✅ Данные СОХРАНЯЮТСЯ при:
- `docker compose restart` - перезапуск контейнеров
- `docker compose down` - остановка без флага `-v`
- `docker compose stop` - остановка контейнеров
- Перезагрузке сервера/компьютера

### ❌ Данные УДАЛЯЮТСЯ при:
- `docker compose down -v` - флаг `-v` удаляет все volumes
- `docker volume rm gigabridge_db_data` - прямое удаление volume
- `docker compose down --volumes` - альтернативный синтаксис

## Проверка состояния

### Проверить запущенные контейнеры
```bash
docker compose ps
```

### Проверить volumes (хранилища данных)
```bash
docker volume ls | findstr gigabridge
```

### Проверить данные в базе
```bash
docker exec gigabridge_db psql -U postgres -d gigabridge_db -c "SELECT * FROM users;"
```

## Резервное копирование

### Создать бэкап базы данных
```bash
docker exec gigabridge_db pg_dump -U postgres gigabridge_db > backup.sql
```

### Восстановить из бэкапа
```bash
docker exec -i gigabridge_db psql -U postgres gigabridge_db < backup.sql
```

## Полная очистка (удалить всё)

Если нужно полностью удалить проект и все данные:

```bash
# Остановить и удалить контейнеры и volumes
docker compose down -v

# Удалить образы (опционально)
docker compose down --rmi all

# Удалить volume вручную (если не удалился)
docker volume rm gigabridge_db_data
```

## Типичные сценарии

### Разработка (данные не важны)
```bash
docker compose down -v  # Удалить всё
docker compose up -d     # Запустить заново
```

### Production (данные важны!)
```bash
docker compose down      # Только остановить
docker compose up -d     # Запустить заново
# Или просто
docker compose restart   # Перезапустить
```

### Обновление кода
```bash
docker compose down      # Остановить
# Обновить код
docker compose build     # Пересобрать образ
docker compose up -d     # Запустить
```

