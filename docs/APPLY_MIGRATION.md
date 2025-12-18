# Применение миграции для удаления полей is_private и password

## Проблема
Код обновлен, но база данных еще содержит старые поля `is_private` и `password` в таблице `locations`, что вызывает ошибку:
```
asyncpg.exceptions.UndefinedColumnError: column locations.is_private does not exist
```

## Решение

### Вариант 1: Через Docker (рекомендуется)

Если бот запущен через Docker:

```bash
docker exec -it gigabridge_bot python scripts/migrate.py upgrade head
```

### Вариант 2: Через Docker Compose

Если используете docker-compose:

```bash
docker-compose exec bot python scripts/migrate.py upgrade head
```

### Вариант 3: Ручное применение через SQL

Если не можете использовать Docker, выполните SQL скрипт напрямую в базе данных:

```bash
# Подключитесь к базе данных
psql -U postgres -d gigabridge_db

# Или через Docker:
docker exec -it gigabridge_db psql -U postgres -d gigabridge_db
```

Затем выполните SQL из файла `database/migrations/apply_remove_private_location_fields.sql`:

```sql
-- Удаляем индекс
DROP INDEX IF EXISTS ix_locations_is_private;

-- Удаляем колонки
ALTER TABLE locations DROP COLUMN IF EXISTS password;
ALTER TABLE locations DROP COLUMN IF EXISTS is_private;
```

### Вариант 4: Через Python скрипт (если установлен alembic локально)

```bash
python scripts/migrate.py upgrade head
```

## Проверка

После применения миграции проверьте, что поля удалены:

```sql
SELECT column_name 
FROM information_schema.columns 
WHERE table_name = 'locations' 
AND column_name IN ('is_private', 'password');
```

Должен вернуться пустой результат.

## Важно

⚠️ **Сделайте бэкап базы данных перед применением миграции!**

```bash
# Бэкап через Docker
docker exec gigabridge_db pg_dump -U postgres gigabridge_db > backup_$(date +%Y%m%d_%H%M%S).sql
```

