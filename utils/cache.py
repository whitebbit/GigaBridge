"""
Утилиты для кэширования данных в Redis
"""
import json
from typing import Optional, Any, List
from core.storage import redis_client
from datetime import timedelta


class CacheKeys:
    """Ключи для кэширования"""
    # Локации
    ACTIVE_LOCATIONS = "cache:locations:active"
    LOCATION_BY_ID = "cache:location:{id}"
    
    # Серверы
    ACTIVE_SERVERS = "cache:servers:active"
    SERVERS_BY_LOCATION = "cache:servers:location:{location_id}"
    SERVER_BY_ID = "cache:server:{id}"
    
    # Пользователи
    USER_BY_TG_ID = "cache:user:tg_id:{tg_id}"
    USER_SUBSCRIPTIONS = "cache:user:{user_id}:subscriptions"
    
    # Тарифы
    TARIFF_BY_ID = "cache:tariff:{id}"


class CacheService:
    """Сервис для работы с кэшем"""
    
    @staticmethod
    async def get(key: str) -> Optional[Any]:
        """Получить значение из кэша"""
        try:
            value = await redis_client.get(key)
            if value:
                return json.loads(value)
            return None
        except Exception as e:
            print(f"Ошибка при получении из кэша {key}: {e}")
            return None
    
    @staticmethod
    async def set(key: str, value: Any, ttl: int = 300) -> bool:
        """Установить значение в кэш с TTL (в секундах)"""
        try:
            await redis_client.setex(
                key,
                ttl,
                json.dumps(value, default=str)
            )
            return True
        except Exception as e:
            print(f"Ошибка при установке в кэш {key}: {e}")
            return False
    
    @staticmethod
    async def delete(key: str) -> bool:
        """Удалить значение из кэша"""
        try:
            await redis_client.delete(key)
            return True
        except Exception as e:
            print(f"Ошибка при удалении из кэша {key}: {e}")
            return False
    
    @staticmethod
    async def delete_pattern(pattern: str) -> int:
        """Удалить все ключи по паттерну"""
        try:
            keys = await redis_client.keys(pattern)
            if keys:
                return await redis_client.delete(*keys)
            return 0
        except Exception as e:
            print(f"Ошибка при удалении по паттерну {pattern}: {e}")
            return 0
    
    @staticmethod
    async def invalidate_user_cache(user_id: int):
        """Инвалидировать весь кэш пользователя"""
        patterns = [
            CacheKeys.USER_BY_TG_ID.format(tg_id="*"),
            CacheKeys.USER_SUBSCRIPTIONS.format(user_id=user_id),
        ]
        for pattern in patterns:
            await CacheService.delete_pattern(pattern)
    
    @staticmethod
    async def invalidate_location_cache():
        """Инвалидировать кэш локаций"""
        patterns = [
            CacheKeys.ACTIVE_LOCATIONS,
            CacheKeys.LOCATION_BY_ID.format(id="*"),
        ]
        for pattern in patterns:
            await CacheService.delete_pattern(pattern)
    
    @staticmethod
    async def invalidate_server_cache(server_id: Optional[int] = None, location_id: Optional[int] = None):
        """Инвалидировать кэш серверов"""
        patterns = []
        if server_id:
            patterns.append(CacheKeys.SERVER_BY_ID.format(id=server_id))
        if location_id:
            patterns.append(CacheKeys.SERVERS_BY_LOCATION.format(location_id=location_id))
        patterns.append(CacheKeys.ACTIVE_SERVERS)
        
        for pattern in patterns:
            await CacheService.delete_pattern(pattern)


# Глобальный экземпляр
cache_service = CacheService()

