from dotenv import load_dotenv
import os
from pathlib import Path

# Принудительно загружаем .env файл с перезаписью существующих переменных
# Это нужно, чтобы переменные из .env файла имели приоритет над системными
env_path = Path(__file__).parent.parent / '.env'
if env_path.exists():
    load_dotenv(env_path, override=True)
else:
    # Если .env в корне не найден, пробуем загрузить из текущей директории
    load_dotenv(override=True)

class Config:
    """Класс конфигурации с возможностью перезагрузки"""
    
    def __init__(self):
        """Инициализация конфига - загружаем переменные окружения"""
        self.reload()
    
    def reload(self):
        """Перезагрузить конфиг из переменных окружения"""
        self.BOT_TOKEN = os.getenv("BOT_TOKEN")

        self.DB_HOST = os.getenv("DB_HOST")
        self.DB_PORT = os.getenv("DB_PORT")
        self.DB_NAME = os.getenv("DB_NAME")
        self.DB_USER = os.getenv("DB_USER")
        self.DB_PASSWORD = os.getenv("DB_PASSWORD")

        self.HIDDIFY_API_URL = os.getenv("HIDDIFY_API_URL")
        self.HIDDIFY_API_KEY = os.getenv("HIDDIFY_API_KEY")
        
        # YooKassa настройки
        self.YOOKASSA_SHOP_ID = os.getenv("YOOKASSA_SHOP_ID")
        self.YOOKASSA_SECRET_KEY = os.getenv("YOOKASSA_SECRET_KEY")
        self.WEBHOOK_URL = os.getenv("WEBHOOK_URL", "")  # URL для webhook от YooKassa
        
        # Настройки скидок
        self.FIRST_PURCHASE_DISCOUNT_PERCENT = float(os.getenv("FIRST_PURCHASE_DISCOUNT_PERCENT", "20"))  # Процент скидки на первую покупку (по умолчанию 20%)
        
        # Тестовый режим для подписок
        # Если true: подписка создается на 1 минуту, проверка каждую минуту
        # Если false: подписка на 30 дней (из тарифа), проверка каждые 6 часов
        # Парсим значение: принимаем только "true" (любой регистр) как True, все остальное - False
        _test_mode_raw = os.getenv("TEST_MODE", "false")
        _test_mode_str = str(_test_mode_raw).strip().lower() if _test_mode_raw else "false"
        self.TEST_MODE = _test_mode_str in ("true", "1", "yes", "on")
        
        # Redis настройки
        self.REDIS_HOST = os.getenv("REDIS_HOST", "redis")
        self.REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
        self.REDIS_DB = int(os.getenv("REDIS_DB", "0"))
        self.REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", None)
        
        # Пароль для команды выдачи безграничной подписки
        self.GRANT_UNLIMITED_PASSWORD = os.getenv("GRANT_UNLIMITED_PASSWORD", "")

config = Config()
