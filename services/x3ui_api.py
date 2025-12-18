"""
Сервис для работы с 3x-ui API
Полностью переписан на основе test.py
"""
import aiohttp
import ssl
import logging
import json
import uuid as uuid_lib
import asyncio
import os
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
from core.config import config

logger = logging.getLogger(__name__)


class X3UIAPI:
    """Класс для работы с 3x-ui API - основан на test.py"""
    
    def __init__(self, api_url: str, username: str, password: str, ssl_certificate: Optional[str] = None):
        """
        Инициализация клиента 3x-ui API
        
        Args:
            api_url: Полный URL сервера 3x-ui (например, http://89.169.7.60:30648/rolDT4Th57aiCxNzOi)
            username: Имя пользователя для входа в панель
            password: Пароль для входа в панель
            ssl_certificate: SSL сертификат в формате PEM (опционально)
        """
        # Используем URL как есть, БЕЗ парсинга (как в test.py)
        self.api_url = api_url.rstrip('/')
        self.username = username
        self.password = password
        self.ssl_certificate = ssl_certificate
        self._session: Optional[aiohttp.ClientSession] = None
        self._authenticated = False
        self._cert_file_path: Optional[str] = None  # Путь к файлу сертификата
        
    async def _get_session(self) -> aiohttp.ClientSession:
        """Получить или создать сессию с cookies"""
        if self._session is None or self._session.closed:
            # Проверяем, используется ли HTTPS
            use_https = self.api_url.startswith('https://')
            
            # Инициализируем SSL контекст и путь к сертификату
            ssl_context = None
            cert_file_path = None
            
            # ВСЕГДА используем сертификат, если он указан (независимо от протокола)
            if self.ssl_certificate:
                # Создаем временный файл сертификата из БД
                import tempfile
                
                try:
                    # Создаем временный файл сертификата
                    temp_file = tempfile.NamedTemporaryFile(mode='w', suffix='.crt', delete=False)
                    temp_file.write(self.ssl_certificate)
                    temp_file.close()
                    cert_file_path = temp_file.name
                    logger.info(f"🔒 SSL сертификат сохранен во временный файл: {cert_file_path}")
                except Exception as e:
                    logger.error(f"❌ Ошибка при создании временного файла сертификата: {e}")
                    cert_file_path = None
                
                if cert_file_path:
                    try:
                        # Используем правильный подход: создаем контекст с cafile
                        if use_https:
                            ssl_context = ssl.create_default_context(cafile=cert_file_path)
                            # Отключаем проверку hostname для работы с IP-адресами
                            # Сертификат может быть выдан для домена, но подключение идет по IP
                            ssl_context.check_hostname = False
                        else:
                            # Для HTTP тоже создаем контекст с сертификатом (может быть нужен для mTLS)
                            ssl_context = ssl.create_default_context()
                            ssl_context.load_verify_locations(cert_file_path)
                            ssl_context.check_hostname = False
                            ssl_context.verify_mode = ssl.CERT_REQUIRED
                        
                        logger.info(f"🔒 SSL контекст создан с сертификатом: {cert_file_path}")
                        logger.info(f"🔒 Протокол: {'HTTPS' if use_https else 'HTTP'}")
                        logger.info(f"🔒 Проверка hostname: {ssl_context.check_hostname}, verify_mode: {ssl_context.verify_mode}")
                        
                        # Сохраняем путь к файлу для последующего использования
                        self._cert_file_path = cert_file_path
                    except Exception as e:
                        logger.error(f"❌ Ошибка при создании SSL контекста с сертификатом: {e}")
                        import traceback
                        logger.error(traceback.format_exc())
                        # В случае ошибки создаем контекст без проверки
                        ssl_context = ssl.create_default_context()
                        ssl_context.check_hostname = False
                        ssl_context.verify_mode = ssl.CERT_NONE
                        self._cert_file_path = None
                else:
                    logger.warning("⚠️ Не удалось создать файл сертификата, используем стандартный контекст")
                    if use_https:
                        ssl_context = ssl.create_default_context()
                    else:
                        ssl_context = False
                    ssl_context.check_hostname = False if ssl_context else None
                    ssl_context.verify_mode = ssl.CERT_NONE if ssl_context else None
                    self._cert_file_path = None
            elif use_https:
                # HTTPS без сертификата - используем стандартную проверку
                ssl_context = ssl.create_default_context()
                logger.debug("⚠️ HTTPS без сертификата, используется стандартная проверка")
                self._cert_file_path = None
            else:
                # HTTP - SSL не нужен
                ssl_context = False
                logger.debug("⚠️ HTTP соединение, SSL не используется")
                self._cert_file_path = None
            
            # Создаем connector с SSL контекстом
            connector = aiohttp.TCPConnector(ssl=ssl_context)
            # Используем CookieJar с unsafe=True для работы с любыми доменами
            cookie_jar = aiohttp.CookieJar(unsafe=True)
            
            self._session = aiohttp.ClientSession(
                connector=connector,
                cookie_jar=cookie_jar,
                timeout=aiohttp.ClientTimeout(total=60, connect=30),  # Увеличиваем таймауты: общий 60с, подключение 30с
                # Включаем автоматическое следование редиректам
                raise_for_status=False  # Не поднимаем исключение автоматически, обрабатываем вручную
            )
        return self._session
    
    async def login(self, max_retries: int = 3) -> bool:
        """
        Выполняет аутентификацию через /login endpoint (как в test.py)
        С повторными попытками при сетевых ошибках.
        
        Args:
            max_retries: Максимальное количество попыток (по умолчанию 3)
        
        Returns:
            True если успешно, False в противном случае
        """
        last_error = None
        
        for attempt in range(1, max_retries + 1):
            try:
                session = await self._get_session()
                login_url = f"{self.api_url}/login"
                # Используем form-data как в test.py: data=self.data
                login_data = aiohttp.FormData()
                login_data.add_field('username', self.username)
                login_data.add_field('password', self.password)
                
                if attempt > 1:
                    logger.info(f"🔄 Попытка аутентификации {attempt}/{max_retries}...")
                elif config.TEST_MODE:
                    logger.debug(f"3x-ui authentication: {login_url}")
                
                try:
                    # Разрешаем редиректы и увеличиваем лимит редиректов
                    # ВСЕГДА передаем SSL контекст в запрос, если есть сертификат
                    ssl_for_request = None
                    if self._cert_file_path:
                        # Используем тот же SSL контекст, что и в сессии
                        use_https = self.api_url.startswith('https://')
                        if use_https:
                            ssl_for_request = ssl.create_default_context(cafile=self._cert_file_path)
                            # Отключаем проверку hostname для работы с IP-адресами
                            ssl_for_request.check_hostname = False
                        else:
                            # Для HTTP тоже создаем контекст с сертификатом
                            ssl_for_request = ssl.create_default_context()
                            ssl_for_request.load_verify_locations(self._cert_file_path)
                            ssl_for_request.check_hostname = False
                            ssl_for_request.verify_mode = ssl.CERT_REQUIRED
                        if config.TEST_MODE:
                            logger.debug(f"SSL context created: {self._cert_file_path}")
                    
                    async with session.post(
                        login_url, 
                        data=login_data,
                        allow_redirects=True,  # Разрешаем автоматическое следование редиректам
                        max_redirects=10,  # Максимальное количество редиректов
                        ssl=ssl_for_request  # Передаем SSL контекст в запрос
                    ) as response:
                        # Проверяем статус ответа (200, 201, 302, 307 - все могут быть успешными)
                        if response.status in [200, 201]:
                            self._authenticated = True
                            if attempt > 1:
                                logger.info(f"✅ Аутентификация успешна после {attempt} попыток")
                            elif config.TEST_MODE:
                                logger.debug("Authentication successful")
                            return True
                        elif response.status in [302, 307, 308]:
                            # Редирект - это нормально, проверяем cookies
                            cookies = session.cookie_jar
                            if cookies:
                                self._authenticated = True
                                if attempt > 1:
                                    logger.info(f"✅ Аутентификация успешна после {attempt} попыток (redirect)")
                                elif config.TEST_MODE:
                                    logger.debug("Authentication successful (redirect)")
                                return True
                            else:
                                if config.TEST_MODE:
                                    response_text = await response.text()
                                    logger.warning(f"Redirect without cookies: {response.status} - {response_text[:200]}")
                                # Пробуем считать успешным, если нет ошибки
                                self._authenticated = True
                                return True
                        else:
                            response_text = await response.text()
                            error_msg = f"Authentication error: {response.status} - {response_text[:500]}"
                            logger.error(error_msg)
                            last_error = error_msg
                            # Для HTTP ошибок не повторяем попытку
                            if response.status >= 400 and response.status < 500:
                                return False
                            # Для серверных ошибок (5xx) повторяем
                            if attempt < max_retries:
                                wait_time = 2 ** attempt  # Экспоненциальная задержка: 2, 4, 8 секунд
                                logger.warning(f"⏳ Повтор через {wait_time} секунд...")
                                await asyncio.sleep(wait_time)
                                continue
                            return False
                except aiohttp.http_exceptions.BadStatusLine as e:
                    # Обработка некорректного формата HTTP ответа (например, HTTP/0.0)
                    if config.TEST_MODE:
                        logger.warning(f"Bad HTTP response format: {e}, trying as success")
                    # Пробуем считать успешным, так как это может быть редирект
                    self._authenticated = True
                    return True
                except aiohttp.http_exceptions.HttpProcessingError as e:
                    # Обработка ошибок обработки HTTP
                    if config.TEST_MODE:
                        logger.warning(f"HTTP processing error: {e}, trying as success")
                    # Пробуем считать успешным, так как это может быть редирект
                    self._authenticated = True
                    return True
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                # Обработка ошибок клиента (сеть, таймаут и т.д.) - повторяем попытку
                error_msg = str(e)
                last_error = error_msg
                logger.warning(f"⚠️ Сетевая ошибка при аутентификации (попытка {attempt}/{max_retries}): {e}")
                
                if attempt < max_retries:
                    wait_time = 2 ** attempt  # Экспоненциальная задержка: 2, 4, 8 секунд
                    logger.info(f"⏳ Повтор через {wait_time} секунд...")
                    await asyncio.sleep(wait_time)
                    # Закрываем сессию перед повторной попыткой
                    try:
                        await self.close()
                    except:
                        pass
                    continue
                else:
                    logger.error(f"❌ Не удалось аутентифицироваться после {max_retries} попыток: {e}")
                    return False
            except aiohttp.ClientResponseError as e:
                # Обработка ошибок HTTP ответа
                if e.status == 0:
                    # Статус 0 обычно означает проблему с парсингом HTTP ответа
                    if config.TEST_MODE:
                        logger.warning("Status 0 (HTTP parsing issue), trying as success")
                    self._authenticated = True
                    return True
                elif e.status in [302, 307, 308]:
                    # Редирект - пробуем считать успешным
                    if config.TEST_MODE:
                        logger.warning("Redirect received, trying as success")
                    self._authenticated = True
                    return True
                error_msg = f"HTTP error during authentication: {e.status} - {e.message}"
                logger.error(error_msg)
                last_error = error_msg
                # Для клиентских ошибок (4xx) не повторяем
                if e.status >= 400 and e.status < 500:
                    return False
                # Для серверных ошибок повторяем
                if attempt < max_retries:
                    wait_time = 2 ** attempt
                    logger.warning(f"⏳ Повтор через {wait_time} секунд...")
                    await asyncio.sleep(wait_time)
                    continue
                return False
            except Exception as e:
                error_msg = f"Unexpected error during authentication: {e}"
                logger.error(error_msg)
                last_error = error_msg
                import traceback
                logger.error(traceback.format_exc())
                # Для неожиданных ошибок тоже повторяем
                if attempt < max_retries:
                    wait_time = 2 ** attempt
                    logger.warning(f"⏳ Повтор через {wait_time} секунд...")
                    await asyncio.sleep(wait_time)
                    try:
                        await self.close()
                    except:
                        pass
                    continue
                return False
        
        # Если все попытки исчерпаны
        logger.error(f"❌ Аутентификация не удалась после {max_retries} попыток. Последняя ошибка: {last_error}")
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
        
        # После аутентификации используем только cookies, без username/password
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json"
        }
        
        if self.ssl_certificate:
            logger.info(f"🔒 Запрос inbounds с SSL сертификатом: {self._cert_file_path}")
            logger.info(f"🔒 URL запроса: {url}")
            logger.info(f"🔒 Использует HTTPS: {url.startswith('https://')}")
        
        # ВСЕГДА передаем SSL контекст в запрос, если есть сертификат
        ssl_for_request = None
        if self._cert_file_path:
            # Используем тот же SSL контекст, что и в сессии
            use_https = self.api_url.startswith('https://')
            if use_https:
                ssl_for_request = ssl.create_default_context(cafile=self._cert_file_path)
                # Отключаем проверку hostname для работы с IP-адресами
                ssl_for_request.check_hostname = False
            else:
                # Для HTTP тоже создаем контекст с сертификатом
                ssl_for_request = ssl.create_default_context()
                ssl_for_request.load_verify_locations(self._cert_file_path)
                ssl_for_request.check_hostname = False
                ssl_for_request.verify_mode = ssl.CERT_REQUIRED
            logger.info(f"🔒 SSL контекст для запроса inbounds создан: {self._cert_file_path}")
        
        try:
            # Пробуем GET запрос без данных (используем только cookies)
            async with session.get(
                url, 
                headers=headers,
                allow_redirects=True,
                max_redirects=10,
                ssl=ssl_for_request  # Передаем SSL контекст в запрос
            ) as response:
                logger.info(f"📡 Получен ответ от сервера: статус {response.status}")
                if response.status == 200:
                    try:
                        result = await response.json()
                        logger.info(f"📋 Результат JSON: {type(result)}, keys: {result.keys() if isinstance(result, dict) else 'N/A'}")
                        if isinstance(result, dict) and "obj" in result:
                            inbounds = result["obj"]
                            logger.info(f"📋 Найдено inbounds: {len(inbounds) if isinstance(inbounds, list) else 0}")
                            if isinstance(inbounds, list):
                                if len(inbounds) > 0:
                                    logger.info(f"📋 Первый inbound (ID: {inbounds[0].get('id', 'N/A')}, protocol: {inbounds[0].get('protocol', 'N/A')})")
                                else:
                                    logger.warning("⚠️ Список inbounds пуст!")
                            return inbounds if isinstance(inbounds, list) else None
                        if isinstance(result, list):
                            logger.info(f"📋 Результат - список, длина: {len(result)}")
                            if len(result) > 0:
                                logger.info(f"📋 Первый элемент: {result[0]}")
                            return result
                        logger.warning(f"⚠️ Неожиданный формат результата: {type(result)}")
                        # Пробуем получить текст для отладки
                        try:
                            response_text = await response.text()
                            logger.warning(f"⚠️ Текст ответа: {response_text[:500]}")
                        except:
                            pass
                        return None
                    except Exception as json_error:
                        logger.error(f"❌ Ошибка парсинга JSON: {json_error}")
                        # Пробуем получить текст для отладки
                        try:
                            response_text = await response.text()
                            logger.error(f"❌ Текст ответа: {response_text[:500]}")
                        except:
                            pass
                        import traceback
                        logger.error(traceback.format_exc())
                        return None
                elif response.status == 404:
                    # Если GET не работает, пробуем POST без username/password (только cookies)
                    async with session.post(
                        url, 
                        headers=headers,
                        allow_redirects=True,
                        max_redirects=10,
                        ssl=ssl_for_request  # Передаем SSL контекст в запрос
                    ) as response2:
                        if response2.status == 200:
                            try:
                                result = await response2.json()
                                if isinstance(result, dict) and "obj" in result:
                                    inbounds = result["obj"]
                                    return inbounds if isinstance(inbounds, list) else None
                                return result if isinstance(result, list) else None
                            except Exception as json_error:
                                logger.error(f"❌ Ошибка парсинга JSON (POST): {json_error}")
                                return None
                        else:
                            response_text2 = await response2.text()
                            logger.error(f"❌ Ошибка получения inbounds (POST): {response2.status} - {response_text2}")
                            return None
                else:
                    response_text = await response.text()
                    logger.error(f"❌ Ошибка получения inbounds: {response.status} - {response_text}")
                    return None
        except aiohttp.http_exceptions.BadStatusLine as e:
            # Обработка некорректного формата HTTP ответа (например, HTTP/0.0)
            # Пробуем через POST как fallback (без username/password, только cookies)
            try:
                async with session.post(
                    url, 
                    headers=headers,
                    allow_redirects=True,
                    max_redirects=10
                ) as response:
                    if response.status == 200:
                        try:
                            result = await response.json()
                            if isinstance(result, dict) and "obj" in result:
                                inbounds = result["obj"]
                                return inbounds if isinstance(inbounds, list) else None
                            return result if isinstance(result, list) else None
                        except Exception as json_error:
                            logger.error(f"❌ Ошибка парсинга JSON (POST fallback): {json_error}")
                            return None
                    else:
                        logger.warning(f"⚠️ POST fallback вернул статус {response.status}, пробуем получить данные несмотря на статус")
                        # Пробуем получить данные даже при не-200 статусе (может быть редирект)
                        try:
                            result = await response.json()
                            if isinstance(result, dict) and "obj" in result:
                                inbounds = result["obj"]
                                if isinstance(inbounds, list) and len(inbounds) > 0:
                                    return inbounds
                            if isinstance(result, list) and len(result) > 0:
                                return result
                        except:
                            pass
                        # Если не удалось получить данные, пробуем еще раз через прямой запрос
                        logger.warning("⚠️ Не удалось получить данные через POST fallback, пробуем прямой запрос")
                        return None
            except aiohttp.http_exceptions.BadStatusLine as e2:
                # Если и POST fallback получил BadStatusLine, пробуем еще раз с другим подходом
                logger.warning(f"⚠️ POST fallback также получил BadStatusLine: {e2}")
                logger.warning("⚠️ Пробуем получить inbounds через прямой запрос без редиректов")
                # Пробуем без allow_redirects (только cookies, без username/password)
                try:
                    async with session.post(
                        url, 
                        headers=headers,
                        allow_redirects=False,  # Без редиректов
                        ssl=ssl_for_request  # Передаем SSL контекст в запрос
                    ) as response:
                        if response.status in [200, 302, 307, 308]:
                            try:
                                result = await response.json()
                                if isinstance(result, dict) and "obj" in result:
                                    inbounds = result["obj"]
                                    if isinstance(inbounds, list) and len(inbounds) > 0:
                                        return inbounds
                                if isinstance(result, list) and len(result) > 0:
                                    return result
                            except:
                                pass
                except:
                    pass
                return None
            except Exception as e2:
                logger.warning(f"⚠️ POST fallback также не сработал: {e2}")
                return None
        except aiohttp.http_exceptions.HttpProcessingError as e:
            # Обработка ошибок обработки HTTP
            logger.warning(f"⚠️ Ошибка обработки HTTP при получении inbounds: {e}")
            logger.warning("⚠️ Пробуем через POST fallback")
            # Пробуем через POST как fallback (только cookies, без username/password)
            try:
                async with session.post(
                    url, 
                    headers=headers,
                    allow_redirects=True,
                    max_redirects=10
                ) as response:
                    if response.status == 200:
                        try:
                            result = await response.json()
                            if isinstance(result, dict) and "obj" in result:
                                inbounds = result["obj"]
                                return inbounds if isinstance(inbounds, list) else None
                            return result if isinstance(result, list) else None
                        except Exception as json_error:
                            logger.error(f"❌ Ошибка парсинга JSON (POST fallback): {json_error}")
                            return None
                    else:
                        logger.warning(f"⚠️ POST fallback вернул статус {response.status}")
                        return None
            except Exception as e2:
                logger.warning(f"⚠️ POST fallback также не сработал: {e2}")
                return None
        except aiohttp.ClientResponseError as e:
            # Обработка ошибок HTTP ответа
            logger.error(f"❌ Ошибка HTTP при получении inbounds: {e.status} - {e.message}")
            if e.status == 0:
                logger.warning("⚠️ Получен статус 0, пробуем через POST fallback")
                # Пробуем через POST как fallback (только cookies, без username/password)
                try:
                    async with session.post(
                        url, 
                        headers=headers,
                        allow_redirects=True,
                        max_redirects=10
                    ) as response:
                        if response.status == 200:
                            try:
                                result = await response.json()
                                if isinstance(result, dict) and "obj" in result:
                                    inbounds = result["obj"]
                                    return inbounds if isinstance(inbounds, list) else None
                                return result if isinstance(result, list) else None
                            except Exception as json_error:
                                logger.error(f"❌ Ошибка парсинга JSON (POST fallback): {json_error}")
                                return None
                        else:
                            logger.warning(f"⚠️ POST fallback вернул статус {response.status}")
                            return None
                except Exception as e2:
                    logger.warning(f"⚠️ POST fallback также не сработал: {e2}")
                    return None
            return None
        except Exception as e:
            logger.error(f"❌ Ошибка при получении inbounds: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None
    
    async def add_client_to_inbound(
        self,
        inbound_id: int,
        email: str,
        days: int = 30,
        tg_id: Optional[str] = None,
        limit_ip: int = 3,
        total_gb: float = 0.0,
        sub_id: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Добавляет клиента к указанному inbound
        
        Args:
            inbound_id: ID inbound для добавления клиента
            email: Email клиента
            days: Количество дней подписки
            tg_id: Telegram ID пользователя (опционально)
            limit_ip: Лимит IP адресов
            total_gb: Лимит трафика в GB (0 = безлимит)
            sub_id: SubId для подписок (опционально, если не указан - используется пустая строка)
            
        Returns:
            Response объект или None
        """
        # Убеждаемся, что мы аутентифицированы
        if not self._authenticated:
            login_success = await self.login()
            if not login_success:
                return {"error": True, "message": "Ошибка аутентификации", "error_type": "authentication"}
        
        # Получаем список inbounds для проверки существования inbound
        inbounds = await self.get_inbounds()
        if inbounds is None:
            return {"error": True, "message": "Ошибка получения списка inbounds с сервера. Проверьте подключение и настройки сервера.", "error_type": "connection"}
        if len(inbounds) == 0:
            return {"error": True, "message": "На сервере нет доступных inbounds", "error_type": "no_inbounds"}
        
        # Проверяем, что inbound существует
        inbound = None
        for inv in inbounds:
            if inv.get("id") == inbound_id:
                inbound = inv
                break
        
        if not inbound:
            return {"error": True, "message": f"Inbound {inbound_id} не найден", "error_type": "inbound_not_found"}
        
        # НЕ задаем expiryTime - бот сам управляет включением/отключением клиента
        # Используем 0 для бессрочной подписки (управление через enable/disable)
        x_time = 0  # Бессрочная подписка, управление через enable/disable
        
        # Генерируем UUID как в test.py
        client_id = str(uuid_lib.uuid4())
        
        # Определяем протокол inbound для правильной настройки клиента
        protocol = inbound.get("protocol", "").lower()
        
        # Проверяем, что протокол поддерживается
        if protocol not in ["vless", "shadowsocks", "vmess", "trojan"]:
            return {"error": True, "message": f"Неподдерживаемый протокол: {protocol}", "error_type": "unsupported_protocol"}
        
        # Для Shadowsocks используем упрощенную структуру без id (UUID)
        if protocol == "shadowsocks":
            # Для Shadowsocks: email, subId, password (password должен быть длиной 32 байта, закодирован в base64)
            # Не добавляем id, alterId, flow - только базовые поля
            # Добавляем временные метки для правильной работы с панелью
            epoch = datetime.utcfromtimestamp(0)
            current_time_ms = int((datetime.utcnow() - epoch).total_seconds() * 1000.0)
            
            # Для Shadowsocks 2022-blake3-aes-256-gcm нужен password длиной 32 байта в base64
            # НО: API 3x-ui может сам генерировать password, если мы не передадим его
            # Попробуем сначала без password, если не сработает - сгенерируем сами
            import secrets
            import base64
            shadowsocks_key = secrets.token_bytes(32)  # 32 байта = 256 бит для AES-256
            shadowsocks_password = base64.b64encode(shadowsocks_key).decode('utf-8')
            
            # Формируем tgId (если передан, иначе 0) - для Shadowsocks должен быть int
            tg_id_value = int(tg_id) if tg_id and str(tg_id).isdigit() else 0
            
            # Структура точно как в рабочем примере q6cxnf0o
            # Порядок полей соответствует рабочему клиенту
            # ВАЖНО: Для Shadowsocks передаем password - API требует его для 2022-blake3-aes-256-gcm
            client_data = {
                "comment": "",
                "created_at": current_time_ms,
                "email": str(email),
                "enable": True,
                "expiryTime": x_time,
                "limitIp": 0,  # В рабочем примере limitIp = 0
                "method": "",  # Пустая строка для метода клиента (метод берется из настроек инбаунда)
                "password": shadowsocks_password,  # Base64-encoded ключ длиной 32 байта - ОБЯЗАТЕЛЬНО для 2022-blake3
                "reset": 0,
                "subId": sub_id if sub_id else "",
                "tgId": tg_id_value,
                "totalGB": 0,  # 0 = безлимитный трафик
                "updated_at": current_time_ms,
            }
            
            # Для Shadowsocks API addClient должен сам добавить клиента в существующий массив
            # Отправляем только клиента, API сам обработает добавление
            # ВАЖНО: API может требовать только массив clients, без других полей settings
            settings = json.dumps({"clients": [client_data]})
            logger.info(f"📝 Shadowsocks: Создаем клиента с email={email}, subId={sub_id if sub_id else 'N/A'}, password length={len(shadowsocks_password)}")
        else:
            # Для VLESS, VMESS, Trojan используем полную структуру с id
            # Добавляем временные метки для правильной работы с панелью
            epoch = datetime.utcfromtimestamp(0)
            current_time_ms = int((datetime.utcnow() - epoch).total_seconds() * 1000.0)
            
            client_data = {
                "id": client_id,
                "email": str(email),
                "limitIp": limit_ip,
                "totalGB": 0,  # 0 = безлимитный трафик (согласно документации API 3x-ui)
                "expiryTime": x_time,
                "enable": True,
                "comment": "",  # Пустой комментарий
                "reset": 0,  # Счетчик сброса трафика
                "created_at": current_time_ms,  # Временная метка создания
                "updated_at": current_time_ms,  # Временная метка обновления
            }
            
            # Добавляем параметры в зависимости от протокола
            if protocol == "vless":
                # Для VLESS не добавляем alterId (в новых версиях API он не используется)
                # Flow может быть пустым или "xtls-rprx-vision" в зависимости от настроек инбаунда
                # Устанавливаем пустую строку, API или инбаунд сам определит нужное значение
                client_data["flow"] = ""  # Пустая строка - будет установлена инбаундом или API
            elif protocol == "vmess":
                client_data["alterId"] = 0
        
        # Всегда устанавливаем totalGB = 0 для безлимитного трафика
        # (не используем переданный total_gb, чтобы гарантировать отсутствие ограничений)
        
        # Для Shadowsocks все поля уже установлены выше, пропускаем этот блок
        # Для Shadowsocks settings уже сформирован выше
        if protocol != "shadowsocks":
            if tg_id:
                client_data["tgId"] = str(tg_id)
            # Используем переданный subId или пустую строку по умолчанию
            client_data["subId"] = sub_id if sub_id else ""
            
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
        
        logger.info(f"📝 Добавление клиента: {url} (email: {email}, protocol: {protocol})")
        
        # Логируем отправляемые данные для отладки (особенно для Shadowsocks)
        if protocol == "shadowsocks":
            logger.info(f"🔍 Shadowsocks: Отправляем клиента с email={email}, subId={sub_id if sub_id else 'N/A'}, password length={len(shadowsocks_password)}")
            logger.info(f"🔍 Shadowsocks client data: {json.dumps(client_data, indent=2)}")
            logger.info(f"🔍 Shadowsocks settings: {settings}")
            logger.info(f"🔍 Shadowsocks request data: {json.dumps(data1, indent=2)}")
        
        try:
            async with session.post(
                url, 
                headers=headers, 
                json=data1,
                allow_redirects=True,
                max_redirects=10
            ) as response:
                response_text = await response.text()
                
                if response.status == 200 or response.status == 201:
                    try:
                        result = await response.json()
                        # Добавляем client_id в результат, чтобы можно было использовать его позже
                        if isinstance(result, dict):
                            result["client_id"] = client_id  # UUID клиента, который мы создали
                            result["client_email"] = email
                        
                        logger.info(f"✅ Клиент успешно создан (protocol: {protocol}, email: {email})")
                        if protocol == "shadowsocks":
                            logger.info(f"✅ Shadowsocks клиент создан: email={email}, subId={sub_id if sub_id else 'N/A'}")
                        return result
                    except:
                        logger.debug(f"✅ Клиент создан (не JSON ответ)")
                        return {"success": True, "status_code": response.status, "client_id": client_id, "client_email": email}
                else:
                    logger.error(f"❌ Ошибка создания клиента: {response.status} - {response_text}")
                    if protocol == "shadowsocks":
                        logger.error(f"❌ Shadowsocks: Не удалось создать клиента. Status: {response.status}, Response: {response_text}")
                        logger.error(f"❌ Shadowsocks: Отправленные данные: {json.dumps(data1, indent=2)}")
                    return {"error": True, "status_code": response.status, "message": response_text, "error_type": "api_error"}
        except Exception as e:
            logger.error(f"❌ Ошибка при создании клиента: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return {"error": True, "status_code": None, "message": str(e), "error_type": "unexpected"}
    
    async def add_client(
        self,
        email: str,
        days: int = 30,
        tg_id: Optional[str] = None,
        limit_ip: int = 3,
        total_gb: float = 0.0,
        sub_id: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Добавляет клиента к первому доступному inbound (точно как в test.py addClient)
        Для обратной совместимости - использует add_client_to_inbound
        
        Args:
            email: Email клиента
            days: Количество дней подписки
            tg_id: Telegram ID пользователя (опционально)
            limit_ip: Лимит IP адресов
            total_gb: Лимит трафика в GB (0 = безлимит)
            sub_id: SubId для подписок (опционально, если не указан - используется пустая строка)
            
        Returns:
            Response объект или None
        """
        # Получаем список inbounds и используем первый доступный
        inbounds = await self.get_inbounds()
        if inbounds is None:
            return {"error": True, "message": "Ошибка получения списка inbounds с сервера. Проверьте подключение и настройки сервера.", "error_type": "connection"}
        if len(inbounds) == 0:
            return {"error": True, "message": "На сервере нет доступных inbounds", "error_type": "no_inbounds"}
        
        # Используем первый inbound
        inbound = inbounds[0]
        inbound_id = inbound.get("id", 1)
        
        return await self.add_client_to_inbound(
            inbound_id=inbound_id,
            email=email,
            days=days,
            tg_id=tg_id,
            limit_ip=limit_ip,
            total_gb=total_gb,
            sub_id=sub_id
        )
    
    async def add_client_to_inbound_by_protocol(
        self,
        protocol: str,
        location_name: str,
        username: str,
        unique_code: str,
        days: int = 30,
        tg_id: Optional[str] = None,
        limit_ip: int = 3,
        sub_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Создает клиента на инбаунде с указанным протоколом
        Формат email: {location_name}@{protocol}&{username}&{unique_code}
        
        Args:
            protocol: Протокол инбаунда ("vless" или "shadowsocks")
            location_name: Название локации (например, "moscow")
            username: Username пользователя (Telegram username или user_{tg_id})
            unique_code: Уникальный код подписки (например, "7acaf1")
            days: Количество дней подписки
            tg_id: Telegram ID пользователя (опционально)
            limit_ip: Лимит IP адресов
            sub_id: SubId для подписок (обязательно)
            
        Returns:
            Результат создания клиента
        """
        if not sub_id:
            return {"error": True, "message": "sub_id обязателен для создания подписки", "error_type": "missing_sub_id"}
        
        protocol = protocol.lower()
        if protocol not in ["vless", "shadowsocks"]:
            return {"error": True, "message": f"Неподдерживаемый протокол: {protocol}. Поддерживаются только vless и shadowsocks", "error_type": "unsupported_protocol"}
        
        # Получаем список inbounds
        inbounds = await self.get_inbounds()
        if inbounds is None:
            return {"error": True, "message": "Ошибка получения списка inbounds с сервера", "error_type": "connection"}
        if len(inbounds) == 0:
            return {"error": True, "message": "На сервере нет доступных inbounds", "error_type": "no_inbounds"}
        
        # Ищем инбаунд с нужным протоколом
        target_inbound = None
        for inbound in inbounds:
            inbound_protocol = inbound.get("protocol", "").lower()
            if inbound_protocol == protocol:
                # Проверяем, что инбаунд активен
                if inbound.get("enable", True):
                    target_inbound = inbound
                    break
        
        if not target_inbound:
            return {"error": True, "message": f"{protocol.upper()} инбаунд не найден или неактивен", "error_type": "inbound_not_found"}
        
        # Формируем email
        client_email = f"{location_name}@{protocol}&{username}&{unique_code}"
        
        # Создаем клиента на найденном инбаунде
        result = await self.add_client_to_inbound(
            inbound_id=target_inbound.get("id"),
            email=client_email,
            days=days,
            tg_id=tg_id,
            limit_ip=limit_ip,
            sub_id=sub_id
        )
        
        return result
    
    async def add_client_to_both_inbounds(
        self,
        location_name: str,
        username: str,
        unique_code: str,
        days: int = 30,
        tg_id: Optional[str] = None,
        limit_ip: int = 3,
        sub_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Создает клиента на VLESS инбаунде с subID
        Формат email: {location_name}@vless&{username}&{unique_code}
        Где unique_code - это уникальный код подписки без названия локации и символа "-"
        
        Args:
            location_name: Название локации (например, "moscow")
            username: Username пользователя (Telegram username или user_{tg_id})
            unique_code: Уникальный код подписки (например, "7acaf1" без "moscow-")
            days: Количество дней подписки
            tg_id: Telegram ID пользователя (опционально)
            limit_ip: Лимит IP адресов
            sub_id: SubId для подписок (обязательно)
            
        Returns:
            Словарь с результатами создания клиента на VLESS инбаунде
        """
        if not sub_id:
            return {"error": True, "message": "sub_id обязателен для создания подписки", "error_type": "missing_sub_id"}
        
        # Получаем список inbounds
        inbounds = await self.get_inbounds()
        if inbounds is None:
            return {"error": True, "message": "Ошибка получения списка inbounds с сервера", "error_type": "connection"}
        if len(inbounds) == 0:
            return {"error": True, "message": "На сервере нет доступных inbounds", "error_type": "no_inbounds"}
        
        # Ищем VLESS инбаунд
        vless_inbound = None
        
        for inbound in inbounds:
            protocol = inbound.get("protocol", "").lower()
            if protocol == "vless" and vless_inbound is None:
                # Проверяем, что инбаунд активен
                if inbound.get("enable", True):
                    vless_inbound = inbound
                    break
        
        # Создаем клиента на VLESS инбаунде
        results = {
            "vless": None,
            "errors": []
        }
        
        if vless_inbound:
            vless_email = f"{location_name}@vless&{username}&{unique_code}"
            vless_result = await self.add_client_to_inbound(
                inbound_id=vless_inbound.get("id"),
                email=vless_email,
                days=days,
                tg_id=tg_id,
                limit_ip=limit_ip,
                sub_id=sub_id
            )
            results["vless"] = vless_result
            if vless_result and vless_result.get("error"):
                results["errors"].append(f"VLESS: {vless_result.get('message', 'Неизвестная ошибка')}")
        else:
            logger.warning(f"⚠️ VLESS инбаунд не найден или неактивен, пропускаем создание VLESS клиента")
            results["errors"].append("VLESS инбаунд не найден или неактивен")
        
        # Проверяем результат
        vless_success = results["vless"] and not results["vless"].get("error")
        
        if not vless_success:
            results["error"] = True
            results["message"] = "; ".join(results["errors"])
            results["error_type"] = "all_failed"
        else:
            results["error"] = False
            results["message"] = "VLESS клиент успешно создан"
        
        return results
    
    async def add_client_to_all_inbounds(
        self,
        location_name: str,
        username: str,
        unique_code: str,
        days: int = 30,
        tg_id: Optional[str] = None,
        limit_ip: int = 3,
        sub_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Создает клиента во всех инбаундах на основе первого клиента каждого инбаунда.
        Для каждого инбаунда берет первого клиента как шаблон, меняет только уникальные поля
        (email, subId, password, id) и создает нового клиента.
        
        Args:
            location_name: Название локации (например, "moscow")
            username: Username пользователя (Telegram username или user_{tg_id})
            unique_code: Уникальный код подписки (например, "7acaf1")
            days: Количество дней подписки
            tg_id: Telegram ID пользователя (опционально)
            limit_ip: Лимит IP адресов
            sub_id: SubId для подписок (обязательно)
            
        Returns:
            Словарь с результатами создания клиентов во всех инбаундах
        """
        if not sub_id:
            return {"error": True, "message": "sub_id обязателен для создания подписки", "error_type": "missing_sub_id"}
        
        # Получаем список inbounds
        inbounds = await self.get_inbounds()
        if inbounds is None:
            return {"error": True, "message": "Ошибка получения списка inbounds с сервера", "error_type": "connection"}
        if len(inbounds) == 0:
            return {"error": True, "message": "На сервере нет доступных inbounds", "error_type": "no_inbounds"}
        
        results = {
            "created": [],
            "errors": [],
            "total_inbounds": len(inbounds)
        }
        
        # Проходим по всем инбаундам
        for inbound in inbounds:
            inbound_id = inbound.get("id")
            if not inbound_id:
                continue
            
            # Пропускаем неактивные инбаунды
            if not inbound.get("enable", True):
                logger.debug(f"⚠️ Inbound {inbound_id} неактивен, пропускаем")
                continue
            
            protocol = inbound.get("protocol", "").lower()
            if protocol not in ["vless", "shadowsocks", "vmess", "trojan"]:
                logger.debug(f"⚠️ Неподдерживаемый протокол {protocol} для inbound {inbound_id}, пропускаем")
                continue
            
            try:
                # Получаем первого клиента из инбаунда как шаблон
                settings_str = inbound.get("settings", "{}")
                try:
                    settings = json.loads(settings_str) if isinstance(settings_str, str) else settings_str
                    clients = settings.get("clients", [])
                except (json.JSONDecodeError, TypeError) as e:
                    logger.warning(f"⚠️ Ошибка парсинга settings для inbound {inbound_id}: {e}")
                    results["errors"].append(f"Inbound {inbound_id}: ошибка парсинга settings")
                    continue
                
                if not clients or len(clients) == 0:
                    logger.warning(f"⚠️ В inbound {inbound_id} нет клиентов для использования как шаблон")
                    results["errors"].append(f"Inbound {inbound_id}: нет клиентов для шаблона")
                    continue
                
                # Берем первого клиента как шаблон
                template_client = clients[0].copy()
                
                # Получаем network из streamSettings для уникальности
                stream_settings_str = inbound.get("streamSettings", "{}")
                try:
                    stream_settings = json.loads(stream_settings_str) if isinstance(stream_settings_str, str) else stream_settings_str
                    network = stream_settings.get("network", "tcp")  # По умолчанию tcp
                except (json.JSONDecodeError, TypeError) as e:
                    logger.warning(f"⚠️ Ошибка парсинга streamSettings для inbound {inbound_id}: {e}, используем 'tcp' по умолчанию")
                    network = "tcp"
                
                logger.info(f"📋 Используем первого клиента из inbound {inbound_id} (protocol: {protocol}, network: {network}) как шаблон")
                
                # Формируем email для нового клиента
                # Формат: {location_name}@{network}&{username}&{unique_code}&{inbound_id}
                # Используем network вместо protocol и добавляем inbound_id для уникальности
                client_email = f"{location_name}@{network}&{username}&{unique_code}&{inbound_id}"
                
                # Создаем новый клиент на основе шаблона
                # Копируем все настройки из шаблона
                new_client = template_client.copy()
                
                # Меняем только уникальные поля
                new_client["email"] = client_email
                new_client["subId"] = sub_id if sub_id else ""
                
                # Генерируем новый UUID для протоколов, которые его используют
                if protocol != "shadowsocks":
                    new_client["id"] = str(uuid_lib.uuid4())
                else:
                    # Для Shadowsocks удаляем id если он есть
                    if "id" in new_client:
                        del new_client["id"]
                    # Генерируем новый password для Shadowsocks
                    import secrets
                    import base64
                    shadowsocks_key = secrets.token_bytes(32)
                    new_client["password"] = base64.b64encode(shadowsocks_key).decode('utf-8')
                
                # Обновляем tgId если передан
                if tg_id:
                    if protocol == "shadowsocks":
                        new_client["tgId"] = int(tg_id) if str(tg_id).isdigit() else 0
                    else:
                        new_client["tgId"] = str(tg_id)
                else:
                    # Если не передан, оставляем из шаблона или ставим 0
                    if "tgId" not in new_client:
                        new_client["tgId"] = 0 if protocol == "shadowsocks" else ""
                
                # Обновляем limitIp если передан
                if limit_ip is not None and protocol != "shadowsocks":
                    new_client["limitIp"] = limit_ip
                
                # Устанавливаем enable = True
                new_client["enable"] = True
                
                # Устанавливаем expiryTime = 0 (бессрочная подписка, управление через enable/disable)
                new_client["expiryTime"] = 0
                
                # Обновляем временные метки
                epoch = datetime.utcfromtimestamp(0)
                current_time_ms = int((datetime.utcnow() - epoch).total_seconds() * 1000.0)
                new_client["created_at"] = current_time_ms
                new_client["updated_at"] = current_time_ms
                
                # Для Shadowsocks убеждаемся, что есть все необходимые поля
                if protocol == "shadowsocks":
                    if "method" not in new_client:
                        new_client["method"] = ""
                    if "comment" not in new_client:
                        new_client["comment"] = ""
                    if "reset" not in new_client:
                        new_client["reset"] = 0
                    if "totalGB" not in new_client:
                        new_client["totalGB"] = 0
                    # Удаляем лишние поля для Shadowsocks
                    if "flow" in new_client:
                        del new_client["flow"]
                    if "alterId" in new_client:
                        del new_client["alterId"]
                else:
                    # Для других протоколов убеждаемся, что есть необходимые поля
                    if "comment" not in new_client:
                        new_client["comment"] = ""
                    if "reset" not in new_client:
                        new_client["reset"] = 0
                    if "totalGB" not in new_client:
                        new_client["totalGB"] = 0
                    # Для VLESS убеждаемся, что flow есть (может быть пустым)
                    if protocol == "vless" and "flow" not in new_client:
                        new_client["flow"] = ""
                    # Для VMESS добавляем alterId если нет
                    if protocol == "vmess" and "alterId" not in new_client:
                        new_client["alterId"] = 0
                
                # Формируем settings с новым клиентом
                settings_dict = {"clients": [new_client]}
                settings_json = json.dumps(settings_dict, ensure_ascii=False)
                
                # Отправляем запрос на создание клиента
                data1 = {
                    "id": inbound_id,
                    "settings": settings_json
                }
                
                session = await self._get_session()
                url = f"{self.api_url}/panel/api/inbounds/addClient"
                
                headers = {
                    "Accept": "application/json",
                    "Content-Type": "application/json"
                }
                
                logger.info(f"📝 Создание клиента в inbound {inbound_id} (protocol: {protocol}, network: {network}, email: {client_email})")
                
                async with session.post(
                    url,
                    headers=headers,
                    json=data1,
                    allow_redirects=True,
                    max_redirects=10
                ) as response:
                    response_text = await response.text()
                    
                    if response.status == 200 or response.status == 201:
                        try:
                            result = await response.json()
                            result["inbound_id"] = inbound_id
                            result["protocol"] = protocol
                            result["client_email"] = client_email
                            results["created"].append({
                                "inbound_id": inbound_id,
                                "protocol": protocol,
                                "network": network,
                                "email": client_email,
                                "result": result
                            })
                            logger.info(f"✅ Клиент создан в inbound {inbound_id} (protocol: {protocol}, network: {network})")
                        except:
                            results["created"].append({
                                "inbound_id": inbound_id,
                                "protocol": protocol,
                                "network": network,
                                "email": client_email,
                                "result": {"success": True, "status_code": response.status}
                            })
                            logger.info(f"✅ Клиент создан в inbound {inbound_id} (protocol: {protocol}, network: {network}, не JSON ответ)")
                    else:
                        error_msg = f"Inbound {inbound_id} ({protocol}): {response.status} - {response_text[:200]}"
                        results["errors"].append(error_msg)
                        logger.error(f"❌ Ошибка создания клиента в inbound {inbound_id}: {error_msg}")
                        
            except Exception as e:
                error_msg = f"Inbound {inbound_id} ({protocol}): {str(e)}"
                results["errors"].append(error_msg)
                logger.error(f"❌ Ошибка при создании клиента в inbound {inbound_id}: {e}")
                import traceback
                logger.error(traceback.format_exc())
        
        # Формируем итоговый результат
        if results["errors"] and not results["created"]:
            results["error"] = True
            results["message"] = f"Не удалось создать клиентов ни в одном инбаунде. Ошибок: {len(results['errors'])}"
            results["error_type"] = "all_failed"
        elif results["errors"]:
            results["error"] = False
            results["message"] = f"Создано клиентов: {len(results['created'])}/{results['total_inbounds']}, ошибок: {len(results['errors'])}"
        else:
            results["error"] = False
            results["message"] = f"Успешно создано клиентов: {len(results['created'])}/{results['total_inbounds']}"
        
        return results
    
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
        
        inbound_id = client.get("inbound_id")
        if not inbound_id:
            return {"error": True, "message": "Не удалось получить ID inbound", "error_type": "invalid_client"}
        
        # Получаем протокол из клиента или определяем из email
        protocol = client.get("protocol")
        if not protocol:
            # Определяем протокол из email (формат: {location}@{protocol}&{username}&{code})
            if "@vless&" in client_email:
                protocol = "vless"
            elif "@shadowsocks&" in client_email:
                protocol = "shadowsocks"
            elif "@vmess&" in client_email:
                protocol = "vmess"
            elif "@trojan&" in client_email:
                protocol = "trojan"
        
        # Для Shadowsocks клиента может не быть поля id (UUID)
        # В этом случае используем email как идентификатор
        client_id = client.get("id")
        if not client_id and protocol == "shadowsocks":
            # Для Shadowsocks используем email как идентификатор
            client_id = client_email
        
        # Получаем текущие данные клиента
        inbounds = await self.get_inbounds()
        if not inbounds:
            return {"error": True, "message": "Не удалось получить список inbounds", "error_type": "no_inbounds"}
        
        inbound = None
        for inv in inbounds:
            if inv.get("id") == inbound_id:
                inbound = inv
                protocol = inv.get("protocol", "").lower()
                break
        
        if not inbound:
            return {"error": True, "message": f"Inbound {inbound_id} не найден", "error_type": "inbound_not_found"}
        
        # Парсим settings для получения текущих данных клиента
        settings_str = inbound.get("settings", "{}")
        try:
            settings = json.loads(settings_str) if isinstance(settings_str, str) else settings_str
            clients = settings.get("clients", [])
            
            logger.info(f"🔍 Поиск клиента {client_email} в {len(clients)} клиентах inbound {inbound_id} (протокол: {protocol})")
            
            # Находим клиента в списке
            current_client_data = None
            for c in clients:
                if c.get("email") == client_email:
                    current_client_data = c.copy()
                    # Для Shadowsocks может не быть id, используем email
                    if not client_id and protocol == "shadowsocks":
                        client_id = client_email  # Используем email как идентификатор для Shadowsocks
                    logger.info(f"✅ Клиент найден: id={current_client_data.get('id', 'N/A')}, enable={current_client_data.get('enable')}")
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
        if "subId" not in current_client_data:
            current_client_data["subId"] = ""
        if "tgId" not in current_client_data:
            current_client_data["tgId"] = 0
        if "comment" not in current_client_data:
            current_client_data["comment"] = ""
        if "reset" not in current_client_data:
            current_client_data["reset"] = 0
        
        # Для Shadowsocks не добавляем flow и alterId, для других протоколов добавляем если нужно
        if protocol != "shadowsocks":
            if "flow" not in current_client_data:
                current_client_data["flow"] = ""
            # Для Shadowsocks удаляем flow и alterId если они есть
        else:
            # Для Shadowsocks удаляем лишние поля
            if "flow" in current_client_data:
                del current_client_data["flow"]
            if "alterId" in current_client_data:
                del current_client_data["alterId"]
            if "id" in current_client_data:
                # Для Shadowsocks не используем id в обновлении
                del current_client_data["id"]
            # Убеждаемся, что есть необходимые поля для Shadowsocks
            if "method" not in current_client_data:
                current_client_data["method"] = ""
            # Для Shadowsocks password должен быть сгенерирован API при создании
            # При обновлении сохраняем существующий password, если он есть
            # Если password отсутствует, это может быть проблемой, но не генерируем его вручную
            # так как это может вызвать проблемы с подключением
            if "password" not in current_client_data or not current_client_data.get("password"):
                logger.warning(f"⚠️ У Shadowsocks клиента {client_email} отсутствует password - это может вызвать проблемы")
        
        # Сохраняем временные метки, если они есть
        if "created_at" not in current_client_data:
            # Если нет created_at, устанавливаем текущее время
            epoch = datetime.utcfromtimestamp(0)
            current_client_data["created_at"] = int((datetime.utcnow() - epoch).total_seconds() * 1000.0)
        
        # Всегда обновляем updated_at
        epoch = datetime.utcfromtimestamp(0)
        current_client_data["updated_at"] = int((datetime.utcnow() - epoch).total_seconds() * 1000.0)
        
        # Удаляем alterId только для протоколов, где он не нужен (кроме VLESS и VMESS)
        if protocol not in ["vless", "vmess"] and "alterId" in current_client_data:
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
        # Для Shadowsocks используем email как идентификатор, если нет id
        update_client_id = client_id if client_id else client_email
        url = f"{self.api_url}/panel/api/inbounds/updateClient/{update_client_id}"
        
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json"
        }
        
        logger.info(f"📝 Обновление клиента: {url}")
        logger.info(f"   Email: {client_email}, Enable: {enable}, Days: {days}")
        logger.info(f"   Client ID: {client_id}, Inbound ID: {inbound_id}")
        logger.info(f"   Request data: id={data1['id']}, settings length={len(data1['settings'])}")
        
        try:
            # Добавляем таймаут для запроса
            timeout = aiohttp.ClientTimeout(total=30, connect=10)
            async with session.post(
                url, 
                headers=headers, 
                json=data1,
                allow_redirects=True,
                max_redirects=10,
                timeout=timeout
            ) as response:
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
        except asyncio.CancelledError:
            # При отмене задачи логируем и пробрасываем дальше
            logger.warning(f"⚠️ Запрос обновления клиента отменен: {client_email}")
            raise  # Пробрасываем CancelledError дальше
        except asyncio.TimeoutError:
            logger.error(f"❌ Таймаут при обновлении клиента: {client_email}")
            return {"error": True, "status_code": None, "message": "Таймаут запроса", "error_type": "timeout"}
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
    
    async def disable_all_clients_by_sub_id(self, sub_id: str) -> Dict[str, Any]:
        """
        Отключает всех клиентов с указанным subID на всех инбаундах
        
        Args:
            sub_id: SubId подписки
            
        Returns:
            Словарь с результатами отключения клиентов
        """
        # Используем update_all_clients_by_sub_id для отключения
        return await self.update_all_clients_by_sub_id(sub_id, enable=False)
    
    async def enable_all_clients_by_sub_id(self, sub_id: str) -> Dict[str, Any]:
        """
        Включает всех клиентов с указанным subID на всех инбаундах
        
        Args:
            sub_id: SubId подписки
            
        Returns:
            Словарь с результатами включения клиентов
        """
        # Используем update_all_clients_by_sub_id для включения
        return await self.update_all_clients_by_sub_id(sub_id, enable=True)
    
    async def update_all_clients_by_sub_id(
        self,
        sub_id: str,
        enable: bool = None,
        days: int = None
    ) -> Dict[str, Any]:
        """
        Обновляет всех клиентов с указанным subID на всех инбаундах
        
        Args:
            sub_id: SubId подписки
            enable: Включить (True) или отключить (False) клиента. Если None - не меняем
            days: Количество дней подписки. Если None - не меняем
            
        Returns:
            Словарь с результатами обновления клиентов
        """
        if not sub_id:
            return {"error": True, "message": "sub_id обязателен", "error_type": "missing_sub_id"}
        
        # Получаем всех клиентов с этим subID
        subscription_clients = await self.get_subscription_by_sub_id(sub_id)
        
        if not subscription_clients:
            logger.warning(f"⚠️ Не найдено клиентов с subID {sub_id}")
            return {"error": True, "message": f"Не найдено клиентов с subID {sub_id}", "error_type": "not_found"}
        
        results = {
            "updated": [],
            "errors": [],
            "total": len(subscription_clients)
        }
        
        # Обновляем каждого клиента
        for client_data in subscription_clients:
            client_email = client_data.get("email")
            if not client_email:
                continue
            
            try:
                result = await self.update_client(client_email, enable=enable, days=days)
                if result and not result.get("error"):
                    results["updated"].append(client_email)
                    logger.info(f"✅ Обновлен клиент {client_email} (subID: {sub_id})")
                else:
                    error_msg = result.get("message", "Неизвестная ошибка") if result else "Ошибка обновления"
                    results["errors"].append(f"{client_email}: {error_msg}")
                    logger.warning(f"⚠️ Не удалось обновить клиента {client_email}: {error_msg}")
            except asyncio.CancelledError:
                # При отмене задачи прерываем обработку
                logger.warning(f"⚠️ Операция обновления клиентов отменена (subID: {sub_id})")
                results["errors"].append("Операция была отменена")
                # Закрываем сессию при отмене
                try:
                    await self.close()
                except:
                    pass
                raise  # Пробрасываем CancelledError дальше
            except Exception as e:
                results["errors"].append(f"{client_email}: {str(e)}")
                logger.error(f"❌ Ошибка при обновлении клиента {client_email}: {e}")
                import traceback
                logger.error(traceback.format_exc())
        
        if results["errors"]:
            results["error"] = True
            results["message"] = f"Обновлено {len(results['updated'])}/{results['total']}, ошибок: {len(results['errors'])}"
        else:
            results["success"] = True
            results["message"] = f"Успешно обновлено {len(results['updated'])} клиентов"
        
        return results
    
    async def delete_all_clients_by_sub_id(self, sub_id: str) -> Dict[str, Any]:
        """
        Удаляет всех клиентов с указанным subID на всех инбаундах
        
        Args:
            sub_id: SubId подписки
            
        Returns:
            Словарь с результатами удаления клиентов
        """
        if not sub_id:
            return {"error": True, "message": "sub_id обязателен", "error_type": "missing_sub_id"}
        
        # Убеждаемся, что мы аутентифицированы перед получением подписки
        # Используем 1 попытку для массовых операций (быстрее)
        if not self._authenticated:
            login_success = await self.login(max_retries=1)
            if not login_success:
                error_msg = f"Не удалось аутентифицироваться на сервере 3x-ui для удаления клиентов с subID {sub_id}"
                logger.error(f"❌ {error_msg}")
                return {"error": True, "message": error_msg, "error_type": "authentication_failed"}
        
        # Получаем всех клиентов с этим subID
        subscription_clients = await self.get_subscription_by_sub_id(sub_id)
        
        if not subscription_clients:
            # Проверяем, была ли это ошибка аутентификации или просто клиенты не найдены
            if not self._authenticated:
                error_msg = f"Ошибка аутентификации при поиске клиентов с subID {sub_id}"
                logger.warning(f"⚠️ {error_msg}")
                return {"error": True, "message": error_msg, "error_type": "authentication_failed"}
            else:
                logger.warning(f"⚠️ Не найдено клиентов с subID {sub_id} (клиенты могли быть уже удалены или подписка не существует)")
                return {"error": True, "message": f"Не найдено клиентов с subID {sub_id}", "error_type": "not_found"}
        
        results = {
            "deleted": [],
            "errors": [],
            "total": len(subscription_clients)
        }
        
        # Удаляем каждого клиента параллельно для ускорения процесса
        async def delete_single_client(client_data: Dict[str, Any]) -> tuple:
            """Удаляет одного клиента и возвращает результат"""
            client_email = client_data.get("email")
            if not client_email:
                return None, None
            
            try:
                result = await self.delete_client(client_email)
                if result and not result.get("error"):
                    logger.info(f"✅ Удален клиент {client_email} (subID: {sub_id})")
                    return client_email, None
                else:
                    error_msg = result.get("message", "Неизвестная ошибка") if result else "Ошибка удаления"
                    logger.warning(f"⚠️ Не удалось удалить клиента {client_email}: {error_msg}")
                    return None, f"{client_email}: {error_msg}"
            except asyncio.CancelledError:
                logger.warning(f"⚠️ Операция удаления клиента {client_email} отменена")
                raise
            except Exception as e:
                logger.error(f"❌ Ошибка при удалении клиента {client_email}: {e}")
                return None, f"{client_email}: {str(e)}"
        
        # Удаляем клиентов параллельно (батчами по 10 для избежания перегрузки)
        batch_size = 10
        for batch_start in range(0, len(subscription_clients), batch_size):
            batch = subscription_clients[batch_start:batch_start + batch_size]
            batch_results = await asyncio.gather(*[delete_single_client(client_data) for client_data in batch], return_exceptions=True)
            
            for result in batch_results:
                if isinstance(result, Exception):
                    if isinstance(result, asyncio.CancelledError):
                        # При отмене задачи прерываем обработку
                        logger.warning(f"⚠️ Операция удаления клиентов отменена (subID: {sub_id})")
                        results["errors"].append("Операция была отменена")
                        try:
                            await self.close()
                        except:
                            pass
                        raise result
                    results["errors"].append(f"Исключение: {str(result)}")
                elif result[0]:  # Успешно удален
                    results["deleted"].append(result[0])
                elif result[1]:  # Ошибка
                    results["errors"].append(result[1])
        
        if results["errors"]:
            results["error"] = True
            results["message"] = f"Удалено {len(results['deleted'])}/{results['total']}, ошибок: {len(results['errors'])}"
        else:
            results["success"] = True
            results["message"] = f"Успешно удалено {len(results['deleted'])} клиентов"
        
        return results
    
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
        Получает клиента по email из соответствующего inbound по протоколу
        
        Args:
            email: Email клиента (формат: {location}@{protocol}&{username}&{code})
            
        Returns:
            Словарь с данными клиента и inbound_id или None
        """
        inbounds = await self.get_inbounds()
        if not inbounds:
            return None
        
        # Определяем протокол из email (формат: {location}@{protocol}&{username}&{code})
        target_protocol = None
        if "@vless&" in email:
            target_protocol = "vless"
        elif "@shadowsocks&" in email:
            target_protocol = "shadowsocks"
        elif "@vmess&" in email:
            target_protocol = "vmess"
        elif "@trojan&" in email:
            target_protocol = "trojan"
        
        # Ищем клиента только в инбаундах с соответствующим протоколом
        for inbound in inbounds:
            inbound_id = inbound.get("id")
            if not inbound_id:
                continue
            
            # Если определили протокол из email, проверяем что инбаунд соответствует
            inbound_protocol = inbound.get("protocol", "").lower()
            if target_protocol and inbound_protocol != target_protocol:
                continue
            
            # Парсим settings из JSON строки
            settings_str = inbound.get("settings", "{}")
            try:
                settings = json.loads(settings_str) if isinstance(settings_str, str) else settings_str
                clients = settings.get("clients", [])
                
                for client in clients:
                    if client.get("email") == email:
                        # Возвращаем клиента с информацией о inbound_id и протоколом
                        result = client.copy()
                        result["inbound_id"] = inbound_id
                        result["protocol"] = inbound_protocol
                        return result
            except (json.JSONDecodeError, TypeError):
                continue
        
        return None
    
    async def get_client_vless_link(
        self,
        client_email: str,
        client_username: str = None
    ) -> Optional[str]:
        """
        Генерирует VLESS ключ для клиента по новому шаблону:
        vless://{client_id}@{server_ip}:{inbound_port}?type={streamSettings_network}&encryption={settings_encryption}&security={streamSettings_security}&pbk={streamSettings_realitySettings_settings_publicKey}&fp={streamSettings_realitySettings_settings_fingerprint}&sni={streamSettings_realitySettings_serverNames[0]}&sid={streamSettings_realitySettings_shortIds[0]}&spx={streamSettings_realitySettings_settings_spiderX}&flow={client_flow}#{user_email}
        
        При наличии нескольких инбаундов выбирает инбаунд с протоколом vless.
        
        Args:
            client_email: Email клиента
            client_username: Username клиента (для отображения в конце ссылки, не используется)
            
        Returns:
            VLESS ссылка или None
        """
        # Получаем все инбаунды
        inbounds = await self.get_inbounds()
        if not inbounds:
            return None
        
        # Ищем клиента в vless инбаундах (приоритет)
        inbound = None
        client_id = None
        client_flow = ""
        
        logger.info(f"🔍 Поиск клиента {client_email} в vless инбаундах...")
        
        # Сначала ищем в vless инбаундах
        for inv in inbounds:
            protocol = inv.get("protocol", "").lower()
            if protocol != "vless":
                continue
            
            inbound_id = inv.get("id")
            if not inbound_id:
                continue
            
            # Парсим settings для поиска клиента
            settings_str = inv.get("settings", "{}")
            try:
                settings = json.loads(settings_str) if isinstance(settings_str, str) else settings_str
                clients = settings.get("clients", [])
                
                for client in clients:
                    if client.get("email") == client_email:
                        # Нашли клиента в vless инбаунде
                        client_id = client.get("id")
                        client_flow = client.get("flow", "")
                        inbound = inv
                        logger.info(f"✅ Клиент найден в vless инбаунде ID={inbound_id}, client_id={client_id}")
                        break
            except (json.JSONDecodeError, TypeError) as e:
                logger.debug(f"   Ошибка парсинга settings для инбаунда {inbound_id}: {e}")
                continue
            
            if inbound:
                break
        
        # Если клиент не найден в vless инбаундах, проверяем протокол из email
        if not inbound:
            # Определяем протокол из email (формат: {location}@{protocol}&{username}&{code})
            if "@shadowsocks&" in client_email:
                logger.debug(f"⚠️ Клиент {client_email} - Shadowsocks, VLESS ключ не может быть сгенерирован")
                return None
            elif "@vless&" not in client_email:
                logger.debug(f"⚠️ Клиент {client_email} не является VLESS клиентом, VLESS ключ не может быть сгенерирован")
                return None
            
            # Если это VLESS клиент, но не найден в vless инбаундах, ищем через get_client_by_email
            client = await self.get_client_by_email(client_email)
            if not client:
                logger.error(f"❌ Клиент {client_email} не найден ни в одном инбаунде")
                return None
            
            client_id = client.get("id")
            inbound_id = client.get("inbound_id")
            protocol = client.get("protocol", "").lower()
            
            if not inbound_id:
                logger.error(f"❌ У клиента {client_email} нет inbound_id")
                return None
            
            if protocol != "vless":
                logger.debug(f"⚠️ Клиент {client_email} находится в инбаунде с протоколом {protocol}, а не vless. VLESS ключ не может быть сгенерирован.")
                return None
            
            # Находим инбаунд
            for inv in inbounds:
                if inv.get("id") == inbound_id:
                    inbound = inv
                    break
            
            if not inbound:
                logger.error(f"❌ Inbound {inbound_id} не найден")
                return None
            
            if not client_id:
                logger.error(f"❌ У клиента {client_email} нет ID")
                return None
        
        if not inbound or not client_id:
            return None
        
        # Получаем порт из inbound
        port = inbound.get("port")
        if not port:
            return None
        
        # Парсим settings для получения encryption и flow клиента
        settings_str = inbound.get("settings", "{}")
        try:
            settings = json.loads(settings_str) if isinstance(settings_str, str) else settings_str
        except (json.JSONDecodeError, TypeError) as e:
            logger.error(f"❌ Ошибка парсинга settings: {e}")
            return None
        
        # Получаем encryption из settings
        encryption = settings.get("encryption", "none")
        
        # Если client_flow еще не установлен (fallback случай), ищем его в settings.clients
        if client_flow == "":
            clients_list = settings.get("clients", [])
            for client_item in clients_list:
                if client_item.get("email") == client_email or client_item.get("id") == client_id:
                    client_flow = client_item.get("flow", "")
                    break
        
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
        
        # Получаем settings внутри realitySettings
        reality_settings_inner = reality_settings.get("settings", {})
        
        # Получаем publicKey из realitySettings.settings.publicKey
        pbk = reality_settings_inner.get("publicKey") or ""
        
        # Получаем fingerprint из realitySettings.settings.fingerprint
        fingerprint = reality_settings_inner.get("fingerprint", "chrome")
        
        # Получаем spiderX из realitySettings.settings.spiderX
        spx = reality_settings_inner.get("spiderX", "/")
        
        # Получаем serverNames[0] из realitySettings.serverNames[0]
        server_names = reality_settings.get("serverNames", [])
        sni = server_names[0] if server_names and len(server_names) > 0 else ""
        
        # Получаем shortIds[0] из realitySettings.shortIds[0]
        short_ids = reality_settings.get("shortIds", [])
        sid_str = short_ids[0] if short_ids and len(short_ids) > 0 else ""
        
        # URL-кодируем spx если нужно
        if spx == "/":
            spx = "%2F"
        elif spx and not spx.startswith("%"):
            from urllib.parse import quote
            spx = quote(spx, safe='')
        
        # Логируем полученные параметры для отладки
        logger.info(f"📋 Параметры для VLESS ключа (новый шаблон):")
        logger.info(f"   Network: {network}, Security: {security}, Encryption: {encryption}")
        logger.info(f"   PBK: {pbk[:20] if pbk else 'N/A'}..., SID: {sid_str}, SNI: {sni}, SPX: {spx}")
        logger.info(f"   Fingerprint: {fingerprint}, Flow: '{client_flow}'")
        
        # Получаем IP адрес из api_url (извлекаем домен/IP)
        try:
            from urllib.parse import urlparse
            parsed_url = urlparse(self.api_url)
            server_ip = parsed_url.hostname or parsed_url.netloc.split(':')[0]
        except:
            # Если не удалось распарсить, используем дефолтное значение
            server_ip = "vpn-x3.ru"  # Fallback
        
        # Формируем VLESS ссылку по новому шаблону
        # vless://{client_id}@{server_ip}:{inbound_port}?type={streamSettings_network}&encryption={settings_encryption}&security={streamSettings_security}&pbk={streamSettings_realitySettings_settings_publicKey}&fp={streamSettings_realitySettings_settings_fingerprint}&sni={streamSettings_realitySettings_serverNames[0]}&sid={streamSettings_realitySettings_shortIds[0]}&spx={streamSettings_realitySettings_settings_spiderX}&flow={client_flow}#{user_email}
        vless_link = (
            f"vless://{client_id}@{server_ip}:{port}"
            f"?type={network}&encryption={encryption}&security={security}"
            f"&pbk={pbk}&fp={fingerprint}&sni={sni}&sid={sid_str}&spx={spx}"
            f"&flow={client_flow}#{client_email}"
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
    async def delete_client(self, client_email: str, max_retries: int = 3, retry_delay: float = 1.0) -> Optional[Dict[str, Any]]:
        """
        Удаляет клиента из 3x-ui с повторными попытками при ошибках соединения
        
        Args:
            client_email: Email клиента для удаления
            max_retries: Максимальное количество попыток
            retry_delay: Задержка между попытками в секундах
            
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
        
        inbound_id = client.get("inbound_id")
        if not inbound_id:
            return {"error": True, "message": "Не удалось получить ID inbound", "error_type": "invalid_client"}
        
        # Для Shadowsocks клиента может не быть поля id (UUID)
        # В этом случае используем email как идентификатор
        client_id = client.get("id")
        if not client_id:
            # Для Shadowsocks используем email как идентификатор
            client_id = client_email
        
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
        
        url = f"{self.api_url}/panel/api/inbounds/update/{inbound_id}"
        
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json"
        }
        
        logger.info(f"🗑️ Удаление клиента: {url}")
        logger.info(f"   Email: {client_email}")
        logger.info(f"   Client ID: {client_id}, Inbound ID: {inbound_id}")
        logger.info(f"   Request data: id={data1['id']}, settings length={len(data1['settings'])}")
        
        # Повторные попытки при ошибках соединения
        last_error = None
        for attempt in range(max_retries):
            try:
                # Пересоздаем сессию при ошибках соединения
                if attempt > 0:
                    # Закрываем старую сессию и пересоздаем
                    if self._session and not self._session.closed:
                        try:
                            await self._session.close()
                        except:
                            pass
                    self._session = None
                    self._authenticated = False
                    
                    # Повторная аутентификация
                    login_success = await self.login()
                    if not login_success:
                        logger.error(f"❌ Ошибка повторной аутентификации при попытке {attempt + 1}")
                        last_error = "Ошибка аутентификации"
                        if attempt < max_retries - 1:
                            await asyncio.sleep(retry_delay)
                        continue
                    
                    logger.info(f"🔄 Повторная попытка {attempt + 1}/{max_retries} удаления клиента {client_email}")
                    await asyncio.sleep(retry_delay)
                
                session = await self._get_session()
                
                # Добавляем таймаут для запроса
                timeout = aiohttp.ClientTimeout(total=30, connect=10)
                async with session.post(
                    url, 
                    headers=headers, 
                    json=data1,
                    allow_redirects=True,
                    max_redirects=10,
                    timeout=timeout
                ) as response:
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
            except asyncio.CancelledError:
                # При отмене задачи логируем и пробрасываем дальше
                logger.warning(f"⚠️ Запрос удаления клиента отменен: {client_email}")
                raise  # Пробрасываем CancelledError дальше
            except (aiohttp.ClientError, aiohttp.client_exceptions.ServerDisconnectedError, ConnectionError) as e:
                last_error = str(e)
                error_type = type(e).__name__
                logger.warning(f"⚠️ Ошибка соединения при удалении клиента {client_email} (попытка {attempt + 1}/{max_retries}): {error_type}: {e}")
                if attempt < max_retries - 1:
                    logger.info(f"⏳ Sleep for {retry_delay:.6f} seconds and try again... (tryings = {attempt}, bot id = {client_id})")
                    await asyncio.sleep(retry_delay)
                else:
                    logger.error(f"❌ Не удалось удалить клиента {client_email} после {max_retries} попыток: {last_error}")
            except asyncio.TimeoutError:
                last_error = "Таймаут запроса"
                logger.error(f"❌ Таймаут при удалении клиента: {client_email} (попытка {attempt + 1}/{max_retries})")
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay)
            except Exception as e:
                last_error = str(e)
                logger.error(f"❌ Ошибка при удалении клиента {client_email} (попытка {attempt + 1}/{max_retries}): {e}")
                import traceback
                logger.error(traceback.format_exc())
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay)
        
        # Если все попытки не удались
        return {"error": True, "status_code": None, "message": last_error or "Неизвестная ошибка", "error_type": "connection_error"}
    
    async def get_all_subscriptions(self) -> Optional[Dict[str, List[Dict[str, Any]]]]:
        """
        Получает все подписки с группировкой по subId.
        Проходит по всем inbounds, извлекает клиентов и группирует их по subId.
        
        Returns:
            Словарь, где ключ - subId, значение - список клиентов с информацией о inbound
            Или None в случае ошибки
        """
        # Убеждаемся, что мы аутентифицированы
        if not self._authenticated:
            login_success = await self.login()
            if not login_success:
                logger.error("❌ Ошибка аутентификации при получении подписок")
                return None
        
        # Получаем все inbounds
        inbounds = await self.get_inbounds()
        if not inbounds:
            logger.warning("⚠️ Не удалось получить список inbounds")
            return {}
        
        subscriptions: Dict[str, List[Dict[str, Any]]] = {}
        
        logger.info(f"📋 Обработка {len(inbounds)} inbounds для поиска подписок...")
        
        # Проходим по всем inbounds
        for inbound in inbounds:
            inbound_id = inbound.get("id")
            if not inbound_id:
                continue
            
            protocol = inbound.get("protocol", "").lower()
            tag = inbound.get("tag", "")
            
            logger.debug(f"   Обработка inbound #{inbound_id}: protocol={protocol}, tag={tag}")
            
            # Парсим settings для получения клиентов
            settings_str = inbound.get("settings", "{}")
            try:
                settings = json.loads(settings_str) if isinstance(settings_str, str) else settings_str
                clients = settings.get("clients", [])
                
                logger.debug(f"      Найдено клиентов в inbound #{inbound_id}: {len(clients)}")
                
                # Проходим по всем клиентам в этом inbound
                for client in clients:
                    # Получаем subId клиента (проверяем разные варианты написания)
                    sub_id = (client.get("subId") or 
                             client.get("sub_id") or 
                             client.get("subID") or 
                             client.get("SubId") or 
                             "")
                    
                    # Если subId пустой, пропускаем клиента (он не в подписке)
                    if not sub_id or str(sub_id).strip() == "":
                        continue
                    
                    # Убираем пробелы
                    sub_id = str(sub_id).strip()
                    
                    logger.debug(f"      Клиент {client.get('email', 'N/A')} имеет subId: {sub_id}")
                    
                    # Добавляем информацию о inbound к клиенту
                    client_with_inbound = client.copy()
                    client_with_inbound["inbound_id"] = inbound_id
                    client_with_inbound["inbound_protocol"] = protocol
                    client_with_inbound["inbound_tag"] = tag
                    
                    # Группируем клиентов по subId
                    if sub_id not in subscriptions:
                        subscriptions[sub_id] = []
                    
                    subscriptions[sub_id].append(client_with_inbound)
                    
            except (json.JSONDecodeError, TypeError) as e:
                logger.warning(f"⚠️ Ошибка парсинга settings для inbound {inbound_id}: {e}")
                continue
        
        logger.info(f"✅ Найдено {len(subscriptions)} уникальных подписок (subId)")
        for sub_id, clients in subscriptions.items():
            logger.debug(f"   SubId {sub_id}: {len(clients)} клиентов")
        
        return subscriptions
    
    async def get_subscription_by_sub_id(self, sub_id: str) -> Optional[List[Dict[str, Any]]]:
        """
        Получает подписку (всех клиентов) по subId.
        
        Args:
            sub_id: SubId подписки
            
        Returns:
            Список клиентов с информацией о inbound, или None если подписка не найдена или произошла ошибка аутентификации
        """
        if not sub_id:
            logger.warning("⚠️ SubId не указан")
            return None
        
        # Убеждаемся, что мы аутентифицированы
        if not self._authenticated:
            login_success = await self.login()
            if not login_success:
                logger.error(f"❌ Ошибка аутентификации при получении подписки с subID {sub_id}. Сервер может быть недоступен.")
                return None
        
        # Нормализуем subId (убираем пробелы, приводим к строке)
        sub_id_normalized = str(sub_id).strip()
        
        logger.info(f"🔍 Поиск подписки с subId: '{sub_id_normalized}'")
        logger.debug(f"   Исходный subId: '{sub_id}'")
        
        # Получаем все подписки
        all_subscriptions = await self.get_all_subscriptions()
        if not all_subscriptions:
            logger.warning(f"⚠️ Подписка с subId {sub_id_normalized} не найдена (нет подписок)")
            return None
        
        logger.debug(f"   Найдено подписок в системе: {len(all_subscriptions)}")
        logger.debug(f"   Доступные subId: {list(all_subscriptions.keys())}")
        
        # Ищем нужную подписку (сравниваем нормализованные значения)
        subscription = None
        for found_sub_id, clients in all_subscriptions.items():
            found_sub_id_normalized = str(found_sub_id).strip()
            # Сравниваем без учета регистра и пробелов
            if found_sub_id_normalized.lower() == sub_id_normalized.lower():
                subscription = clients
                logger.info(f"   ✅ Найдено совпадение: '{found_sub_id_normalized}' == '{sub_id_normalized}'")
                break
        
        if not subscription:
            logger.warning(f"⚠️ Подписка с subId '{sub_id_normalized}' не найдена")
            logger.warning(f"   Доступные subId для сравнения: {[str(sid).strip() for sid in all_subscriptions.keys()]}")
            return None
        
        logger.info(f"✅ Найдена подписка с subId {sub_id_normalized}: {len(subscription)} клиентов")
        return subscription
    
    async def get_client_keys_from_subscription(
        self,
        sub_id: str
    ) -> Optional[List[Dict[str, Any]]]:
        """
        Получает ключи (subscription links) для всех клиентов в подписке по subId.
        Использует шаблонный метод генерации VLESS ссылок.
        
        Args:
            sub_id: SubId подписки
            
        Returns:
            Список словарей с информацией о клиенте и его ключах
        """
        if not sub_id:
            logger.warning("⚠️ SubId не указан")
            return None
        
        # Получаем подписку по subId
        subscription = await self.get_subscription_by_sub_id(sub_id)
        if not subscription:
            logger.warning(f"⚠️ Не удалось получить подписку с subId {sub_id}")
            return None
        
        logger.info(f"🔑 Получение ключей для {len(subscription)} клиентов в подписке {sub_id}...")
        
        client_keys = []
        
        # Для каждого клиента получаем его ключи через шаблонный метод
        for client_data in subscription:
            client_email = client_data.get("email")
            inbound_id = client_data.get("inbound_id")
            inbound_protocol = client_data.get("inbound_protocol", "").lower()
            
            if not client_email:
                logger.warning("⚠️ У клиента нет email, пропускаем")
                continue
            
            logger.debug(f"   Получение ключа для клиента {client_email} (inbound {inbound_id})")
            
            # Генерируем VLESS ссылку только для VLESS клиентов
            vless_link = None
            if inbound_protocol == "vless":
                try:
                    vless_link = await self.get_client_vless_link(
                        client_email
                    )
                    if vless_link:
                        logger.debug(f"   ✅ Сгенерирован VLESS ключ для {client_email}")
                except Exception as e:
                    logger.warning(f"   ⚠️ Ошибка при генерации VLESS ключа для {client_email}: {e}")
            else:
                logger.debug(f"   ⚠️ Клиент {client_email} с протоколом {inbound_protocol}, VLESS ключ не генерируется")
            
            # Формируем результат для клиента
            client_key_info = {
                "client": client_data,
                "inbound_id": inbound_id,
                "inbound_protocol": inbound_protocol,
                "vless_link": vless_link,  # Сгенерированный ключ через шаблон
            }
            
            client_keys.append(client_key_info)
        
        logger.info(f"✅ Получено ключей для {len(client_keys)} клиентов в подписке {sub_id}")
        return client_keys
    
    async def close(self):
        """Закрыть сессию"""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None
            self._authenticated = False
        
        # Удаляем файл сертификата при закрытии (опционально, можно оставить для переиспользования)
        # if self._cert_file_path and os.path.exists(self._cert_file_path):
        #     try:
        #         os.unlink(self._cert_file_path)
        #     except:
        #         pass


def get_x3ui_client(api_url: str, username: str, password: str, ssl_certificate: Optional[str] = None) -> X3UIAPI:
    """
    Создает и возвращает клиент 3x-ui API
    
    Args:
        api_url: Полный URL сервера 3x-ui (может содержать WebBasePath)
        username: Имя пользователя для входа в панель
        password: Пароль для входа в панель
        ssl_certificate: SSL сертификат в формате PEM (опционально)
        
    Returns:
        Экземпляр X3UIAPI
    """
    return X3UIAPI(api_url, username, password, ssl_certificate)
