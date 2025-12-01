"""
УСТАРЕВШИЙ СКРИПТ - используйте scripts/init_db.py или scripts/migrate.py

Этот файл оставлен для обратной совместимости.
Для работы с миграциями используйте:
    python scripts/migrate.py upgrade head
    python scripts/init_db.py
"""
import asyncio
import sys
from pathlib import Path

# Добавляем корневую директорию проекта в PYTHONPATH
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from alembic.config import Config
from alembic import command

async def init_db():
    """Устаревшая функция - используйте миграции Alembic"""
    print("⚠️  ВНИМАНИЕ: Эта функция устарела!")
    print("💡 Используйте миграции Alembic:")
    print("   python scripts/migrate.py upgrade head")
    print("   или")
    print("   python scripts/init_db.py")
    
    # Для обратной совместимости применяем миграции
    alembic_cfg = Config(str(project_root / "alembic.ini"))
    command.upgrade(alembic_cfg, "head")


if __name__ == "__main__":
    asyncio.run(init_db())
