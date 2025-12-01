"""
Утилиты для парсинга URL 3x-ui API
"""
from urllib.parse import urlparse, urlunparse


def parse_x3ui_api_url(full_url: str) -> str:
    """
    Парсит полный URL 3x-ui и извлекает базовый URL для API
    
    Согласно документации 3x-ui, API доступен напрямую на порту панели (обычно 2053),
    а не через WebBasePath. WebBasePath используется только для веб-интерфейса.
    
    Примеры:
    - http://89.169.7.60:443/GPqoKweuuRVv6bcIKB -> http://89.169.7.60:2053
    - https://89.169.7.60:443/GPqoKweuuRVv6bcIKB -> https://89.169.7.60:2053
    - http://89.169.7.60:2053 -> http://89.169.7.60:2053
    - https://domain.com:2053 -> https://domain.com:2053
    
    Args:
        full_url: Полный URL (может содержать WebBasePath)
        
    Returns:
        Базовый URL для API (без WebBasePath, с портом 2053 по умолчанию)
    """
    parsed = urlparse(full_url)
    
    # Извлекаем схему и хост
    scheme = parsed.scheme or "http"
    hostname = parsed.hostname or parsed.netloc.split(":")[0] if ":" in parsed.netloc else parsed.netloc
    
    # Определяем порт
    # Если порт указан в URL, используем его (даже если это нестандартный порт)
    # Если порт 443 или 80, это может быть веб-интерфейс через reverse proxy
    # В этом случае меняем на стандартный порт панели 3x-ui (2053)
    # Если порт не указан, используем 2053
    if parsed.port:
        port = parsed.port
        # Если порт 443 или 80, это может быть веб-интерфейс через reverse proxy
        # Меняем на стандартный порт панели 3x-ui (2053)
        # Но если указан другой порт (например, 30648), оставляем его как есть
        if port in [443, 80]:
            port = 2053
        # Иначе используем указанный порт (может быть любой порт, на котором работает панель)
    else:
        # Если порт не указан, используем стандартный порт панели 3x-ui
        port = 2053
    
    # Формируем базовый URL без пути (WebBasePath игнорируется)
    base_url = f"{scheme}://{hostname}:{port}"
    
    return base_url

