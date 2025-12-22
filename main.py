import asyncio
import sys
import os
from pathlib import Path
from core.loader import bot, dp
from handlers import start, menu
from handlers.cabinet import profile
from handlers.cabinet import support as cabinet_support
from handlers.buy import select_plan, payment
from handlers.admin import servers_router, users_router, dashboard_router, locations_router, promocodes_router, support_router, tutorials_router, documentation_router, backup_router, updates_router
from utils.logger import logger

# Добавляем корневую директорию проекта в PYTHONPATH
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

async def apply_migrations():
    """Автоматически применяет миграции базы данных при старте"""
    from alembic.config import Config
    from alembic import command
    from database.base import engine
    from sqlalchemy import text
    
    logger.info("Проверка и применение миграций базы данных...")
    
    # Ждем, пока база данных станет доступной
    max_retries = 30
    retry_count = 0
    while retry_count < max_retries:
        try:
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            logger.info("Подключение к базе данных установлено")
            break
        except Exception as e:
            retry_count += 1
            if retry_count >= max_retries:
                logger.error(f"Не удалось подключиться к базе данных после {max_retries} попыток: {e}")
                raise
            logger.debug(f"Ожидание подключения к базе данных... ({retry_count}/{max_retries})")
            await asyncio.sleep(2)
    
    # Проверяем, есть ли таблицы в базе данных
    try:
        async with engine.connect() as conn:
            result = await conn.execute(text("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name NOT IN ('alembic_version')
            """))
            tables = result.fetchall()
            tables_exist = len(tables) > 0
    except Exception:
        tables_exist = False
    
    # Применяем миграции через subprocess, чтобы избежать конфликтов с event loop
    try:
        import subprocess
        import sys
        result = subprocess.run(
            [sys.executable, str(project_root / "scripts" / "migrate.py"), "upgrade", "head"],
            capture_output=True,
            text=True,
            cwd=str(project_root)
        )
        if result.returncode != 0:
            logger.error(f"Ошибка при применении миграций: {result.stderr}")
            raise Exception(f"Миграции не применены: {result.stderr}")
        
        # Проверяем результат
        async with engine.connect() as conn:
            result = await conn.execute(text("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name NOT IN ('alembic_version')
            """))
            tables_after = result.fetchall()
            
        if len(tables_after) > 0:
            logger.info(f"Миграции применены успешно. Найдено таблиц: {len(tables_after)}")
        elif not tables_exist:
            logger.warning("Миграции применены, но таблицы не найдены. Возможно, миграция пустая.")
        else:
            logger.info("Миграции базы данных применены успешно")
    except Exception as e:
        logger.error(f"Ошибка при применении миграций: {e}")
        if "Target database is not up to date" in str(e):
            logger.warning("Попробуйте применить миграции вручную: docker exec -it gigabridge_bot python scripts/migrate.py upgrade head")
        elif "Can't locate revision" in str(e):
            logger.warning("Возможно, нужно создать начальную миграцию: docker exec -it gigabridge_bot python scripts/init_db.py")

async def main():
    # Применяем миграции перед запуском бота
    await apply_migrations()
    
    # Запускаем централизованный планировщик
    from services.scheduler import start_scheduler
    start_scheduler()
    
    # Добавляем задачи проверки подписок
    from services.subscription_checker import start_subscription_checker
    start_subscription_checker()
    
    # Добавляем задачу обработки повторных попыток создания подписок
    from services.subscription_retry import start_subscription_retry_handler
    start_subscription_retry_handler()
    
    # Добавляем задачу проверки оплаты серверов
    from services.server_payment_checker import start_server_payment_checker
    start_server_payment_checker()
    
    # Добавляем задачу проверки загрузки серверов
    from services.server_load_checker import start_server_load_checker
    start_server_load_checker()
    
    # Добавляем задачу автоматической отправки бэкапов админам
    from services.backup_scheduler import start_weekly_backup
    start_weekly_backup()
    
    # Патчим методы для автоматического добавления кнопок управления
    from utils.message_utils import patch_bot_methods
    patch_bot_methods()
    
    # Роутеры бота
    # Важно: users_router должен быть раньше servers_router,
    # чтобы обработчик cancel с фильтром состояния обрабатывался первым
    dp.include_router(start.router)
    dp.include_router(menu.router)
    dp.include_router(profile.router)
    dp.include_router(cabinet_support.router)
    dp.include_router(select_plan.router)
    dp.include_router(payment.router)
    dp.include_router(locations_router)
    dp.include_router(users_router)  # Регистрируем раньше servers_router
    dp.include_router(servers_router)
    dp.include_router(dashboard_router)
    dp.include_router(promocodes_router)
    dp.include_router(tutorials_router)
    dp.include_router(documentation_router)
    dp.include_router(backup_router)
    dp.include_router(updates_router)
    dp.include_router(support_router)

    # Перезагружаем .env файл ПЕРЕД созданием конфига
    from dotenv import load_dotenv
    from pathlib import Path
    
    env_file = Path(__file__).parent / '.env'
    if env_file.exists():
        # Читаем содержимое .env файла для проверки
        try:
            with open(env_file, 'r', encoding='utf-8') as f:
                env_content = f.read()
            test_mode_in_file = None
            for line in env_content.split('\n'):
                if line.strip().startswith('TEST_MODE'):
                    test_mode_in_file = line.strip()
                    break
            if test_mode_in_file:
                logger.info(f"📄 Найдено в .env файле: {test_mode_in_file}")
            else:
                logger.warning("⚠️ TEST_MODE не найден в .env файле!")
        except Exception as e:
            logger.error(f"Ошибка при чтении .env файла: {e}")
        
        # Принудительно перезагружаем .env с перезаписью
        load_dotenv(env_file, override=True)
        logger.info(f"✅ Перезагружен .env файл: {env_file}")
    else:
        logger.warning(f"⚠️ .env файл не найден: {env_file}")
    
    # Теперь перезагружаем конфиг, чтобы он прочитал обновленные переменные
    from core.config import config
    config.reload()
    
    # Логируем текущее значение TEST_MODE
    test_mode_env = os.getenv('TEST_MODE', 'не установлено')
    logger.info(f"🔍 TEST_MODE = {config.TEST_MODE} (тип: {type(config.TEST_MODE).__name__})")
    logger.info(f"🔍 TEST_MODE из env: '{test_mode_env}' (тип: {type(test_mode_env).__name__})")
    
    # Проверяем, что значение правильное
    if config.TEST_MODE and test_mode_env.lower() not in ('true', '1', 'yes', 'on'):
        logger.error(f"❌ КРИТИЧЕСКАЯ ОШИБКА: TEST_MODE={config.TEST_MODE}, но в env='{test_mode_env}'")
        logger.error("❌ Возможно, переменная кэширована. Перезапустите Docker контейнер полностью!")
    elif not config.TEST_MODE and test_mode_env.lower() in ('true', '1', 'yes', 'on'):
        logger.error(f"❌ КРИТИЧЕСКАЯ ОШИБКА: TEST_MODE={config.TEST_MODE}, но в env='{test_mode_env}' (должно быть False)")
        logger.error("❌ Проверьте парсинг в core/config.py")
    
    logger.info("Bot started")
    try:
        await dp.start_polling(bot)
    finally:
        # Останавливаем планировщик при завершении
        from services.scheduler import stop_scheduler
        stop_scheduler()

if __name__ == "__main__":
    asyncio.run(main())
