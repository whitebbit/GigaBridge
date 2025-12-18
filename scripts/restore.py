"""
Скрипт для восстановления базы данных из бэкапа
Восстанавливает базу данных из SQL дампа
"""
import os
import sys
import subprocess
import json
import tarfile
from pathlib import Path
from datetime import datetime

# Добавляем корневую директорию проекта в PYTHONPATH
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from core.config import config
from utils.logger import logger


def restore_backup(backup_path: str, confirm: bool = False):
    """
    Восстанавливает базу данных из бэкапа
    
    Args:
        backup_path: Путь к файлу бэкапа (.tar.gz)
        confirm: Подтверждение восстановления (по умолчанию False для безопасности)
    
    Returns:
        tuple: (success: bool, message: str)
    """
    if not confirm:
        return False, "Требуется подтверждение. Используйте --confirm для подтверждения восстановления."
    
    try:
        backup_file = Path(backup_path)
        if not backup_file.exists():
            return False, f"Файл бэкапа не найден: {backup_path}"
        
        if not backup_file.suffixes == ['.tar', '.gz']:
            return False, "Файл должен быть в формате .tar.gz"
        
        # Создаем временную директорию для распаковки
        temp_dir = project_root / "backups" / "temp_restore"
        temp_dir.mkdir(parents=True, exist_ok=True)
        
        try:
            # Распаковываем архив
            logger.info(f"Распаковка архива {backup_file.name}...")
            with tarfile.open(backup_file, "r:gz") as tar:
                tar.extractall(temp_dir)
            
            # Ищем SQL файл и метаданные
            sql_files = list(temp_dir.glob("*.sql"))
            metadata_files = list(temp_dir.glob("*_metadata.json"))
            
            if not sql_files:
                return False, "SQL файл не найден в архиве"
            
            sql_file = sql_files[0]
            
            # Читаем метаданные, если есть
            metadata = None
            if metadata_files:
                try:
                    with open(metadata_files[0], "r", encoding="utf-8") as f:
                        metadata = json.load(f)
                    logger.info(f"Метаданные бэкапа: создан {metadata.get('created_at', 'неизвестно')}")
                except Exception as e:
                    logger.warning(f"Не удалось прочитать метаданные: {e}")
            
            # Формируем команду psql для восстановления
            psql_cmd = [
                "psql",
                "-h", config.DB_HOST,
                "-p", str(config.DB_PORT),
                "-U", config.DB_USER,
                "-d", config.DB_NAME,
                "-f", str(sql_file),
            ]
            
            # Устанавливаем переменную окружения для пароля
            env = os.environ.copy()
            env["PGPASSWORD"] = config.DB_PASSWORD
            
            logger.info(f"Восстановление базы данных {config.DB_NAME} из бэкапа...")
            logger.warning("⚠️ ВНИМАНИЕ: Все текущие данные будут перезаписаны!")
            
            # Выполняем восстановление
            result = subprocess.run(
                psql_cmd,
                env=env,
                capture_output=True,
                text=True
            )
            
            if result.returncode != 0:
                error_msg = result.stderr or result.stdout
                logger.error(f"Ошибка при восстановлении базы данных: {error_msg}")
                return False, f"Ошибка восстановления: {error_msg}"
            
            logger.info("База данных успешно восстановлена из бэкапа")
            return True, f"База данных успешно восстановлена из бэкапа: {backup_file.name}"
            
        finally:
            # Удаляем временную директорию
            import shutil
            if temp_dir.exists():
                shutil.rmtree(temp_dir)
                logger.info("Временные файлы удалены")
        
    except FileNotFoundError:
        error_msg = "psql не найден. Убедитесь, что PostgreSQL клиент установлен."
        logger.error(error_msg)
        return False, error_msg
    except Exception as e:
        error_msg = f"Ошибка при восстановлении бэкапа: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return False, error_msg


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Использование: python restore.py <путь_к_бэкапу> [--confirm]")
        sys.exit(1)
    
    backup_path = sys.argv[1]
    confirm = "--confirm" in sys.argv
    
    success, message = restore_backup(backup_path, confirm=confirm)
    if success:
        print(f"✅ {message}")
        sys.exit(0)
    else:
        print(f"❌ {message}")
        sys.exit(1)

