import pytest
from core.platform_detect import detect_platform, is_supported_url

def test_detect_youtube():
    assert detect_platform("https://www.youtube.com/watch?v=dQw4w9WgXcQ") == "youtube"
    assert detect_platform("https://youtu.be/dQw4w9WgXcQ") == "youtube"
    assert detect_platform("https://youtube.com/shorts/some_id") == "youtube"

def test_detect_tiktok():
    assert detect_platform("https://www.tiktok.com/@user/video/1234567890") == "tiktok"
    assert detect_platform("https://vm.tiktok.com/ZSdfasdf/") == "tiktok"

def test_detect_instagram():
    assert detect_platform("https://www.instagram.com/reel/abcdefg/") == "instagram"
    assert detect_platform("https://instagram.com/p/abcdefg/") == "instagram"

def test_detect_twitter():
    assert detect_platform("https://twitter.com/user/status/1234567890") == "twitter"
    assert detect_platform("https://x.com/user/status/1234567890") == "twitter"

def test_detect_vk():
    assert detect_platform("https://vk.com/video-12345_67890") == "vk"
    assert detect_platform("https://vk.com/clip-123_456") == "vk"

def test_detect_facebook():
    assert detect_platform("https://www.facebook.com/watch/?v=1234567890") == "facebook"
    assert detect_platform("https://fb.watch/abcdefg/") == "facebook"

def test_detect_vimeo():
    assert detect_platform("https://vimeo.com/123456789") == "vimeo"

def test_detect_dailymotion():
    assert detect_platform("https://www.dailymotion.com/video/x7abcde") == "dailymotion"

def test_detect_unknown():
    assert detect_platform("https://example.com/video.mp4") == "unknown"

def test_is_supported_url():
    assert is_supported_url("https://youtu.be/abc") == True
    assert is_supported_url("https://example.com") == False
