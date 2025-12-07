"""
Настройка подключения к базе данных PostgreSQL
Оптимизировано для высокой нагрузки и стабильности
"""
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from core.config import config
from utils.logger import logger

Base = declarative_base()

DATABASE_URL = (
    f"postgresql+asyncpg://{config.DB_USER}:{config.DB_PASSWORD}"
    f"@{config.DB_HOST}:{config.DB_PORT}/{config.DB_NAME}"
)

# Оптимизированные настройки пула соединений для высокой нагрузки
try:
    engine = create_async_engine(
        DATABASE_URL,
        echo=False,  # Отключаем echo в продакшене для производительности
        pool_size=30,  # Увеличенный размер пула соединений для высокой нагрузки
        max_overflow=50,  # Максимальное количество дополнительных соединений
        pool_pre_ping=True,  # Проверка соединений перед использованием
        pool_recycle=3600,  # Переиспользование соединений каждый час
        pool_timeout=30,  # Таймаут ожидания свободного соединения из пула (секунды)
        connect_args={
            "command_timeout": 30,  # Таймаут команды SQL
            "server_settings": {
                "application_name": "gigabridge_bot",
                "jit": "off",  # Отключаем JIT для быстрых запросов
                "statement_timeout": "30000",  # 30 секунд таймаут для запросов
                "lock_timeout": "10000",  # 10 секунд таймаут для блокировок
            }
        }
    )
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    logger.info("Database engine initialized successfully")
except Exception as e:
    logger.error(f"Failed to initialize database engine: {e}")
    raise
