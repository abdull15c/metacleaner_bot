"""
URL валидация для защиты от SSRF атак.
"""
import ipaddress
import logging
from urllib.parse import urlparse
from typing import Optional

logger = logging.getLogger(__name__)

# Whitelist доменов для скачивания
ALLOWED_DOMAINS = {
    # YouTube
    "youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be",
    # Instagram
    "instagram.com", "www.instagram.com",
    # TikTok
    "tiktok.com", "www.tiktok.com", "vm.tiktok.com",
    # Facebook
    "facebook.com", "www.facebook.com", "fb.watch",
    # Twitter/X
    "twitter.com", "www.twitter.com", "x.com", "www.x.com",
    # Vimeo
    "vimeo.com", "www.vimeo.com",
    # Dailymotion
    "dailymotion.com", "www.dailymotion.com", "dai.ly",
}

# Private IP ranges (RFC 1918, RFC 4193, loopback)
PRIVATE_IP_RANGES = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),  # Link-local
    ipaddress.ip_network("::1/128"),  # IPv6 loopback
    ipaddress.ip_network("fc00::/7"),  # IPv6 private
    ipaddress.ip_network("fe80::/10"),  # IPv6 link-local
]


class InvalidURLError(Exception):
    """URL не прошел валидацию безопасности."""
    pass


def is_private_ip(ip_str: str) -> bool:
    """Проверка, является ли IP приватным."""
    try:
        ip = ipaddress.ip_address(ip_str)
        return any(ip in network for network in PRIVATE_IP_RANGES)
    except ValueError:
        return False


def validate_download_url(url: str, platform: Optional[str] = None) -> str:
    """
    Валидация URL для защиты от SSRF.
    
    Args:
        url: URL для проверки
        platform: Платформа (youtube, instagram, tiktok, facebook)
    
    Returns:
        Нормализованный URL
        
    Raises:
        InvalidURLError: Если URL не прошел валидацию
    """
    if not url or not isinstance(url, str):
        raise InvalidURLError("URL не может быть пустым")
    
    url = url.strip()
    
    # Проверка длины
    if len(url) > 2048:
        raise InvalidURLError("URL слишком длинный")
    
    # Парсинг URL
    try:
        parsed = urlparse(url)
    except Exception as e:
        logger.warning(f"Failed to parse URL: {e}")
        raise InvalidURLError("Некорректный формат URL")
    
    # Проверка схемы
    if parsed.scheme not in ("http", "https"):
        raise InvalidURLError(f"Недопустимая схема: {parsed.scheme}. Разрешены только http/https")
    
    # Проверка наличия хоста
    if not parsed.netloc:
        raise InvalidURLError("URL должен содержать домен")
    
    # Извлечение домена (без порта)
    hostname = parsed.hostname
    if not hostname:
        raise InvalidURLError("Не удалось извлечь hostname из URL")
    
    hostname_lower = hostname.lower()
    
    # Проверка на localhost
    if hostname_lower in ("localhost", "0.0.0.0"):
        raise InvalidURLError("Доступ к localhost запрещен")
    
    # Проверка на IP адрес
    try:
        ip = ipaddress.ip_address(hostname)
        if is_private_ip(str(ip)):
            raise InvalidURLError("Доступ к приватным IP адресам запрещен")
        # Разрешаем публичные IP (для CDN и т.д.)
        logger.info(f"URL contains public IP: {ip}")
    except ValueError:
        # Это домен, не IP - продолжаем проверку
        pass
    
    # Проверка whitelist доменов
    domain_allowed = False
    for allowed in ALLOWED_DOMAINS:
        if hostname_lower == allowed or hostname_lower.endswith(f".{allowed}"):
            domain_allowed = True
            break
    
    if not domain_allowed:
        raise InvalidURLError(
            f"Домен {hostname} не в whitelist. "
            f"Поддерживаются: YouTube, Instagram, TikTok, Facebook, Twitter, Vimeo, Dailymotion"
        )
    
    # Проверка порта (если указан)
    if parsed.port:
        if parsed.port not in (80, 443, 8080, 8443):
            raise InvalidURLError(f"Недопустимый порт: {parsed.port}")
    
    # Дополнительная проверка для конкретных платформ
    if platform == "youtube":
        if not any(d in hostname_lower for d in ["youtube.com", "youtu.be"]):
            raise InvalidURLError("Для YouTube используйте ссылки youtube.com или youtu.be")
    
    logger.info(f"URL validation passed: {hostname}")
    return url


def sanitize_url_for_logging(url: str) -> str:
    """
    Удаляет чувствительные параметры из URL для безопасного логирования.
    
    Args:
        url: Исходный URL
        
    Returns:
        URL без токенов и паролей
    """
    try:
        parsed = urlparse(url)
        # Возвращаем только схему, хост и путь
        return f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
    except Exception:
        return "[invalid_url]"
