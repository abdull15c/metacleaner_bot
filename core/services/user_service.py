from datetime import datetime, timedelta, timezone
from typing import Optional
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from core.models import User


class UserService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_or_create(self, telegram_id, username=None, first_name=None):
        result = await self.session.execute(select(User).where(User.telegram_id == telegram_id))
        user = result.scalar_one_or_none()
        if user is None:
            user = User(telegram_id=telegram_id, username=username, first_name=first_name,
                        daily_reset_at=datetime.now(timezone.utc))
            self.session.add(user)
            await self.session.flush()
            return user, True
        if username and user.username != username: user.username = username
        if first_name and user.first_name != first_name: user.first_name = first_name
        user.last_seen_at = datetime.now(timezone.utc)
        return user, False

    async def get_by_telegram_id(self, telegram_id) -> Optional[User]:
        r = await self.session.execute(select(User).where(User.telegram_id == telegram_id))
        return r.scalar_one_or_none()

    async def get_all_active_users(self):
        r = await self.session.execute(select(User).where(User.is_banned == False))
        return list(r.scalars().all())

    async def increment_daily_count(self, user, max_daily) -> bool:
        """
        Атомарный инкремент дневного счетчика с автоматическим сбросом.
        
        SECURITY FIX: Устранена race condition через атомарную операцию.
        """
        from sqlalchemy import update, case, or_, and_
        now = datetime.now(timezone.utc)
        reset_threshold = now - timedelta(days=1)
        
        # Атомарная операция: проверка + сброс + инкремент в одном UPDATE
        stmt = (
            update(User)
            .where(User.id == user.id)
            .where(
                # Условие: счетчик не превышен ИЛИ нужен сброс
                or_(
                    and_(
                        User.daily_job_count < max_daily,
                        User.daily_reset_at > reset_threshold
                    ),
                    User.daily_reset_at <= reset_threshold,
                    User.daily_reset_at.is_(None)
                )
            )
            .values(
                daily_job_count=case(
                    # Если нужен сброс - установить 1
                    (
                        or_(
                            User.daily_reset_at <= reset_threshold,
                            User.daily_reset_at.is_(None)
                        ),
                        1
                    ),
                    # Иначе инкремент
                    else_=User.daily_job_count + 1
                ),
                daily_reset_at=case(
                    # Если нужен сброс - установить now
                    (
                        or_(
                            User.daily_reset_at <= reset_threshold,
                            User.daily_reset_at.is_(None)
                        ),
                        now
                    ),
                    # Иначе оставить как есть
                    else_=User.daily_reset_at
                )
            )
            .returning(User.daily_job_count, User.daily_reset_at)
        )
        
        result = await self.session.execute(stmt)
        row = result.one_or_none()
        
        if row is None:
            # Лимит превышен
            return False
        
        # Обновить объект в памяти
        user.daily_job_count = row[0]
        user.daily_reset_at = row[1]
        
        return True

    async def rollback_daily_job_increment(self, user) -> None:
        if user.daily_job_count and user.daily_job_count > 0:
            user.daily_job_count -= 1

    async def get_by_id(self, user_id) -> Optional[User]:
        return await self.session.get(User, user_id)

    async def delete_me(self, telegram_id) -> bool:
        u = await self.get_by_telegram_id(telegram_id)
        if not u: return False
        
        from sqlalchemy import update
        from core.models import Job
        await self.session.execute(
            update(Job).where(Job.user_id == u.id).values(cleanup_done=True)
        )
        
        await self.session.delete(u)
        return True

    async def ban_user(self, telegram_id) -> bool:
        u = await self.get_by_telegram_id(telegram_id)
        if not u: return False
        u.is_banned = True; return True

    async def unban_user(self, telegram_id) -> bool:
        u = await self.get_by_telegram_id(telegram_id)
        if not u: return False
        u.is_banned = False; return True

    async def count_total(self) -> int:
        r = await self.session.execute(select(func.count(User.id)))
        return r.scalar() or 0

    async def count_active_today(self) -> int:
        cutoff = datetime.now(timezone.utc) - timedelta(days=1)
        r = await self.session.execute(select(func.count(User.id)).where(User.last_seen_at >= cutoff))
        return r.scalar() or 0
