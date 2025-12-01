import asyncio
import sys
from pathlib import Path
from core.loader import bot, dp
from handlers import start, menu
from handlers.cabinet import profile
from handlers.cabinet import support as cabinet_support
from handlers.buy import select_plan, payment
from handlers.admin import servers_router, users_router, dashboard_router, locations_router, promocodes_router, support_router

# Добавляем корневую директорию проекта в PYTHONPATH
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

async def apply_migrations():
    """Автоматически применяет миграции базы данных при старте"""
    from alembic.config import Config
    from alembic import command
    from database.base import engine
    from sqlalchemy import text
    
    print("🔄 Проверка и применение миграций базы данных...")
    
    # Ждем, пока база данных станет доступной
    max_retries = 30
    retry_count = 0
    while retry_count < max_retries:
        try:
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            print("✅ Подключение к базе данных установлено")
            break
        except Exception as e:
            retry_count += 1
            if retry_count >= max_retries:
                print(f"❌ Не удалось подключиться к базе данных после {max_retries} попыток")
                raise
            print(f"⏳ Ожидание подключения к базе данных... ({retry_count}/{max_retries})")
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
            print(f"⚠️  Ошибка при применении миграций:")
            print(result.stderr)
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
            print(f"✅ Миграции базы данных применены успешно. Найдено таблиц: {len(tables_after)}")
        elif not tables_exist:
            print("⚠️  Миграции применены, но таблицы не найдены.")
            print("💡 Возможно, миграция пустая. Создайте новую миграцию:")
            print("   docker exec -it gigabridge_bot python scripts/migrate.py revision --autogenerate -m 'Initial tables'")
            print("   docker exec -it gigabridge_bot python scripts/migrate.py upgrade head")
        else:
            print("✅ Миграции базы данных применены успешно")
    except Exception as e:
        print(f"⚠️  Ошибка при применении миграций: {e}")
        if "Target database is not up to date" in str(e):
            print("💡 Попробуйте применить миграции вручную:")
            print("   docker exec -it gigabridge_bot python scripts/migrate.py upgrade head")
        elif "Can't locate revision" in str(e):
            print("💡 Возможно, нужно создать начальную миграцию:")
            print("   docker exec -it gigabridge_bot python scripts/init_db.py")
        else:
            print("💡 Проверьте логи выше для деталей")

async def main():
    # Применяем миграции перед запуском бота
    await apply_migrations()
    
    # Запускаем централизованный планировщик
    from services.scheduler import start_scheduler
    start_scheduler()
    
    # Добавляем задачи проверки подписок
    from services.subscription_checker import start_subscription_checker
    start_subscription_checker()
    
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
    dp.include_router(support_router)

    print("🤖 Bot started...")
    try:
        await dp.start_polling(bot)
    finally:
        # Останавливаем планировщик при завершении
        from services.scheduler import stop_scheduler
        stop_scheduler()

if __name__ == "__main__":
    asyncio.run(main())
