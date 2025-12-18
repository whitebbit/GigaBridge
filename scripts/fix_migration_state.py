"""
Скрипт для исправления состояния базы данных после ошибки миграции
Использование:
    python scripts/fix_migration_state.py
"""
import sys
import asyncio
from pathlib import Path

# Добавляем корневую директорию проекта в PYTHONPATH
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from database.base import engine
from sqlalchemy import text
from utils.logger import logger


async def check_database_state():
    """Проверяет состояние базы данных"""
    try:
        async with engine.connect() as conn:
            # Проверяем, есть ли таблица alembic_version
            result = await conn.execute(text("""
                SELECT EXISTS (
                    SELECT 1 
                    FROM information_schema.tables 
                    WHERE table_schema = 'public' 
                    AND table_name = 'alembic_version'
                )
            """))
            alembic_exists = result.scalar()
            
            if alembic_exists:
                # Получаем текущую версию миграции
                result = await conn.execute(text("SELECT version_num FROM alembic_version"))
                version = result.scalar()
                logger.info(f"Текущая версия миграции: {version}")
            else:
                logger.warning("Таблица alembic_version не найдена")
            
            # Проверяем, есть ли таблицы
            result = await conn.execute(text("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name NOT IN ('alembic_version')
                ORDER BY table_name
            """))
            tables = result.fetchall()
            
            logger.info(f"Найдено таблиц: {len(tables)}")
            if tables:
                logger.info("Таблицы: " + ", ".join([t[0] for t in tables]))
            
            # Проверяем, существует ли колонка subscription_url
            result = await conn.execute(text("""
                SELECT EXISTS (
                    SELECT 1 
                    FROM information_schema.columns 
                    WHERE table_name = 'servers' 
                    AND column_name = 'subscription_url'
                    AND table_schema = 'public'
                )
            """))
            column_exists = result.scalar()
            logger.info(f"Колонка subscription_url в таблице servers: {'существует' if column_exists else 'не существует'}")
            
            return {
                'alembic_exists': alembic_exists,
                'version': version if alembic_exists else None,
                'tables_count': len(tables),
                'subscription_url_exists': column_exists
            }
    except Exception as e:
        logger.error(f"Ошибка при проверке состояния базы данных: {e}")
        raise


async def fix_database_state():
    """Исправляет состояние базы данных"""
    try:
        async with engine.connect() as conn:
            # Откатываем любые незавершенные транзакции
            await conn.execute(text("ROLLBACK"))
            logger.info("Откат незавершенных транзакций выполнен")
            
            # Проверяем состояние
            state = await check_database_state()
            
            if state['tables_count'] == 0:
                logger.warning("База данных пуста. Нужно применить миграции.")
                logger.info("Выполните: docker exec -it gigabridge_bot python scripts/migrate.py upgrade head")
            else:
                logger.info("База данных содержит таблицы. Можно попробовать применить миграции.")
                
    except Exception as e:
        logger.error(f"Ошибка при исправлении состояния базы данных: {e}")
        raise


async def main():
    logger.info("Проверка состояния базы данных...")
    try:
        state = await check_database_state()
        
        if state['tables_count'] == 0 and state['alembic_exists']:
            logger.warning("База данных в неконсистентном состоянии: есть alembic_version, но нет таблиц")
            logger.info("Рекомендуется пересоздать базу данных или вручную исправить состояние")
        elif state['tables_count'] == 0:
            logger.info("База данных пуста. Это нормально для первого запуска.")
        else:
            logger.info("База данных содержит данные. Состояние выглядит нормально.")
            
    except Exception as e:
        logger.error(f"Не удалось проверить состояние базы данных: {e}")
        logger.info("Попробуйте пересоздать базу данных:")
        logger.info("  docker-compose down -v")
        logger.info("  docker-compose up -d")


if __name__ == "__main__":
    asyncio.run(main())
