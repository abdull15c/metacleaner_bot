#!/usr/bin/env python3
"""
Health check скрипт для мониторинга состояния MetaCleaner Bot.
Проверяет все критические компоненты системы.
"""
import asyncio
import sys
import os
from pathlib import Path

# Добавить корень проекта в PYTHONPATH
sys.path.insert(0, str(Path(__file__).parent.parent))

from datetime import datetime, timedelta, timezone


class HealthChecker:
    """Проверка здоровья всех компонентов системы."""
    
    def __init__(self):
        self.checks = []
        self.failed = []
    
    async def check_database(self) -> bool:
        """Проверка подключения к БД."""
        try:
            from core.database import engine
            from sqlalchemy import text
            
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            
            self.checks.append(("Database", "OK", "Connected"))
            return True
        except Exception as e:
            self.checks.append(("Database", "FAIL", str(e)[:100]))
            self.failed.append("database")
            return False
    
    async def check_redis(self) -> bool:
        """Проверка подключения к Redis."""
        try:
            import redis.asyncio as aioredis
            from core.config import settings
            
            r = aioredis.from_url(str(settings.redis_url))
            await r.ping()
            await r.close()
            
            self.checks.append(("Redis", "OK", "Connected"))
            return True
        except Exception as e:
            self.checks.append(("Redis", "FAIL", str(e)[:100]))
            self.failed.append("redis")
            return False
    
    async def check_celery_workers(self) -> bool:
        """Проверка Celery воркеров."""
        try:
            from workers.celery_app import app
            
            # Проверка активных воркеров
            inspect = app.control.inspect()
            active = inspect.active()
            
            if not active:
                self.checks.append(("Celery Workers", "WARN", "No active workers"))
                return True  # Не критично для health check
            
            worker_count = len(active)
            self.checks.append(("Celery Workers", "OK", f"{worker_count} workers active"))
            return True
        except Exception as e:
            self.checks.append(("Celery Workers", "FAIL", str(e)[:100]))
            self.failed.append("celery")
            return False
    
    async def check_disk_space(self) -> bool:
        """Проверка свободного места на диске."""
        try:
            import shutil
            from core.config import settings
            
            usage = shutil.disk_usage(settings.temp_upload_dir)
            free_percent = (usage.free / usage.total) * 100
            free_gb = usage.free / (1024**3)
            
            if free_percent < 10:
                self.checks.append(("Disk Space", "CRITICAL", f"{free_percent:.1f}% free ({free_gb:.1f} GB)"))
                self.failed.append("disk_space")
                return False
            elif free_percent < 20:
                self.checks.append(("Disk Space", "WARN", f"{free_percent:.1f}% free ({free_gb:.1f} GB)"))
                return True
            else:
                self.checks.append(("Disk Space", "OK", f"{free_percent:.1f}% free ({free_gb:.1f} GB)"))
                return True
        except Exception as e:
            self.checks.append(("Disk Space", "FAIL", str(e)[:100]))
            return False
    
    async def check_temp_files(self) -> bool:
        """Проверка размера temp директории."""
        try:
            from storage.local import storage
            
            temp_size_mb = storage.temp_total_size_mb()
            
            if temp_size_mb > 10000:  # 10GB
                self.checks.append(("Temp Files", "WARN", f"{temp_size_mb:.1f} MB (>10GB)"))
            else:
                self.checks.append(("Temp Files", "OK", f"{temp_size_mb:.1f} MB"))
            
            return True
        except Exception as e:
            self.checks.append(("Temp Files", "FAIL", str(e)[:100]))
            return False
    
    async def check_stuck_jobs(self) -> bool:
        """Проверка зависших задач."""
        try:
            from core.database import get_db_session
            from core.models import Job, JobStatus
            from sqlalchemy import select, and_
            
            stuck_threshold = datetime.now(timezone.utc) - timedelta(hours=2)
            
            async with get_db_session() as session:
                # Pending jobs старше 2 часов
                pending_stmt = select(Job).where(
                    and_(
                        Job.status == JobStatus.pending,
                        Job.created_at < stuck_threshold
                    )
                )
                pending_result = await session.execute(pending_stmt)
                stuck_pending = len(list(pending_result.scalars().all()))
                
                # Processing jobs старше 2 часов
                processing_stmt = select(Job).where(
                    and_(
                        Job.status.in_([JobStatus.processing, JobStatus.downloading]),
                        Job.started_at < stuck_threshold
                    )
                )
                processing_result = await session.execute(processing_stmt)
                stuck_processing = len(list(processing_result.scalars().all()))
                
                total_stuck = stuck_pending + stuck_processing
                
                if total_stuck > 0:
                    self.checks.append(("Stuck Jobs", "WARN", f"{total_stuck} jobs stuck (pending: {stuck_pending}, processing: {stuck_processing})"))
                else:
                    self.checks.append(("Stuck Jobs", "OK", "No stuck jobs"))
                
                return True
        except Exception as e:
            self.checks.append(("Stuck Jobs", "FAIL", str(e)[:100]))
            return False
    
    async def check_recent_errors(self) -> bool:
        """Проверка недавних ошибок."""
        try:
            from core.database import get_db_session
            from core.models import Job, JobStatus
            from sqlalchemy import select, func
            
            cutoff = datetime.now(timezone.utc) - timedelta(hours=1)
            
            async with get_db_session() as session:
                stmt = select(func.count(Job.id)).where(
                    and_(
                        Job.status == JobStatus.failed,
                        Job.created_at >= cutoff
                    )
                )
                result = await session.execute(stmt)
                error_count = result.scalar() or 0
                
                if error_count > 10:
                    self.checks.append(("Recent Errors", "WARN", f"{error_count} errors in last hour"))
                else:
                    self.checks.append(("Recent Errors", "OK", f"{error_count} errors in last hour"))
                
                return True
        except Exception as e:
            self.checks.append(("Recent Errors", "FAIL", str(e)[:100]))
            return False
    
    async def run_all_checks(self) -> bool:
        """Запустить все проверки."""
        print("=" * 60)
        print("MetaCleaner Bot - Health Check")
        print(f"Timestamp: {datetime.now(timezone.utc).isoformat()}")
        print("=" * 60)
        print()
        
        # Запуск всех проверок
        await self.check_database()
        await self.check_redis()
        await self.check_celery_workers()
        await self.check_disk_space()
        await self.check_temp_files()
        await self.check_stuck_jobs()
        await self.check_recent_errors()
        
        # Вывод результатов
        print(f"{'Component':<20} {'Status':<10} {'Details'}")
        print("-" * 60)
        
        for component, status, details in self.checks:
            status_symbol = {
                "OK": "✓",
                "WARN": "⚠",
                "FAIL": "✗",
                "CRITICAL": "✗✗"
            }.get(status, "?")
            
            print(f"{component:<20} {status_symbol} {status:<8} {details}")
        
        print()
        print("=" * 60)
        
        if self.failed:
            print(f"FAILED: {', '.join(self.failed)}")
            print("=" * 60)
            return False
        else:
            print("ALL CHECKS PASSED")
            print("=" * 60)
            return True


async def main():
    """Главная функция."""
    checker = HealthChecker()
    success = await checker.run_all_checks()
    
    # Exit code для мониторинга
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    asyncio.run(main())
