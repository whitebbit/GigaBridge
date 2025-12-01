"""
Сервис для работы с Hiddify API
"""
import aiohttp
import ssl
import logging
from typing import Optional, Dict, Any
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class HiddifyAPI:
    """Класс для работы с Hiddify API"""
    
    def __init__(self, api_url: str, api_key: str, proxy_path: str = None):
        """
        Инициализация клиента Hiddify API
        
        Args:
            api_url: Базовый URL сервера Hiddify (например, https://89.169.7.60)
            api_key: Hiddify-API-Key (UUID администратора) для аутентификации
            proxy_path: Proxy path из админ-панели Hiddify (например, iewGvZ4ifCI6xh4rU0yJUXH2)
        """
        # Убираем trailing slash если есть
        self.api_url = api_url.rstrip('/')
        self.api_key = api_key
        # Убираем leading/trailing slashes из proxy_path
        self.proxy_path = proxy_path.strip('/') if proxy_path else None
        
        # Формируем базовый URL: {api_url}/{proxy_path} (без /api/v2)
        # Версия API будет добавляться в каждый endpoint
        if self.proxy_path:
            self.base_url = f"{self.api_url}/{self.proxy_path}"
        else:
            self.base_url = self.api_url
        
    async def _make_request(
        self, 
        method: str, 
        endpoint: str, 
        data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Выполняет HTTP запрос к Hiddify API
        
        Args:
            method: HTTP метод (GET, POST, PUT, DELETE)
            endpoint: Конечная точка API (полный путь, например /api/v1/user)
            data: Тело запроса (для POST/PUT)
            params: Параметры запроса (для GET)
            
        Returns:
            Ответ API в виде словаря или None в случае ошибки
        """
        # Формируем полный URL: base_url уже содержит api_url и proxy_path
        # endpoint может быть в формате: {uuid}/api/v2/user/all-configs/ или /api/v2/user/
        # Структура: {api_url}/{proxy_path}/{endpoint}
        # Убираем начальный слеш из endpoint, но сохраняем trailing slash если он есть
        endpoint_clean = endpoint.lstrip('/')
        base_url_clean = self.base_url.rstrip('/')
        # Формируем URL с одним слешем между base_url и endpoint
        url = f"{base_url_clean}/{endpoint_clean}" if endpoint_clean else base_url_clean
        headers = {
            "Hiddify-API-Key": self.api_key,  # Hiddify использует заголовок Hiddify-API-Key вместо Authorization
            "Accept": "application/json",      # Добавляем заголовок Accept как в примере curl
            "Content-Type": "application/json"
        }
        
        # Формируем полный URL с query параметрами для логирования
        full_url_with_params = url
        if params:
            from urllib.parse import urlencode
            query_string = urlencode(params)
            full_url_with_params = f"{url}?{query_string}"
        
        # Логируем запрос (без ключа для безопасности)
        logger.info(f"🌐 Hiddify API Request: {method} {full_url_with_params}")
        logger.info(f"📋 Base URL: {self.base_url}")
        logger.info(f"📋 Original Endpoint: {endpoint}")
        logger.info(f"📋 Final URL: {url}")
        if params:
            logger.info(f"📋 Query Parameters: {params}")
        logger.info(f"📋 API URL: {self.api_url}, Proxy Path: {self.proxy_path}")
        api_key_preview = f"{'*' * (len(self.api_key) - 4) + self.api_key[-4:]}" if len(self.api_key) > 4 else "****"
        logger.info(f"🔑 Hiddify API Headers: Hiddify-API-Key={api_key_preview}, Accept=application/json")
        
        try:
            # Создаем SSL контекст с отключенной проверкой сертификата
            # ВНИМАНИЕ: Это только для тестирования/разработки!
            # В продакшене лучше использовать правильный сертификат
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE
            
            connector = aiohttp.TCPConnector(ssl=ssl_context)
            
            async with aiohttp.ClientSession(connector=connector) as session:
                async with session.request(
                    method=method,
                    url=url,
                    headers=headers,
                    json=data,
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    logger.info(f"📡 Hiddify API Response: {method} {url}")
                    logger.info(f"📊 Status Code: {response.status}")
                    
                    if response.status == 200 or response.status == 201:
                        try:
                            # Пробуем распарсить как JSON
                            content_type = response.headers.get("Content-Type", "").lower()
                            if "application/json" in content_type or "text/json" in content_type:
                                result = await response.json()
                            else:
                                # Если не JSON, читаем как текст
                                result = await response.text()
                        except Exception as json_error:
                            logger.warning(f"Hiddify API: Не удалось распарсить JSON ответ: {json_error}")
                            # Если не удалось распарсить JSON, читаем как текст
                            try:
                                result = await response.text()
                            except:
                                result = None
                        
                        if result:
                            result_preview = str(result)[:500] if not isinstance(result, dict) else str(result)[:200]
                            logger.info(f"Hiddify API {method} {endpoint} - Success: {type(result).__name__} - {result_preview}")
                        return result
                    else:
                        # Для ошибок читаем текст ответа
                        try:
                            response_text = await response.text()
                        except:
                            response_text = "Не удалось прочитать текст ошибки"
                        
                        logger.error(
                            f"❌ Hiddify API {method} {url} - Error {response.status}: {response_text[:500]}"
                        )
                        logger.error(f"🔍 Full URL was: {url}")
                        logger.error(f"🔍 Base URL: {self.base_url}")
                        logger.error(f"🔍 Endpoint: {endpoint}")
                        
                        # Возвращаем словарь с ошибкой вместо None
                        return {"error": True, "status_code": response.status, "message": response_text, "error_type": "api_error"}
                        
        except aiohttp.ClientError as e:
            error_msg = f"Ошибка подключения к Hiddify API: {str(e)}"
            logger.error(f"Hiddify API {method} {endpoint} - Connection error: {e}")
            # Возвращаем словарь с ошибкой вместо None
            return {"error": True, "status_code": None, "message": error_msg, "error_type": "connection"}
        except Exception as e:
            error_msg = f"Неожиданная ошибка при запросе к Hiddify API: {str(e)}"
            logger.error(f"Hiddify API {method} {endpoint} - Unexpected error: {e}")
            import traceback
            logger.error(traceback.format_exc())
            # Возвращаем словарь с ошибкой вместо None
            return {"error": True, "status_code": None, "message": error_msg, "error_type": "unexpected"}
    
    async def create_user(
        self,
        name: str,
        package_days: int = 30,
        traffic: int = 0,  # 0 = безлимит
        note: Optional[str] = None,
        telegram_id: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Создает нового пользователя в Hiddify
        
        Args:
            name: Имя пользователя
            package_days: Количество дней действия подписки (по умолчанию 30)
            traffic: Лимит трафика в GB (0 = безлимит)
            note: Примечание
            telegram_id: Telegram ID пользователя (для связи)
            
        Returns:
            Словарь с данными созданного пользователя или None
        """
        # Формируем данные запроса согласно документации Hiddify API v2
        # Endpoint: POST /api/v2/admin/user
        # Из ошибки 422 видно, что НЕИЗВЕСТНЫЕ поля: note, package_size, resetMod, traffic
        # Используем только известные поля из документации API
        # Согласно ошибке 422:
        # - "name": ["Missing data for required field."] - поле name ОБЯЗАТЕЛЬНО
        # - "username": ["Unknown field."] - поле username НЕИЗВЕСТНО
        # Значит нужно использовать "name", а не "username"
        data = {
            "name": name,  # ✅ Используем name (обязательное поле)
            "package_days": package_days,  # package_days должен быть правильным полем
        }
        
        # Убираем все неизвестные поля из ошибки 422:
        # - package_size ❌
        # - resetMod ❌
        # - traffic ❌
        # - note ❌
        
        # Оставляем только поля, которые не были в списке ошибок
        # comment - попробуем, если не было в списке ошибок
        comment_parts = []
        if note:
            comment_parts.append(note)
        if telegram_id:
            comment_parts.append(f"Telegram ID: {telegram_id}")
        if comment_parts:
            data["comment"] = " | ".join(comment_parts)
        
        # telegram_id - попробуем, если не было в списке ошибок
        if telegram_id:
            data["telegram_id"] = telegram_id
        
        # Пробуем разные варианты путей для создания пользователя
        # URL формируется как: {base_url}/api/v2/{endpoint}, где base_url = {api_url}/{proxy_path}
        # Согласно документации curl: {api_url}/{proxy_path}/api/v2/user/all-configs/
        # Для создания пользователя используем POST на /api/v2/user/
        # Пробуем разные варианты endpoints для создания пользователя
        # Согласно примеру curl: GET /api/v2/user/all-configs/ существует
        # Для POST запроса на создание пользователя могут быть другие пути
        # Правильный endpoint найден: /api/v2/admin/user (вернул 422, значит endpoint правильный)
        endpoints_to_try = [
            "/api/v2/admin/user",     # ✅ Правильный endpoint (вернул 422, значит существует)
        ]
        
        for endpoint in endpoints_to_try:
            logger.info(f"Попытка создать пользователя через POST {endpoint}")
            logger.info(f"📦 Данные запроса: {data}")
            result = await self._make_request("POST", endpoint, data=data)
            if result and not (isinstance(result, dict) and result.get("error")):
                logger.info(f"✅ Пользователь успешно создан через {endpoint}")
                return result
            elif result and isinstance(result, dict):
                error_msg = result.get("message", result.get("msg", "Неизвестная ошибка"))
                status_code = result.get("status_code", 500)
                logger.warning(f"⚠️ Ошибка {status_code} при создании через {endpoint}: {error_msg}")
        
        # Если все попытки не удались, возвращаем последний результат с ошибкой
        return result if result else {"error": True, "message": "Не удалось создать пользователя ни по одному из известных путей API", "error_type": "api_endpoint_not_found"}
    
    async def get_user(self, user_id: int) -> Optional[Dict[str, Any]]:
        """
        Получает информацию о пользователе по ID
        
        Args:
            user_id: ID пользователя в Hiddify
            
        Returns:
            Словарь с данными пользователя или None
        """
        # Пробуем разные варианты путей
        result = await self._make_request("GET", f"/api/v2/user/{user_id}")
        if result and isinstance(result, dict) and result.get("error"):
            result = await self._make_request("GET", f"/api/v1/user/{user_id}")
        if result and isinstance(result, dict) and result.get("error"):
            result = await self._make_request("GET", f"/user/{user_id}")
        return result
    
    async def get_user_subscription(self, user_id: int, user_uuid: str = None) -> Optional[Dict[str, Any]]:
        """
        Получает подписку пользователя (ключ доступа)
        
        Args:
            user_id: ID пользователя в Hiddify
            user_uuid: UUID пользователя (может потребоваться для некоторых endpoints)
            
        Returns:
            Словарь с данными подписки (включая ключ) или None
        """
        # Пробуем разные варианты путей для получения подписки
        # Согласно примеру curl: GET /api/v2/user/all-configs/
        # Это может быть общий endpoint для всех пользователей или нужен ID/UUID
        endpoints_to_try = []
        
        # Сначала пробуем варианты с UUID (UUID из примера curl может быть необязателен)
        if user_uuid:
            endpoints_to_try.extend([
                f"/api/v2/user/{user_uuid}/all-configs/",
                f"/api/v2/user/{user_uuid}/all-configs",
                f"/api/v2/user/{user_uuid}/subscription/",
                f"/api/v2/user/{user_uuid}/subscription",
            ])
        
        # Варианты с ID
        if user_id:
            endpoints_to_try.extend([
                f"/api/v2/user/{user_id}/all-configs/",
                f"/api/v2/user/{user_id}/all-configs",
                f"/api/v2/user/{user_id}/subscription/",
                f"/api/v2/user/{user_id}/subscription",
                f"/api/v1/user/{user_id}/subscription",
                f"/user/{user_id}/subscription",
            ])
        
        # Общий endpoint (может быть для текущего пользователя API ключа)
        endpoints_to_try.extend([
            "/api/v2/user/all-configs/",
            "/api/v2/user/all-configs",
        ])
        
        for endpoint in endpoints_to_try:
            logger.info(f"Попытка получить подписку через {endpoint}")
            result = await self._make_request("GET", endpoint)
            if result and not (isinstance(result, dict) and result.get("error")):
                logger.info(f"✅ Подписка успешно получена через {endpoint}")
                return result
            elif result and isinstance(result, dict) and result.get("error"):
                error_msg = result.get("message", "Неизвестная ошибка")
                status_code = result.get("status_code", 500)
                logger.warning(f"⚠️ Ошибка {status_code} при получении подписки через {endpoint}: {error_msg}")
        
        return None
    
    async def update_user(
        self,
        user_id: int,
        package_days: Optional[int] = None,
        traffic: Optional[int] = None,
        note: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Обновляет данные пользователя
        
        Args:
            user_id: ID пользователя в Hiddify
            package_days: Новое количество дней действия подписки
            traffic: Новый лимит трафика в GB
            note: Новое примечание
            
        Returns:
            Обновленные данные пользователя или None
        """
        data = {}
        if package_days is not None:
            data["package_days"] = package_days
        if traffic is not None:
            data["traffic"] = traffic
        if note is not None:
            data["note"] = note
        
        if not data:
            return None
            
        result = await self._make_request("PUT", f"/api/v2/user/{user_id}", data=data)
        return result
    
    async def delete_user(self, user_id: int) -> bool:
        """
        Удаляет пользователя
        
        Args:
            user_id: ID пользователя в Hiddify
            
        Returns:
            True если успешно, False в противном случае
        """
        result = await self._make_request("DELETE", f"/api/v2/user/{user_id}")
        return result is not None
    
    async def get_all_users(self) -> Optional[list]:
        """
        Получает список всех пользователей
        
        Returns:
            Список пользователей или None
        """
        result = await self._make_request("GET", "/api/v2/user")
        if isinstance(result, list):
            return result
        elif isinstance(result, dict) and "users" in result:
            return result["users"]
        return result


def get_hiddify_client(api_url: str, api_key: str, proxy_path: str = None) -> HiddifyAPI:
    """
    Создает и возвращает клиент Hiddify API
    
    Args:
        api_url: Базовый URL сервера Hiddify (например, https://89.169.7.60)
        api_key: Hiddify-API-Key (UUID администратора)
        proxy_path: Proxy path из админ-панели Hiddify (например, iewGvZ4ifCI6xh4rU0yJUXH2)
        
    Returns:
        Экземпляр HiddifyAPI
    """
    return HiddifyAPI(api_url, api_key, proxy_path)

