"""
Централизованная система логирования
Логирование не зависит от TEST_MODE
"""
from loguru import logger
import sys
import os

# Удаляем стандартный обработчик
logger.remove()

# Уровень логирования можно настроить через переменную окружения LOG_LEVEL
# По умолчанию INFO (показывает все важные события)
log_level = os.getenv("LOG_LEVEL", "INFO").upper()

# Единое логирование для всех режимов
# Логирование в консоль
logger.add(
    sys.stdout,
    format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>",
    level=log_level,
    colorize=True
)

# Логирование в файл
logger.add(
    "bot.log",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {message}",
    level=log_level,
    rotation="50 MB",
    retention="30 days",
    compression="zip"
)

# Экспортируем logger для использования в других модулях
__all__ = ['logger']
