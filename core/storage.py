"""
Настройка хранилищ для FSM и других данных
"""
from aiogram.fsm.storage.redis import RedisStorage
from core.config import config
import redis.asyncio as redis


def get_redis_client() -> redis.Redis:
    """Получить клиент Redis для прямого доступа"""
    return redis.Redis(
        host=config.REDIS_HOST,
        port=config.REDIS_PORT,
        db=config.REDIS_DB,
        password=config.REDIS_PASSWORD,
        decode_responses=True
    )


def get_fsm_storage() -> RedisStorage:
    """Получить хранилище FSM на основе Redis"""
    # Формируем URL с паролем, если он указан
    if config.REDIS_PASSWORD:
        redis_url = f"redis://:{config.REDIS_PASSWORD}@{config.REDIS_HOST}:{config.REDIS_PORT}/{config.REDIS_DB}"
    else:
        redis_url = f"redis://{config.REDIS_HOST}:{config.REDIS_PORT}/{config.REDIS_DB}"
    
    return RedisStorage.from_url(redis_url)


# Создаем глобальные экземпляры
redis_client = get_redis_client()
fsm_storage = get_fsm_storage()

