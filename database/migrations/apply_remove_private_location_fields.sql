-- Миграция: удаление полей is_private и password из таблицы locations
-- Выполните этот SQL скрипт в вашей базе данных PostgreSQL

-- 1. Удаляем индекс
DROP INDEX IF EXISTS ix_locations_is_private;

-- 2. Удаляем колонки
ALTER TABLE locations DROP COLUMN IF EXISTS password;
ALTER TABLE locations DROP COLUMN IF EXISTS is_private;

-- 3. Обновляем версию миграции в таблице alembic_version (если нужно)
-- Это делается автоматически при использовании alembic, но для ручного применения можно пропустить

