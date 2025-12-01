# Миграции базы данных

> 📋 **Быстрая шпаргалка:** [MIGRATION_COMMANDS.md](MIGRATION_COMMANDS.md)

Проект использует **Alembic** для управления миграциями базы данных. Это профессиональный подход, который позволяет:

- ✅ Версионировать изменения схемы БД
- ✅ Откатывать изменения при необходимости
- ✅ Безопасно применять изменения в production
- ✅ Не пересоздавать таблицы при каждом запуске

## 🚀 Быстрый старт

### Первоначальная инициализация базы данных

Если база данных пуста, выполните:

```bash
docker exec -it gigabridge_bot python scripts/init_db.py
```

Это создаст начальную миграцию и применит её.

## 📝 Работа с миграциями

### Применение миграций

```bash
# Применить все миграции до последней версии
docker exec -it gigabridge_bot python scripts/migrate.py upgrade head
```

### Создание новой миграции

Когда вы изменили модели в `database/models.py`, создайте миграцию:

```bash
# Создать миграцию с автогенерацией
docker exec -it gigabridge_bot python scripts/migrate.py revision --autogenerate -m "описание изменений"
```

**Пример:**
```bash
docker exec -it gigabridge_bot python scripts/migrate.py revision --autogenerate -m "add user email field"
```

### Просмотр текущей версии

```bash
docker exec -it gigabridge_bot python scripts/migrate.py current
```

### Просмотр истории миграций

```bash
docker exec -it gigabridge_bot python scripts/migrate.py history
```

### Откат миграций

```bash
# Откатить последнюю миграцию
docker exec -it gigabridge_bot python scripts/migrate.py downgrade -1

# Откатить до конкретной версии
docker exec -it gigabridge_bot python scripts/migrate.py downgrade <revision_id>
```

## 📁 Структура миграций

```
database/
  migrations/
    versions/          # Файлы миграций
      xxxx_initial_migration.py
      xxxx_add_user_email.py
      ...
    env.py             # Конфигурация Alembic
    script.py.mako     # Шаблон для миграций
```

## 🔧 Команды Alembic (прямое использование в Docker)

Если нужно использовать Alembic напрямую:

```bash
# Применить миграции
docker exec -it gigabridge_bot alembic upgrade head

# Создать миграцию
docker exec -it gigabridge_bot alembic revision --autogenerate -m "описание"

# Откатить миграцию
docker exec -it gigabridge_bot alembic downgrade -1

# Показать текущую версию
docker exec -it gigabridge_bot alembic current

# Показать историю
docker exec -it gigabridge_bot alembic history
```

## ⚠️ Важные замечания

1. **Не редактируйте существующие миграции** - создавайте новые
2. **Всегда проверяйте автогенерированные миграции** перед применением
3. **Делайте бэкап БД** перед применением миграций в production
4. **Тестируйте миграции** на тестовой базе данных

## 📋 Типичный workflow

1. Изменить модели в `database/models.py`
2. Создать миграцию: `docker exec -it gigabridge_bot python scripts/migrate.py revision --autogenerate -m "описание"`
3. Проверить созданный файл миграции в `database/migrations/versions/`
4. Применить миграцию: `docker exec -it gigabridge_bot python scripts/migrate.py upgrade head`
5. Протестировать изменения

## 🔍 Решение проблем

### Ошибка "Target database is not up to date"

Примените миграции:
```bash
docker exec -it gigabridge_bot python scripts/migrate.py upgrade head
```

### Ошибка "Can't locate revision identified by..."

Проверьте историю миграций:
```bash
docker exec -it gigabridge_bot python scripts/migrate.py history
```

### Миграция не видит изменения

Убедитесь, что:
- Все модели импортированы в `database/models.py`
- Модели импортированы в `database/migrations/env.py`
- Используется флаг `--autogenerate`

## 📚 Дополнительная информация

- [Документация Alembic](https://alembic.sqlalchemy.org/)
- [SQLAlchemy Migrations](https://docs.sqlalchemy.org/en/20/core/metadata.html)

