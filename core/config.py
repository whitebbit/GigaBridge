from dotenv import load_dotenv
import os

load_dotenv()

class Config:
    BOT_TOKEN = os.getenv("BOT_TOKEN")

    DB_HOST = os.getenv("DB_HOST")
    DB_PORT = os.getenv("DB_PORT")
    DB_NAME = os.getenv("DB_NAME")
    DB_USER = os.getenv("DB_USER")
    DB_PASSWORD = os.getenv("DB_PASSWORD")

    HIDDIFY_API_URL = os.getenv("HIDDIFY_API_URL")
    HIDDIFY_API_KEY = os.getenv("HIDDIFY_API_KEY")
    
    # YooKassa настройки
    YOOKASSA_SHOP_ID = os.getenv("YOOKASSA_SHOP_ID")
    YOOKASSA_SECRET_KEY = os.getenv("YOOKASSA_SECRET_KEY")
    WEBHOOK_URL = os.getenv("WEBHOOK_URL", "")  # URL для webhook от YooKassa
    
    # Настройки скидок
    FIRST_PURCHASE_DISCOUNT_PERCENT = float(os.getenv("FIRST_PURCHASE_DISCOUNT_PERCENT", "20"))  # Процент скидки на первую покупку (по умолчанию 20%)
    
    # Тестовый режим для подписок
    # Если true: подписка создается на 1 минуту, проверка каждую минуту
    # Если false: подписка на 30 дней (из тарифа), проверка каждые 6 часов
    TEST_MODE = os.getenv("TEST_MODE", "false").lower() == "true"
    
    # Redis настройки
    REDIS_HOST = os.getenv("REDIS_HOST", "redis")
    REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
    REDIS_DB = int(os.getenv("REDIS_DB", "0"))
    REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", None)

config = Config()
