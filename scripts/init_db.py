"""
Скрипт для первоначальной инициализации базы данных
Создает начальную миграцию и применяет её (только для первого запуска)
Использование: python scripts/init_db.py
"""
import sys
from pathlib import Path

# Добавляем корневую директорию проекта в PYTHONPATH
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from alembic.config import Config
from alembic import command
from alembic.runtime.migration import MigrationContext
from sqlalchemy import inspect, text
from database.base import engine
import asyncio

async def check_tables_exist():
    """Проверяет, существуют ли таблицы в базе данных"""
    try:
        async with engine.connect() as conn:
            result = await conn.execute(text("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name NOT IN ('alembic_version')
            """))
            tables = result.fetchall()
            return len(tables) > 0
    except Exception as e:
        print(f"⚠️  Ошибка при проверке таблиц: {e}")
        return False

async def check_migrations_applied():
    """Проверяет, применены ли миграции"""
    try:
        async with engine.connect() as conn:
            result = await conn.execute(text("SELECT version_num FROM alembic_version"))
            version = result.fetchone()
            return version is not None
    except Exception:
        return False

async def main():
    print("🔍 Проверка состояния базы данных...")
    
    # Проверяем, применены ли миграции
    migrations_applied = await check_migrations_applied()
    
    if migrations_applied:
        print("✅ Миграции уже применены.")
        print("💡 Используйте 'python scripts/migrate.py upgrade head' для применения новых миграций.")
        return
    
    # Проверяем, есть ли таблицы (старый способ без миграций)
    tables_exist = await check_tables_exist()
    
    if tables_exist:
        print("⚠️  В базе данных есть таблицы, но миграции не применены.")
        print("💡 Рекомендуется создать начальную миграцию на основе существующих таблиц:")
        print("   python scripts/migrate.py revision --autogenerate -m 'Initial migration'")
        print("   python scripts/migrate.py upgrade head")
        return
    
    print("📦 База данных пуста. Создание начальной миграции...")
    
    # Создаем конфигурацию Alembic
    alembic_cfg = Config(str(project_root / "alembic.ini"))
    
    # Создаем начальную миграцию
    print("📝 Создание начальной миграции...")
    command.revision(
        alembic_cfg,
        message="Initial migration",
        autogenerate=True
    )
    
    # Применяем миграцию
    print("🚀 Применение миграции...")
    command.upgrade(alembic_cfg, "head")
    
    print("✅ База данных успешно инициализирована!")

if __name__ == "__main__":
    asyncio.run(main())

