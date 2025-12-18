"""
Скрипт для создания бэкапа базы данных
Создает SQL дамп PostgreSQL базы данных и упаковывает его в архив
"""
import os
import sys
import subprocess
import json
from pathlib import Path
from datetime import datetime
import tarfile
import gzip

# Добавляем корневую директорию проекта в PYTHONPATH
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from core.config import config
from utils.logger import logger


def create_backup():
    """Создает бэкап базы данных"""
    try:
        # Создаем директорию для бэкапов, если её нет
        backups_dir = project_root / "backups"
        backups_dir.mkdir(exist_ok=True)
        
        # Генерируем имя файла с датой и временем
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_name = f"backup_{timestamp}"
        sql_file = backups_dir / f"{backup_name}.sql"
        archive_file = backups_dir / f"{backup_name}.tar.gz"
        
        logger.info(f"Создание бэкапа базы данных: {backup_name}")
        
        # Формируем команду pg_dump
        # Используем синхронный pg_dump, так как он более надежен для бэкапов
        pg_dump_cmd = [
            "pg_dump",
            "-h", config.DB_HOST,
            "-p", str(config.DB_PORT),
            "-U", config.DB_USER,
            "-d", config.DB_NAME,
            "-F", "plain",  # Формат plain SQL
            "-f", str(sql_file),
            "--no-owner",  # Не включать команды владения
            "--no-acl",  # Не включать команды прав доступа
            "--clean",  # Включать команды DROP перед CREATE
        ]
        
        # Устанавливаем переменную окружения для пароля
        env = os.environ.copy()
        env["PGPASSWORD"] = config.DB_PASSWORD
        
        # Выполняем pg_dump
        logger.info(f"Выполнение pg_dump для базы данных {config.DB_NAME}...")
        result = subprocess.run(
            pg_dump_cmd,
            env=env,
            capture_output=True,
            text=True
        )
        
        if result.returncode != 0:
            error_msg = result.stderr or result.stdout
            logger.error(f"Ошибка при создании дампа базы данных: {error_msg}")
            return None, f"Ошибка pg_dump: {error_msg}"
        
        # Проверяем, что файл создан и не пустой
        if not sql_file.exists() or sql_file.stat().st_size == 0:
            logger.error("Файл дампа не создан или пуст")
            return None, "Файл дампа не создан или пуст"
        
        logger.info(f"SQL дамп создан: {sql_file.stat().st_size / 1024 / 1024:.2f} MB")
        
        # Создаем метаданные бэкапа
        metadata = {
            "backup_name": backup_name,
            "created_at": datetime.now().isoformat(),
            "database_name": config.DB_NAME,
            "database_host": config.DB_HOST,
            "database_port": config.DB_PORT,
            "file_size_mb": round(sql_file.stat().st_size / 1024 / 1024, 2),
            "version": "1.0"
        }
        
        metadata_file = backups_dir / f"{backup_name}_metadata.json"
        with open(metadata_file, "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)
        
        # Создаем архив (tar.gz)
        logger.info("Создание архива...")
        with tarfile.open(archive_file, "w:gz") as tar:
            tar.add(sql_file, arcname=f"{backup_name}.sql")
            tar.add(metadata_file, arcname=f"{backup_name}_metadata.json")
        
        # Удаляем временные файлы
        sql_file.unlink()
        metadata_file.unlink()
        
        archive_size = archive_file.stat().st_size / 1024 / 1024
        logger.info(f"Бэкап успешно создан: {archive_file.name} ({archive_size:.2f} MB)")
        
        # Автоматически очищаем старые бэкапы (оставляем последние 20)
        try:
            deleted_count, cleanup_error = cleanup_old_backups(keep_count=20)
            if deleted_count > 0:
                logger.info(f"Удалено старых бэкапов: {deleted_count}")
            if cleanup_error:
                logger.warning(f"Предупреждение при очистке: {cleanup_error}")
        except Exception as e:
            logger.warning(f"Не удалось очистить старые бэкапы: {e}")
        
        return str(archive_file), None
        
    except FileNotFoundError:
        error_msg = "pg_dump не найден. Убедитесь, что PostgreSQL клиент установлен."
        logger.error(error_msg)
        return None, error_msg
    except Exception as e:
        error_msg = f"Ошибка при создании бэкапа: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return None, error_msg


def list_backups():
    """Возвращает список доступных бэкапов"""
    backups_dir = project_root / "backups"
    if not backups_dir.exists():
        return []
    
    backups = []
    for file in backups_dir.glob("backup_*.tar.gz"):
        try:
            stat = file.stat()
            backups.append({
                "name": file.name,
                "path": str(file),
                "size_mb": round(stat.st_size / 1024 / 1024, 2),
                "created_at": datetime.fromtimestamp(stat.st_mtime).isoformat()
            })
        except Exception as e:
            logger.warning(f"Ошибка при чтении информации о бэкапе {file.name}: {e}")
    
    # Сортируем по дате создания (новые первыми)
    backups.sort(key=lambda x: x["created_at"], reverse=True)
    return backups


def cleanup_old_backups(keep_count: int = 10):
    """
    Удаляет старые бэкапы, оставляя только последние N
    
    Args:
        keep_count: Количество бэкапов для сохранения (по умолчанию 10)
    
    Returns:
        tuple: (deleted_count: int, error: str or None)
    """
    try:
        backups = list_backups()
        
        if len(backups) <= keep_count:
            return 0, None
        
        # Удаляем старые бэкапы (оставляем первые keep_count)
        deleted_count = 0
        for backup in backups[keep_count:]:
            try:
                backup_file = Path(backup["path"])
                if backup_file.exists():
                    backup_file.unlink()
                    deleted_count += 1
                    logger.info(f"Удален старый бэкап: {backup['name']}")
            except Exception as e:
                logger.warning(f"Ошибка при удалении бэкапа {backup['name']}: {e}")
        
        return deleted_count, None
        
    except Exception as e:
        error_msg = f"Ошибка при очистке старых бэкапов: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return 0, error_msg


if __name__ == "__main__":
    # Если запущен как скрипт, создаем бэкап
    backup_path, error = create_backup()
    if error:
        print(f"Ошибка: {error}")
        sys.exit(1)
    else:
        print(f"Бэкап успешно создан: {backup_path}")

