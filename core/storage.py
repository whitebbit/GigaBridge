"""
Настройка хранилищ для FSM и других данных
Оптимизировано с обработкой ошибок и retry механизмами
"""
from aiogram.fsm.storage.redis import RedisStorage
from core.config import config
import redis.asyncio as redis
from utils.logger import logger
import asyncio


def get_redis_client() -> redis.Redis:
    """Получить клиент Redis для прямого доступа с оптимизированными настройками"""
    return redis.Redis(
        host=config.REDIS_HOST,
        port=config.REDIS_PORT,
        db=config.REDIS_DB,
        password=config.REDIS_PASSWORD,
        decode_responses=True,
        socket_connect_timeout=5,
        socket_timeout=5,
        retry_on_timeout=True,
        health_check_interval=30,
        max_connections=50
    )


def get_fsm_storage() -> RedisStorage:
    """Получить хранилище FSM на основе Redis с обработкой ошибок"""
    try:
        # Формируем URL с паролем, если он указан
        if config.REDIS_PASSWORD:
            redis_url = f"redis://:{config.REDIS_PASSWORD}@{config.REDIS_HOST}:{config.REDIS_PORT}/{config.REDIS_DB}"
        else:
            redis_url = f"redis://{config.REDIS_HOST}:{config.REDIS_PORT}/{config.REDIS_DB}"
        
        return RedisStorage.from_url(redis_url)
    except Exception as e:
        logger.error(f"Failed to create Redis storage: {e}")
        raise


# Создаем глобальные экземпляры с обработкой ошибок
try:
    redis_client = get_redis_client()
    fsm_storage = get_fsm_storage()
except Exception as e:
    logger.error(f"Failed to initialize Redis client/storage: {e}")
    # В случае ошибки создаем заглушки, чтобы приложение могло запуститься
    # но будет логировать ошибки при использовании
    redis_client = None
    fsm_storage = None

