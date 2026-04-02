import asyncio, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


async def main():
    from core.database import init_db, get_db_session
    from core.services.settings_service import SettingsService
    await init_db()
    async with get_db_session() as session:
        await SettingsService(session).seed_defaults()
        await session.commit()
    print("✓ Настройки по умолчанию заполнены")


asyncio.run(main())
