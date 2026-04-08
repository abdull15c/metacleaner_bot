import re

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
