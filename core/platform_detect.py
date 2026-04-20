import ipaddress
import socket
from urllib.parse import urlparse

# Блокируемые схемы протоколов
BLOCKED_SCHEMES = {'file', 'ftp', 'gopher', 'data', 'javascript', 'about', 'blob'}

# Приватные IP диапазоны
PRIVATE_RANGES = [
    ipaddress.ip_network('10.0.0.0/8'),
    ipaddress.ip_network('172.16.0.0/12'),
    ipaddress.ip_network('192.168.0.0/16'),
    ipaddress.ip_network('127.0.0.0/8'),
    ipaddress.ip_network('169.254.0.0/16'),
    ipaddress.ip_network('::1/128'),  # IPv6 localhost
    ipaddress.ip_network('fc00::/7'),  # IPv6 private
]


def _is_blocked_ip(ip: ipaddress._BaseAddress) -> bool:
    for private_range in PRIVATE_RANGES:
        if ip in private_range:
            return True
    return bool(
        ip.is_link_local or
        ip.is_multicast or
        ip.is_loopback or
        ip.is_reserved or
        ip.is_unspecified
    )


def _resolve_host_ips(hostname: str) -> set[ipaddress._BaseAddress]:
    resolved_ips: set[ipaddress._BaseAddress] = set()
    infos = socket.getaddrinfo(hostname, None, proto=socket.IPPROTO_TCP)
    for family, _, _, _, sockaddr in infos:
        if family == socket.AF_INET:
            resolved_ips.add(ipaddress.ip_address(sockaddr[0]))
        elif family == socket.AF_INET6:
            resolved_ips.add(ipaddress.ip_address(sockaddr[0]))
    return resolved_ips

def validate_url_security(url: str) -> tuple[bool, str]:
    """
    Проверка URL на SSRF и другие атаки.
    
    Returns:
        (is_valid, error_message)
    """
    if not url or not url.strip():
        return False, "Empty URL"
    
    url = url.strip()
    
    # Проверка длины
    if len(url) > 2048:
        return False, "URL too long (max 2048 chars)"
    
    try:
        parsed = urlparse(url.lower())
        
        # Проверка схемы
        if not parsed.scheme:
            return False, "Missing URL scheme (http/https required)"
        
        if parsed.scheme not in ('http', 'https'):
            if parsed.scheme in BLOCKED_SCHEMES:
                return False, f"Blocked scheme: {parsed.scheme}"
            return False, "Only HTTP/HTTPS allowed"
        
        # Проверка хоста
        if not parsed.netloc:
            return False, "Invalid URL: no host"
        
        # Извлечь hostname без порта
        hostname = parsed.hostname
        if not hostname:
            return False, "Invalid hostname"
        
        # Блокировка localhost
        if hostname in ('localhost', '0.0.0.0', '127.0.0.1', '::1'):
            return False, "Localhost access denied"
        
        # Проверка IP-адресов
        try:
            ip = ipaddress.ip_address(hostname)
            if _is_blocked_ip(ip):
                return False, f"Blocked IP type: {ip}"
        except ValueError:
            try:
                resolved_ips = _resolve_host_ips(hostname)
            except socket.gaierror:
                return False, "Hostname resolution failed"

            if not resolved_ips:
                return False, "Hostname did not resolve to any IP"

            for resolved_ip in resolved_ips:
                if _is_blocked_ip(resolved_ip):
                    return False, f"Resolved to blocked IP: {resolved_ip}"

        return True, "OK"
        
    except Exception as e:
        return False, f"URL validation error: {str(e)}"

def detect_platform(url: str) -> str:
    url = url.lower()
    if "youtube.com" in url or "youtu.be" in url:
        return "youtube"
    elif "tiktok.com" in url:
        return "tiktok"
    elif "instagram.com" in url:
        return "instagram"
    elif "twitter.com" in url or "x.com" in url:
        return "twitter"
    elif "vk.com/video" in url or "vk.com/clip" in url:
        return "vk"
    elif "facebook.com" in url or "fb.watch" in url:
        return "facebook"
    elif "vimeo.com" in url:
        return "vimeo"
    elif "dailymotion.com" in url:
        return "dailymotion"
    return "unknown"

def is_supported_url(url: str) -> bool:
    return detect_platform(url) != "unknown"
