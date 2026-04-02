import subprocess, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

G="[92m✓[0m"; R="[91m✗[0m"; Y="[93m![0m"
ok=True


def chk(name, fn):
    global ok
    try:
        result = fn()
        print(f"  {G}  {name}: {result}")
    except Exception as e:
        print(f"  {R}  {name}: {e}"); ok = False


def ffmpeg():
    r = subprocess.run(["ffmpeg","-version"], capture_output=True, text=True, timeout=5)
    if r.returncode != 0: raise Exception("non-zero exit")
    return r.stdout.split("\n")[0]


def redis_check():
    import redis
    from core.config import settings
    r = redis.from_url(settings.redis_url, socket_timeout=3); r.ping(); return settings.redis_url


def env_check():
    from core.config import settings
    if "your_bot_token" in settings.bot_token: raise Exception("BOT_TOKEN not set")
    return f"...{settings.bot_token[-6:]}"


print("\nMetaCleaner Bot — Pre-flight Check")
print("="*40)
def python_311_plus():
    if sys.version_info < (3, 11):
        raise Exception(f"need Python 3.11+, got {sys.version_info.major}.{sys.version_info.minor}")
    return f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"


chk("Python 3.11+", python_311_plus)
chk("FFmpeg",       ffmpeg)
chk("Redis",        redis_check)
chk(".env/token",   env_check)
print("="*40)
if ok:
    print("[92m✓ Всё готово к запуску![0m\n")
else:
    print("[91m✗ Исправьте ошибки выше.[0m\n"); sys.exit(1)
