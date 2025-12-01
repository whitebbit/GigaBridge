"""
Утилиты для парсинга и форматирования URL Hiddify API
"""
from urllib.parse import urlparse
from typing import Tuple, Optional


def parse_hiddify_url(full_url: str) -> Tuple[str, Optional[str]]:
    """
    Парсит полный URL Hiddify на базовый URL и proxy_path
    
    Args:
        full_url: Полный URL (например, https://89.169.7.60/iewGvZ4ifCI6xh4rU0yJUXH2)
        
    Returns:
        Кортеж (base_url, proxy_path), где:
        - base_url: Базовый URL (например, https://89.169.7.60)
        - proxy_path: Proxy path (например, iewGvZ4ifCI6xh4rU0yJUXH2) или None
    """
    full_url = full_url.strip().rstrip('/')
    
    # Парсим URL
    parsed = urlparse(full_url)
    
    # Базовый URL - это схема + host + port (если есть)
    base_url = f"{parsed.scheme}://{parsed.netloc}"
    
    # Путь после первого слеша - это proxy_path
    path = parsed.path.lstrip('/')
    
    if path:
        # Берем первую часть пути как proxy_path
        # Например, из /iewGvZ4ifCI6xh4rU0yJUXH2/api/v2 берем iewGvZ4ifCI6xh4rU0yJUXH2
        path_parts = path.split('/')
        proxy_path = path_parts[0] if path_parts[0] else None
    else:
        proxy_path = None
    
    return base_url, proxy_path


def build_hiddify_url(base_url: str, proxy_path: Optional[str] = None) -> str:
    """
    Собирает полный URL Hiddify из базового URL и proxy_path
    
    Args:
        base_url: Базовый URL (например, https://89.169.7.60)
        proxy_path: Proxy path (например, iewGvZ4ifCI6xh4rU0yJUXH2) или None
        
    Returns:
        Полный URL (например, https://89.169.7.60/iewGvZ4ifCI6xh4rU0yJUXH2)
    """
    base_url = base_url.strip().rstrip('/')
    
    if proxy_path:
        proxy_path = proxy_path.strip().lstrip('/').rstrip('/')
        return f"{base_url}/{proxy_path}"
    else:
        return base_url


def get_full_api_url(api_url: str, proxy_path: Optional[str] = None) -> str:
    """
    Получить полный URL для API запросов (включая /api/v2 если нужно)
    Удобная функция для использования в сервисе Hiddify API
    
    Args:
        api_url: Базовый URL
        proxy_path: Proxy path или None
        
    Returns:
        Полный URL с proxy_path (если указан)
    """
    return build_hiddify_url(api_url, proxy_path)

