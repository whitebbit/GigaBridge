from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from core.config import config

Base = declarative_base()

DATABASE_URL = (
    f"postgresql+asyncpg://{config.DB_USER}:{config.DB_PASSWORD}"
    f"@{config.DB_HOST}:{config.DB_PORT}/{config.DB_NAME}"
)

# Оптимизированные настройки пула соединений для высокой нагрузки
engine = create_async_engine(
    DATABASE_URL,
    echo=False,  # Отключаем echo в продакшене для производительности
    pool_size=20,  # Размер пула соединений
    max_overflow=40,  # Максимальное количество дополнительных соединений
    pool_pre_ping=True,  # Проверка соединений перед использованием
    pool_recycle=3600,  # Переиспользование соединений каждый час
    connect_args={
        "command_timeout": 30,  # Таймаут команды
        "server_settings": {
            "application_name": "gigabridge_bot",
            "jit": "off",  # Отключаем JIT для быстрых запросов
        }
    }
)
async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
