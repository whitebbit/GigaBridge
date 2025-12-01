"""
Сервис для работы с 3x-ui API
Полностью переписан на основе test.py
"""
import aiohttp
import ssl
import logging
import json
import uuid as uuid_lib
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class X3UIAPI:
    """Класс для работы с 3x-ui API - основан на test.py"""
    
    def __init__(self, api_url: str, username: str, password: str):
        """
        Инициализация клиента 3x-ui API
        
        Args:
            api_url: Полный URL сервера 3x-ui (например, http://89.169.7.60:30648/rolDT4Th57aiCxNzOi)
            username: Имя пользователя для входа в панель
            password: Пароль для входа в панель
        """
        # Используем URL как есть, БЕЗ парсинга (как в test.py)
        self.api_url = api_url.rstrip('/')
        self.username = username
        self.password = password
        self._session: Optional[aiohttp.ClientSession] = None
        self._authenticated = False
        
    async def _get_session(self) -> aiohttp.ClientSession:
        """Получить или создать сессию с cookies"""
        if self._session is None or self._session.closed:
            # Создаем SSL контекст с отключенной проверкой сертификата
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE
            
            connector = aiohttp.TCPConnector(ssl=ssl_context)
            # Используем CookieJar с unsafe=True для работы с любыми доменами
            cookie_jar = aiohttp.CookieJar(unsafe=True)
            
            self._session = aiohttp.ClientSession(
                connector=connector,
                cookie_jar=cookie_jar,
                timeout=aiohttp.ClientTimeout(total=30)
            )
        return self._session
    
    async def login(self) -> bool:
        """
        Выполняет аутентификацию через /login endpoint (как в test.py)
        
        Returns:
            True если успешно, False в противном случае
        """
        try:
            session = await self._get_session()
            login_url = f"{self.api_url}/login"
            # Используем form-data как в test.py: data=self.data
            login_data = aiohttp.FormData()
            login_data.add_field('username', self.username)
            login_data.add_field('password', self.password)
            
            logger.info(f"🔐 Аутентификация в 3x-ui: {login_url}")
            print(f"\n{'='*80}")
            print(f"🔐 АУТЕНТИФИКАЦИЯ В 3X-UI API:")
            print(f"{'='*80}")
            print(f"📋 Метод: POST")
            print(f"🔗 URL: {login_url}")
            print(f"📋 Данные: username={self.username}, password=****")
            print(f"{'='*80}\n")
            
            async with session.post(login_url, data=login_data) as response:
                print(f"\n{'='*80}")
                print(f"📡 ОТВЕТ НА АУТЕНТИФИКАЦИЮ:")
                print(f"{'='*80}")
                print(f"📊 Status Code: {response.status}")
                print(f"📋 Заголовки ответа:")
                for key, value in response.headers.items():
                    print(f"   {key}: {value}")
                
                # Проверяем cookies после запроса
                # В aiohttp cookies сохраняются автоматически в cookie_jar
                cookies = session.cookie_jar
                cookie_list = list(cookies) if cookies else []
                cookie_count = len(cookie_list)
                print(f"📋 Cookies в сессии после запроса: {cookie_count}")
                if cookie_list:
                    for cookie in cookie_list:
                        print(f"   Cookie: {cookie.key}={cookie.value[:50] if len(cookie.value) > 50 else cookie.value}...")
                
                print(f"{'='*80}\n")
                
                # В test.py проверяется только статус 200
                if response.status == 200:
                    self._authenticated = True
                    logger.info("✅ Аутентификация успешна")
                    print("✅ Аутентификация успешна")
                    return True
                else:
                    response_text = await response.text()
                    logger.error(f"❌ Ошибка аутентификации: {response.status} - {response_text}")
                    print(f"❌ Ошибка аутентификации: {response.status} - {response_text}")
                    return False
        except Exception as e:
            logger.error(f"❌ Ошибка при аутентификации: {e}")
            import traceback
            logger.error(traceback.format_exc())
            print(f"❌ Ошибка при аутентификации: {e}")
            return False
    
    async def get_inbounds(self) -> Optional[List[Dict[str, Any]]]:
        """
        Получает список всех inbounds (как в test.py: /panel/api/inbounds/list)
        
        Returns:
            Список inbounds или None
        """
        # Сначала логинимся (как в test.py - сначала test_connect, потом list)
        if not self._authenticated:
            login_success = await self.login()
            if not login_success:
                return None
        
        session = await self._get_session()
        url = f"{self.api_url}/panel/api/inbounds/list"
        
        # В test.py используется: json=self.data (username и password) - передаем их в JSON
        request_data = {
            "username": self.username,
            "password": self.password
        }
        
        logger.info(f"📋 Получение списка inbounds: {url}")
        print(f"\n{'='*80}")
        print(f"📋 ПОЛУЧЕНИЕ СПИСКА INBOUNDS:")
        print(f"{'='*80}")
        print(f"🔗 URL: {url}")
        print(f"📋 JSON данные: username={self.username}, password=****")
        print(f"{'='*80}\n")
        
        try:
            # В test.py используется GET с json=self.data
            # В requests это работает, но в aiohttp GET не поддерживает json
            # Попробуем сначала GET с data (JSON строка), если не сработает - POST
            import json as json_lib
            json_data = json_lib.dumps(request_data)
            headers = {
                "Accept": "application/json",
                "Content-Type": "application/json"
            }
            
            # Проверяем cookies перед запросом
            cookies_before = list(session.cookie_jar) if session.cookie_jar else []
            print(f"📋 Cookies перед запросом: {len(cookies_before)}")
            if cookies_before:
                for cookie in cookies_before:
                    print(f"   Cookie: {cookie.key}={cookie.value[:30]}...")
            
            # Пробуем GET с data (как в requests)
            async with session.get(url, data=json_data, headers=headers) as response:
                print(f"📊 Status Code: {response.status}")
                response_text = await response.text()
                print(f"📋 Response (первые 500 символов): {response_text[:500]}")
                
                if response.status == 200:
                    try:
                        result = await response.json()
                        print(f"✅ Получен ответ: {type(result).__name__}")
                        if isinstance(result, dict) and "obj" in result:
                            inbounds = result["obj"]
                            print(f"📋 Найдено inbounds: {len(inbounds) if isinstance(inbounds, list) else 0}")
                            return inbounds if isinstance(inbounds, list) else None
                        return result if isinstance(result, list) else None
                    except Exception as json_error:
                        logger.error(f"❌ Ошибка парсинга JSON: {json_error}")
                        print(f"❌ Ошибка парсинга JSON: {json_error}")
                        return None
                elif response.status == 404:
                    # Если GET не работает, пробуем POST (как в других методах API)
                    logger.warning(f"⚠️ GET вернул 404, пробуем POST")
                    print(f"⚠️ GET вернул 404, пробуем POST")
                    async with session.post(url, json=request_data, headers=headers) as response2:
                        print(f"📊 Status Code (POST): {response2.status}")
                        response_text2 = await response2.text()
                        print(f"📋 Response POST (первые 500 символов): {response_text2[:500]}")
                        
                        if response2.status == 200:
                            try:
                                result = await response2.json()
                                print(f"✅ Получен ответ (POST): {type(result).__name__}")
                                if isinstance(result, dict) and "obj" in result:
                                    inbounds = result["obj"]
                                    print(f"📋 Найдено inbounds: {len(inbounds) if isinstance(inbounds, list) else 0}")
                                    return inbounds if isinstance(inbounds, list) else None
                                return result if isinstance(result, list) else None
                            except Exception as json_error:
                                logger.error(f"❌ Ошибка парсинга JSON (POST): {json_error}")
                                print(f"❌ Ошибка парсинга JSON (POST): {json_error}")
                                return None
                        else:
                            logger.error(f"❌ Ошибка получения inbounds (POST): {response2.status} - {response_text2}")
                            print(f"❌ Ошибка (POST): {response2.status} - {response_text2}")
                            return None
                else:
                    logger.error(f"❌ Ошибка получения inbounds: {response.status} - {response_text}")
                    print(f"❌ Ошибка: {response.status} - {response_text}")
                    return None
        except Exception as e:
            logger.error(f"❌ Ошибка при получении inbounds: {e}")
            import traceback
            logger.error(traceback.format_exc())
            print(f"❌ Ошибка: {e}")
            return None
    
    async def add_client(
        self,
        email: str,
        days: int = 30,
        tg_id: Optional[str] = None,
        limit_ip: int = 3,
        total_gb: float = 0.0
    ) -> Optional[Dict[str, Any]]:
        """
        Добавляет клиента к первому доступному inbound (точно как в test.py addClient)
        
        Args:
            email: Email клиента
            days: Количество дней подписки
            tg_id: Telegram ID пользователя (опционально)
            limit_ip: Лимит IP адресов
            total_gb: Лимит трафика в GB (0 = безлимит)
            
        Returns:
            Response объект или None
        """
        # Убеждаемся, что мы аутентифицированы
        if not self._authenticated:
            login_success = await self.login()
            if not login_success:
                return {"error": True, "message": "Ошибка аутентификации", "error_type": "authentication"}
        
        # Получаем список inbounds и используем первый доступный
        inbounds = await self.get_inbounds()
        if not inbounds or len(inbounds) == 0:
            return {"error": True, "message": "На сервере нет доступных inbounds", "error_type": "no_inbounds"}
        
        # Используем первый inbound (как в test.py - там всегда используется id=1)
        inbound = inbounds[0]
        inbound_id = inbound.get("id", 1)
        
        # НЕ задаем expiryTime - бот сам управляет включением/отключением клиента
        # Используем 0 для бессрочной подписки (управление через enable/disable)
        x_time = 0  # Бессрочная подписка, управление через enable/disable
        
        # Генерируем UUID как в test.py
        client_id = str(uuid_lib.uuid4())
        
        # Формируем данные клиента точно как в test.py
        client_data = {
            "id": client_id,
            "alterId": 0,  # В новых версиях обычно 0
            "email": str(email),
            "limitIp": limit_ip,
            "totalGB": 0,  # 0 = безлимитный трафик (согласно документации API 3x-ui)
            "expiryTime": x_time,
            "enable": True,
            "flow": "xtls-rprx-vision",  # Параметр flow для VLESS с XTLS
        }
        
        # Всегда устанавливаем totalGB = 0 для безлимитного трафика
        # (не используем переданный total_gb, чтобы гарантировать отсутствие ограничений)
        
        if tg_id:
            client_data["tgId"] = str(tg_id)
        
        client_data["subId"] = ""  # Как в test.py
        
        # Формируем settings как JSON строку (как в test.py)
        settings = json.dumps({"clients": [client_data]})
        
        # Формируем данные запроса точно как в test.py
        data1 = {
            "id": inbound_id,
            "settings": settings
        }
        
        session = await self._get_session()
        url = f"{self.api_url}/panel/api/inbounds/addClient"
        
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json"
        }
        
        logger.info(f"📝 Добавление клиента: {url}")
        print(f"\n{'='*80}")
        print(f"📝 ДОБАВЛЕНИЕ КЛИЕНТА:")
        print(f"{'='*80}")
        print(f"🔗 URL: {url}")
        print(f"📋 Inbound ID: {inbound_id}")
        print(f"📋 Email: {email}")
        print(f"📋 Days: {days}")
        print(f"📋 Data: {json.dumps(data1, indent=2)}")
        print(f"{'='*80}\n")
        
        try:
            async with session.post(url, headers=headers, json=data1) as response:
                print(f"📊 Status Code: {response.status}")
                response_text = await response.text()
                print(f"📋 Response: {response_text[:500]}")
                
                if response.status == 200 or response.status == 201:
                    try:
                        result = await response.json()
                        # Добавляем client_id в результат, чтобы можно было использовать его позже
                        if isinstance(result, dict):
                            result["client_id"] = client_id  # UUID клиента, который мы создали
                            result["client_email"] = email
                        print(f"✅ Клиент успешно создан")
                        return result
                    except:
                        print(f"✅ Клиент создан (не JSON ответ)")
                        return {"success": True, "status_code": response.status, "client_id": client_id, "client_email": email}
                else:
                    logger.error(f"❌ Ошибка создания клиента: {response.status} - {response_text}")
                    print(f"❌ Ошибка: {response.status} - {response_text}")
                    return {"error": True, "status_code": response.status, "message": response_text, "error_type": "api_error"}
        except Exception as e:
            logger.error(f"❌ Ошибка при создании клиента: {e}")
            import traceback
            logger.error(traceback.format_exc())
            print(f"❌ Ошибка: {e}")
            return {"error": True, "status_code": None, "message": str(e), "error_type": "unexpected"}
    
    async def update_client(
        self,
        client_email: str,
        enable: bool = None,
        days: int = None
    ) -> Optional[Dict[str, Any]]:
        """
        Обновляет клиента (включение/отключение или продление)
        
        Args:
            client_email: Email клиента
            enable: Включить (True) или отключить (False) клиента. Если None - не меняем
            days: Количество дней для продления (опционально)
            
        Returns:
            Response объект или None
        """
        # Убеждаемся, что мы аутентифицированы
        if not self._authenticated:
            login_success = await self.login()
            if not login_success:
                return {"error": True, "message": "Ошибка аутентификации", "error_type": "authentication"}
        
        # Получаем клиента по email
        client = await self.get_client_by_email(client_email)
        if not client:
            return {"error": True, "message": f"Клиент с email {client_email} не найден", "error_type": "client_not_found"}
        
        client_id = client.get("id")
        inbound_id = client.get("inbound_id")
        if not client_id or not inbound_id:
            return {"error": True, "message": "Не удалось получить ID клиента или inbound", "error_type": "invalid_client"}
        
        # Получаем текущие данные клиента
        inbounds = await self.get_inbounds()
        if not inbounds:
            return {"error": True, "message": "Не удалось получить список inbounds", "error_type": "no_inbounds"}
        
        inbound = None
        for inv in inbounds:
            if inv.get("id") == inbound_id:
                inbound = inv
                break
        
        if not inbound:
            return {"error": True, "message": f"Inbound {inbound_id} не найден", "error_type": "inbound_not_found"}
        
        # Парсим settings для получения текущих данных клиента
        settings_str = inbound.get("settings", "{}")
        try:
            settings = json.loads(settings_str) if isinstance(settings_str, str) else settings_str
            clients = settings.get("clients", [])
            
            logger.info(f"🔍 Поиск клиента {client_email} в {len(clients)} клиентах inbound {inbound_id}")
            
            # Находим клиента в списке
            current_client_data = None
            for c in clients:
                if c.get("email") == client_email:
                    current_client_data = c.copy()
                    logger.info(f"✅ Клиент найден: id={current_client_data.get('id')}, enable={current_client_data.get('enable')}")
                    break
            
            if not current_client_data:
                logger.error(f"❌ Клиент {client_email} не найден в настройках inbound {inbound_id}")
                logger.error(f"   Доступные клиенты: {[c.get('email') for c in clients]}")
                return {"error": True, "message": "Клиент не найден в настройках inbound", "error_type": "client_not_found"}
        except (json.JSONDecodeError, TypeError) as e:
            logger.error(f"❌ Ошибка парсинга settings: {e}")
            logger.error(f"   Settings string: {settings_str[:200]}...")
            return {"error": True, "message": f"Ошибка парсинга settings: {e}", "error_type": "parse_error"}
        
        # Обновляем данные клиента
        if enable is not None:
            logger.info(f"🔄 Обновление enable: {current_client_data.get('enable')} -> {enable}")
            current_client_data["enable"] = enable
        
        # Если нужно продлить подписку
        if days is not None and days > 0:
            # Вычисляем новое время истечения
            epoch = datetime.utcfromtimestamp(0)
            current_time = int((datetime.utcnow() - epoch).total_seconds() * 1000.0)
            
            # Если у клиента уже есть expiryTime и он не истек, продлеваем от текущего времени
            if current_client_data.get("expiryTime", 0) > current_time:
                # Продлеваем от текущего времени истечения
                x_time = current_client_data.get("expiryTime", current_time)
                x_time += 86400000 * days - 10800000
            else:
                # Создаем новое время от текущего момента
                x_time = current_time + 86400000 * days - 10800000
            
            current_client_data["expiryTime"] = x_time
            # При продлении автоматически включаем клиента
            current_client_data["enable"] = True
        
        # Сохраняем ВСЕ поля клиента из исходных данных (важно для правильной работы API)
        # Убеждаемся, что все необходимые поля присутствуют согласно шаблону
        # Формат должен быть точно как в примере curl
        
        # Обязательные поля (если их нет, устанавливаем значения по умолчанию)
        if "limitIp" not in current_client_data:
            current_client_data["limitIp"] = 0
        if "totalGB" not in current_client_data:
            current_client_data["totalGB"] = 0
        if "expiryTime" not in current_client_data:
            current_client_data["expiryTime"] = 0
        if "flow" not in current_client_data:
            current_client_data["flow"] = ""
        if "subId" not in current_client_data:
            current_client_data["subId"] = ""
        if "tgId" not in current_client_data:
            current_client_data["tgId"] = 0
        if "comment" not in current_client_data:
            current_client_data["comment"] = ""
        if "reset" not in current_client_data:
            current_client_data["reset"] = 0
        
        # Сохраняем временные метки, если они есть
        if "created_at" not in current_client_data:
            # Если нет created_at, устанавливаем текущее время
            epoch = datetime.utcfromtimestamp(0)
            current_client_data["created_at"] = int((datetime.utcnow() - epoch).total_seconds() * 1000.0)
        
        # Всегда обновляем updated_at
        epoch = datetime.utcfromtimestamp(0)
        current_client_data["updated_at"] = int((datetime.utcnow() - epoch).total_seconds() * 1000.0)
        
        # Удаляем alterId, если он есть (в новом формате его нет)
        if "alterId" in current_client_data:
            del current_client_data["alterId"]
        
        logger.info(f"📋 Финальные данные клиента перед отправкой:")
        logger.info(f"   id: {current_client_data.get('id')}")
        logger.info(f"   email: {current_client_data.get('email')}")
        logger.info(f"   enable: {current_client_data.get('enable')}")
        logger.info(f"   flow: {current_client_data.get('flow')}")
        logger.info(f"   limitIp: {current_client_data.get('limitIp')}")
        logger.info(f"   totalGB: {current_client_data.get('totalGB')}")
        logger.info(f"   expiryTime: {current_client_data.get('expiryTime')}")
        logger.info(f"   tgId: {current_client_data.get('tgId')}")
        logger.info(f"   subId: {current_client_data.get('subId')}")
        logger.info(f"   comment: {current_client_data.get('comment')}")
        logger.info(f"   reset: {current_client_data.get('reset')}")
        logger.info(f"   created_at: {current_client_data.get('created_at')}")
        logger.info(f"   updated_at: {current_client_data.get('updated_at')}")
        
        # Логируем все ключи для отладки
        logger.info(f"📋 Все ключи клиента: {list(current_client_data.keys())}")
        
        # ВАЖНО: В test.py и curl примере отправляется только ОДИН клиент в массиве!
        # Не все клиенты, а только обновляемый клиент
        # Формируем settings с ТОЛЬКО обновляемым клиентом (как в test.py)
        settings_dict = {"clients": [current_client_data]}
        settings = json.dumps(settings_dict, ensure_ascii=False)
        logger.info(f"📦 Settings JSON (только обновляемый клиент): {settings[:500]}...")
        logger.info(f"📊 Отправляем только 1 клиента (как в test.py)")
        
        # Формируем данные запроса точно как в примере curl
        data1 = {
            "id": inbound_id,
            "settings": settings  # Это должна быть JSON строка, а не объект!
        }
        
        session = await self._get_session()
        url = f"{self.api_url}/panel/api/inbounds/updateClient/{client_id}"
        
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json"
        }
        
        logger.info(f"📝 Обновление клиента: {url}")
        logger.info(f"   Email: {client_email}, Enable: {enable}, Days: {days}")
        logger.info(f"   Client ID: {client_id}, Inbound ID: {inbound_id}")
        logger.info(f"   Request data: id={data1['id']}, settings length={len(data1['settings'])}")
        
        try:
            async with session.post(url, headers=headers, json=data1) as response:
                response_text = await response.text()
                logger.info(f"📡 Ответ от API: status={response.status}, text={response_text[:200]}...")
                
                if response.status == 200 or response.status == 201:
                    try:
                        result = await response.json()
                        logger.info(f"✅ Клиент успешно обновлен: {result}")
                        return result
                    except Exception as json_error:
                        logger.warning(f"⚠️ Не удалось распарсить JSON ответ: {json_error}")
                        logger.info(f"✅ Клиент обновлен (не JSON ответ), status: {response.status}")
                        return {"success": True, "status_code": response.status, "message": response_text}
                else:
                    logger.error(f"❌ Ошибка обновления клиента: {response.status}")
                    logger.error(f"   Response text: {response_text}")
                    logger.error(f"   Request URL: {url}")
                    logger.error(f"   Request data: {json.dumps(data1, indent=2)[:500]}...")
                    return {"error": True, "status_code": response.status, "message": response_text, "error_type": "api_error"}
        except Exception as e:
            logger.error(f"❌ Ошибка при обновлении клиента: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return {"error": True, "status_code": None, "message": str(e), "error_type": "unexpected"}
    
    async def enable_client(self, client_email: str) -> Optional[Dict[str, Any]]:
        """Включить клиента"""
        logger.info(f"🔄 Включение клиента: {client_email}")
        result = await self.update_client(client_email, enable=True)
        
        # Если обновление прошло успешно, считаем что клиент включен
        # Проверка состояния может быть неточной из-за кэширования на стороне API
        if result and not result.get("error"):
            logger.info(f"✅ Клиент {client_email} включен (ответ API успешен)")
            return result
        else:
            return result
    
    async def disable_client(self, client_email: str) -> Optional[Dict[str, Any]]:
        """Отключить клиента"""
        logger.info(f"🔄 Отключение клиента: {client_email}")
        result = await self.update_client(client_email, enable=False)
        
        # Если обновление прошло успешно, считаем что клиент отключен
        # Проверка состояния может быть неточной из-за кэширования на стороне API
        if result and not result.get("error"):
            logger.info(f"✅ Клиент {client_email} отключен (ответ API успешен)")
            return result
        else:
            return result
    
    async def get_inbound_by_id(self, inbound_id: int) -> Optional[Dict[str, Any]]:
        """
        Получает информацию о inbound по ID
        
        Args:
            inbound_id: ID inbound
            
        Returns:
            Словарь с данными inbound или None
        """
        inbounds = await self.get_inbounds()
        if not inbounds:
            return None
        
        for inbound in inbounds:
            if isinstance(inbound, dict) and inbound.get("id") == inbound_id:
                return inbound
        
        return None
    
    async def get_client_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        """
        Получает клиента по email из первого доступного inbound
        
        Args:
            email: Email клиента
            
        Returns:
            Словарь с данными клиента и inbound_id или None
        """
        inbounds = await self.get_inbounds()
        if not inbounds:
            return None
        
        # Ищем клиента во всех inbounds
        for inbound in inbounds:
            inbound_id = inbound.get("id")
            if not inbound_id:
                continue
            
            # Парсим settings из JSON строки
            settings_str = inbound.get("settings", "{}")
            try:
                settings = json.loads(settings_str) if isinstance(settings_str, str) else settings_str
                clients = settings.get("clients", [])
                
                for client in clients:
                    if client.get("email") == email:
                        # Возвращаем клиента с информацией о inbound_id
                        result = client.copy()
                        result["inbound_id"] = inbound_id
                        return result
            except (json.JSONDecodeError, TypeError):
                continue
        
        return None
    
    async def get_client_vless_link(
        self,
        client_email: str,
        client_username: str = None,
        server_pbk: str = None
    ) -> Optional[str]:
        """
        Генерирует VLESS ключ для клиента по шаблону:
        vless://{user_id}@{IP}:{PORT}?type=tcp&encryption=none&security=reality&pbk={PBK}&fp=chrome&sni=www.microsoft.com&sid={SID}&spx=%2F&flow=xtls-rprx-vision#{USERNAME}
        
        Args:
            client_email: Email клиента
            client_username: Username клиента (для отображения в конце ссылки)
            
        Returns:
            VLESS ссылка или None
        """
        client = await self.get_client_by_email(client_email)
        if not client:
            return None
        
        # Получаем client_id (UUID) и inbound_id
        client_id = client.get("id")
        inbound_id = client.get("inbound_id")
        if not client_id or not inbound_id:
            return None
        
        # Получаем данные inbound для получения настроек потока
        inbounds = await self.get_inbounds()
        if not inbounds:
            return None
        
        inbound = None
        for inv in inbounds:
            if inv.get("id") == inbound_id:
                inbound = inv
                break
        
        if not inbound:
            return None
        
        # Получаем порт из inbound
        port = inbound.get("port")
        if not port:
            return None
        
        # Парсим streamSettings для получения параметров Reality
        stream_settings_str = inbound.get("streamSettings", "{}")
        try:
            stream_settings = json.loads(stream_settings_str) if isinstance(stream_settings_str, str) else stream_settings_str
        except (json.JSONDecodeError, TypeError) as e:
            logger.error(f"❌ Ошибка парсинга streamSettings: {e}")
            return None
        
        # Получаем параметры сети и безопасности
        network = stream_settings.get("network", "tcp")
        security = stream_settings.get("security", "reality")
        
        # Получаем параметры Reality из realitySettings
        reality_settings = stream_settings.get("realitySettings", {})
        
        # Используем PBK из сервера (переданный параметр)
        pbk = server_pbk or ""
        
        if not pbk:
            logger.warning("⚠️ PBK не передан из сервера. Убедитесь, что PBK установлен в настройках сервера.")
        # Получаем остальные параметры Reality
        if not reality_settings:
            reality_settings = stream_settings
        
        sid_list = (reality_settings.get("shortIds") or 
                   reality_settings.get("shortId") or 
                   reality_settings.get("shortids") or
                   stream_settings.get("shortIds") or
                   stream_settings.get("shortId") or [])
        if isinstance(sid_list, str):
            sid_list = [sid_list]
        sid_str = sid_list[0] if sid_list and len(sid_list) > 0 else ""
        
        sni = (reality_settings.get("serverName") or 
              reality_settings.get("sni") or 
              reality_settings.get("serverName") or
              stream_settings.get("serverName") or
              stream_settings.get("sni") or 
              "www.microsoft.com")
        
        spx = (reality_settings.get("spiderX") or 
              reality_settings.get("spx") or
              stream_settings.get("spiderX") or
              stream_settings.get("spx") or 
              "/")
        
        # URL-кодируем spx если нужно (должно быть %2F для /)
        if spx == "/":
            spx = "%2F"
        elif spx and not spx.startswith("%"):
            from urllib.parse import quote
            spx = quote(spx, safe='')
        
        # Логируем полученные параметры для отладки
        logger.info(f"📋 Параметры для VLESS ключа:")
        logger.info(f"   Network: {network}, Security: {security}")
        logger.info(f"   PBK: {pbk[:20] if pbk else 'N/A'}..., SID: {sid_str}, SNI: {sni}, SPX: {spx}")
        
        # Проверяем, что все необходимые параметры есть
        if not pbk:
            logger.warning("⚠️ PBK (publicKey) не найден в настройках Reality")
        if not sid_str:
            logger.warning("⚠️ SID (shortId) не найден в настройках Reality")
        
        # Получаем IP адрес из api_url (извлекаем домен/IP)
        try:
            from urllib.parse import urlparse
            parsed_url = urlparse(self.api_url)
            server_ip = parsed_url.hostname or parsed_url.netloc.split(':')[0]
        except:
            # Если не удалось распарсить, используем дефолтное значение
            server_ip = "vpn-x3.ru"  # Fallback
        
        # Формируем VLESS ссылку по шаблону
        # vless://{user_id}@{IP}:{PORT}?type=tcp&encryption=none&security=reality&pbk={PBK}&fp=chrome&sni=www.microsoft.com&sid={SID}&spx=%2F&flow=xtls-rprx-vision#{USERNAME}
        # Используем уникальный email (который уже содержит уникальный ID) для отображения
        username_display = client_email  # Всегда используем уникальный email
        
        vless_link = (
            f"vless://{client_id}@{server_ip}:{port}"
            f"?type={network}&encryption=none&security={security}"
            f"&pbk={pbk}&fp=chrome&sni={sni}&sid={sid_str}&spx={spx}"
            f"&flow=xtls-rprx-vision#{username_display}"
        )
        
        return vless_link
    
    async def get_client_subscription_link(
        self,
        client_email: str
    ) -> Optional[str]:
        """
        Получает VLESS ссылку для клиента (алиас для get_client_vless_link для обратной совместимости)
        
        Args:
            client_email: Email клиента
            
        Returns:
            VLESS ссылка или None
        """
        return await self.get_client_vless_link(client_email)
    
    async def delete_client(self, client_email: str) -> Optional[Dict[str, Any]]:
        """
        Удаляет клиента из 3x-ui
        
        Args:
            client_email: Email клиента для удаления
            
        Returns:
            Response объект или None
        """
        # Убеждаемся, что мы аутентифицированы
        if not self._authenticated:
            login_success = await self.login()
            if not login_success:
                return {"error": True, "message": "Ошибка аутентификации", "error_type": "authentication"}
        
        # Получаем клиента по email
        client = await self.get_client_by_email(client_email)
        if not client:
            return {"error": True, "message": f"Клиент с email {client_email} не найден", "error_type": "client_not_found"}
        
        client_id = client.get("id")
        inbound_id = client.get("inbound_id")
        if not client_id or not inbound_id:
            return {"error": True, "message": "Не удалось получить ID клиента или inbound", "error_type": "invalid_client"}
        
        # Получаем текущие данные inbound
        inbounds = await self.get_inbounds()
        if not inbounds:
            return {"error": True, "message": "Не удалось получить список inbounds", "error_type": "no_inbounds"}
        
        inbound = None
        for inv in inbounds:
            if inv.get("id") == inbound_id:
                inbound = inv
                break
        
        if not inbound:
            return {"error": True, "message": f"Inbound {inbound_id} не найден", "error_type": "inbound_not_found"}
        
        # Парсим settings для получения текущих данных клиентов
        settings_str = inbound.get("settings", "{}")
        try:
            settings = json.loads(settings_str) if isinstance(settings_str, str) else settings_str
            clients = settings.get("clients", [])
            
            logger.info(f"🔍 Поиск клиента {client_email} для удаления в {len(clients)} клиентах inbound {inbound_id}")
            
            # Удаляем клиента из списка
            updated_clients = [c for c in clients if c.get("email") != client_email]
            
            if len(updated_clients) == len(clients):
                logger.error(f"❌ Клиент {client_email} не найден в настройках inbound {inbound_id}")
                return {"error": True, "message": "Клиент не найден в настройках inbound", "error_type": "client_not_found"}
            
            logger.info(f"✅ Клиент {client_email} найден, будет удален из {len(clients)} клиентов (останется {len(updated_clients)})")
            
            # ВАЖНО: Сохраняем ВСЕ настройки из settings, обновляя только список clients
            # Это гарантирует, что мы не потеряем другие настройки inbound
            updated_settings = settings.copy()
            updated_settings["clients"] = updated_clients
            
            # Преобразуем обратно в JSON строку
            settings_json = json.dumps(updated_settings, ensure_ascii=False)
            logger.info(f"📦 Settings JSON (без удаленного клиента): {len(updated_clients)} клиентов, сохранены все настройки")
            
        except (json.JSONDecodeError, TypeError) as e:
            logger.error(f"❌ Ошибка парсинга settings: {e}")
            logger.error(f"   Settings string: {settings_str[:200]}...")
            return {"error": True, "message": f"Ошибка парсинга settings: {e}", "error_type": "parse_error"}
        
        # Формируем данные запроса для обновления inbound
        # ВАЖНО: Передаем все поля inbound, чтобы не потерять другие настройки
        # Копируем все поля из inbound и обновляем только settings
        data1 = inbound.copy()
        data1["settings"] = settings_json  # JSON строка со всеми настройками, включая обновленный список clients
        data1["id"] = inbound_id  # Убеждаемся, что ID правильный
        
        session = await self._get_session()
        url = f"{self.api_url}/panel/api/inbounds/update/{inbound_id}"
        
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json"
        }
        
        logger.info(f"🗑️ Удаление клиента: {url}")
        logger.info(f"   Email: {client_email}")
        logger.info(f"   Client ID: {client_id}, Inbound ID: {inbound_id}")
        logger.info(f"   Request data: id={data1['id']}, settings length={len(data1['settings'])}")
        
        try:
            async with session.post(url, headers=headers, json=data1) as response:
                response_text = await response.text()
                logger.info(f"📡 Ответ от API: status={response.status}, text={response_text[:200]}...")
                
                if response.status == 200 or response.status == 201:
                    try:
                        result = await response.json()
                        logger.info(f"✅ Клиент {client_email} успешно удален: {result}")
                        return result
                    except Exception as json_error:
                        logger.warning(f"⚠️ Не удалось распарсить JSON ответ: {json_error}")
                        logger.info(f"✅ Клиент удален (не JSON ответ), status: {response.status}")
                        return {"success": True, "status_code": response.status, "message": response_text}
                else:
                    logger.error(f"❌ Ошибка удаления клиента: {response.status}")
                    logger.error(f"   Response text: {response_text}")
                    logger.error(f"   Request URL: {url}")
                    logger.error(f"   Request data: {json.dumps(data1, indent=2)[:500]}...")
                    return {"error": True, "status_code": response.status, "message": response_text, "error_type": "api_error"}
        except Exception as e:
            logger.error(f"❌ Ошибка при удалении клиента: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return {"error": True, "status_code": None, "message": str(e), "error_type": "unexpected"}
    
    async def close(self):
        """Закрыть сессию"""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None
            self._authenticated = False


def get_x3ui_client(api_url: str, username: str, password: str) -> X3UIAPI:
    """
    Создает и возвращает клиент 3x-ui API
    
    Args:
        api_url: Полный URL сервера 3x-ui (может содержать WebBasePath)
        username: Имя пользователя для входа в панель
        password: Пароль для входа в панель
        
    Returns:
        Экземпляр X3UIAPI
    """
    return X3UIAPI(api_url, username, password)
