import asyncio, sys, os, getpass
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


async def main():
    from core.database import init_db, get_db_session
    from core.models import Admin
    from admin.auth import hash_password
    from sqlalchemy import select
    print("\n" + "="*50)
    print("  MetaCleaner Bot — Создание администратора")
    print("="*50)
    await init_db()
    username = input("\nЛогин: ").strip()
    if not username: print("❌ Логин не может быть пустым"); sys.exit(1)
    password = getpass.getpass("Пароль: ")
    if len(password) < 6: print("❌ Минимум 6 символов"); sys.exit(1)
    confirm = getpass.getpass("Подтвердите пароль: ")
    if password != confirm: print("❌ Пароли не совпадают"); sys.exit(1)
    async with get_db_session() as session:
        r = await session.execute(select(Admin).where(Admin.username == username))
        if r.scalar_one_or_none(): print(f"❌ Администратор '{username}' уже существует"); sys.exit(1)
        session.add(Admin(username=username, password_hash=hash_password(password), is_active=True))
        await session.commit()
    from core.config import settings
    h = settings.admin_host
    if h in ("0.0.0.0", "::", "[::]"):
        h = "127.0.0.1"
    print(f"\n✅ Администратор '{username}' создан!")
    print(f"   Панель: http://{h}:{settings.admin_port}/admin/login\n")


asyncio.run(main())
