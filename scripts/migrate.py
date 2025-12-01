"""
Скрипт для применения миграций базы данных
Использование:
    python scripts/migrate.py upgrade head    # Применить все миграции
    python scripts/migrate.py downgrade -1    # Откатить последнюю миграцию
    python scripts/migrate.py revision --autogenerate -m "описание"  # Создать новую миграцию
"""
import sys
from pathlib import Path

# Добавляем корневую директорию проекта в PYTHONPATH
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from alembic.config import Config
from alembic import command

def main():
    # Создаем конфигурацию Alembic
    alembic_cfg = Config(str(project_root / "alembic.ini"))
    
    # Передаем аргументы командной строки
    if len(sys.argv) < 2:
        print("Использование:")
        print("  python scripts/migrate.py upgrade head          # Применить все миграции")
        print("  python scripts/migrate.py downgrade -1          # Откатить последнюю миграцию")
        print("  python scripts/migrate.py revision --autogenerate -m 'описание'  # Создать миграцию")
        print("  python scripts/migrate.py current              # Показать текущую версию")
        print("  python scripts/migrate.py history               # Показать историю миграций")
        sys.exit(1)
    
    command_name = sys.argv[1]
    args = sys.argv[2:]
    
    if command_name == "upgrade":
        revision = args[0] if args else "head"
        command.upgrade(alembic_cfg, revision)
    elif command_name == "downgrade":
        revision = args[0] if args else "-1"
        command.downgrade(alembic_cfg, revision)
    elif command_name == "revision":
        autogenerate = "--autogenerate" in args
        message = None
        if "-m" in args:
            message = args[args.index("-m") + 1]
        command.revision(alembic_cfg, message=message, autogenerate=autogenerate)
    elif command_name == "current":
        command.current(alembic_cfg)
    elif command_name == "history":
        command.history(alembic_cfg)
    else:
        print(f"Неизвестная команда: {command_name}")
        sys.exit(1)

if __name__ == "__main__":
    main()

