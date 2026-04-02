"""Сброс пароля существующего администратора (SSH на сервер, venv активен).

  python scripts/reset_admin_password.py
"""
import asyncio
import getpass
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


async def main():
    from sqlalchemy import select

    from admin.auth import hash_password
    from core.database import init_db, get_db_session
    from core.models import Admin

    print("\n" + "=" * 50)
    print("  MetaCleaner — сброс пароля администратора")
    print("=" * 50)
    await init_db()
    username = input("\nЛогин (существующий в БД): ").strip()
    if not username:
        print("❌ Логин пустой")
        sys.exit(1)
    password = getpass.getpass("Новый пароль: ")
    if len(password) < 6:
        print("❌ Минимум 6 символов")
        sys.exit(1)
    confirm = getpass.getpass("Повторите пароль: ")
    if password != confirm:
        print("❌ Пароли не совпадают")
        sys.exit(1)

    async with get_db_session() as session:
        r = await session.execute(select(Admin).where(Admin.username == username))
        admin = r.scalar_one_or_none()
        if not admin:
            print(f"❌ Администратор '{username}' не найден.")
            print("   Создайте нового: python scripts/create_admin.py")
            sys.exit(1)
        admin.password_hash = hash_password(password)
        admin.is_active = True
        await session.commit()

    print(f"\n✅ Пароль для '{username}' обновлён. Войдите в /admin/login\n")


if __name__ == "__main__":
    asyncio.run(main())
