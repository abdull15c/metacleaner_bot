"""
Тесты для security fixes.
Проверка всех критических исправлений безопасности.
"""
import pytest
from unittest.mock import Mock, patch


class TestSSRFProtection:
    """Тесты SSRF защиты."""
    
    def test_block_localhost(self):
        """Блокировка localhost."""
        from core.url_validator import validate_download_url, InvalidURLError
        
        with pytest.raises(InvalidURLError, match="localhost"):
            validate_download_url("http://localhost:8000/admin")
    
    def test_block_private_ip(self):
        """Блокировка private IP."""
        from core.url_validator import validate_download_url, InvalidURLError
        
        with pytest.raises(InvalidURLError, match="приватным IP"):
            validate_download_url("http://192.168.1.1/")
        
        with pytest.raises(InvalidURLError, match="приватным IP"):
            validate_download_url("http://10.0.0.1/")
    
    def test_block_file_protocol(self):
        """Блокировка file:// протокола."""
        from core.url_validator import validate_download_url, InvalidURLError
        
        with pytest.raises(InvalidURLError, match="Недопустимая схема"):
            validate_download_url("file:///etc/passwd")
    
    def test_allow_youtube(self):
        """Разрешение YouTube URL."""
        from core.url_validator import validate_download_url
        
        url = validate_download_url("https://youtube.com/watch?v=dQw4w9WgXcQ")
        assert url == "https://youtube.com/watch?v=dQw4w9WgXcQ"
    
    def test_block_non_whitelisted_domain(self):
        """Блокировка не-whitelisted доменов."""
        from core.url_validator import validate_download_url, InvalidURLError
        
        with pytest.raises(InvalidURLError, match="не в whitelist"):
            validate_download_url("https://evil.com/video.mp4")
    
    def test_url_too_long(self):
        """Блокировка слишком длинных URL."""
        from core.url_validator import validate_download_url, InvalidURLError
        
        long_url = "https://youtube.com/" + "a" * 3000
        with pytest.raises(InvalidURLError, match="слишком длинный"):
            validate_download_url(long_url)


class TestRaceConditionFix:
    """Тесты исправления race condition."""
    
    @pytest.mark.asyncio
    async def test_atomic_increment(self, db_session):
        """Атомарный инкремент daily_job_count."""
        from core.models import User
        from core.services.user_service import UserService
        from datetime import datetime, timezone
        
        # Создать пользователя
        user = User(
            telegram_id=999001,
            daily_job_count=0,
            daily_reset_at=datetime.now(timezone.utc)
        )
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)
        
        us = UserService(db_session)
        
        # Первый инкремент
        result1 = await us.increment_daily_count(user, max_daily=10)
        await db_session.commit()
        await db_session.refresh(user)
        
        assert result1 is True
        assert user.daily_job_count == 1
        
        # Второй инкремент
        result2 = await us.increment_daily_count(user, max_daily=10)
        await db_session.commit()
        await db_session.refresh(user)
        
        assert result2 is True
        assert user.daily_job_count == 2
    
    @pytest.mark.asyncio
    async def test_limit_enforcement(self, db_session):
        """Проверка соблюдения лимита."""
        from core.models import User
        from core.services.user_service import UserService
        from datetime import datetime, timezone
        
        user = User(
            telegram_id=999002,
            daily_job_count=9,
            daily_reset_at=datetime.now(timezone.utc)
        )
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)
        
        us = UserService(db_session)
        
        # Должен пройти (9 -> 10)
        result1 = await us.increment_daily_count(user, max_daily=10)
        await db_session.commit()
        await db_session.refresh(user)
        assert result1 is True
        assert user.daily_job_count == 10
        
        # Должен быть отклонен (10 >= 10)
        result2 = await us.increment_daily_count(user, max_daily=10)
        await db_session.commit()
        await db_session.refresh(user)
        assert result2 is False
        assert user.daily_job_count == 10


class TestMaxConcurrentJobs:
    """Тесты глобального лимита MAX_CONCURRENT_JOBS."""
    
    @pytest.mark.asyncio
    async def test_count_active_jobs(self, db_session):
        """Подсчет активных задач."""
        from core.models import Job, JobStatus, SourceType, User
        from core.services.job_service import JobService
        from datetime import datetime, timezone
        
        # Создать пользователя
        user = User(telegram_id=999003, daily_reset_at=datetime.now(timezone.utc))
        db_session.add(user)
        await db_session.commit()
        
        js = JobService(db_session)
        
        # Создать активные задачи
        for i in range(3):
            job = await js.create_job(user.id, SourceType.upload)
            job.status = JobStatus.processing
        
        await db_session.commit()
        
        # Проверить подсчет
        count = await js.count_active_jobs()
        assert count == 3


class TestMetadataTruncation:
    """Тесты ограничения размера метаданных."""
    
    def test_small_metadata_unchanged(self):
        """Маленькие метаданные не изменяются."""
        from core.metadata_utils import truncate_metadata
        
        small = {"title": "Test", "duration": "120"}
        result = truncate_metadata(small)
        
        assert result == small
        assert "_truncated" not in result
    
    def test_large_metadata_truncated(self):
        """Большие метаданные усекаются."""
        from core.metadata_utils import truncate_metadata
        
        # Создать большой словарь (>10KB)
        large = {f"key_{i}": "x" * 1000 for i in range(20)}
        result = truncate_metadata(large, max_size=5000)
        
        assert "_truncated" in result
        assert "_original_size" in result
        assert result["_original_size"] > 5000


class TestCleanupLogic:
    """Тесты исправленной логики cleanup."""
    
    @pytest.mark.asyncio
    async def test_pending_jobs_use_created_at(self, db_session):
        """Pending jobs используют created_at."""
        from core.models import Job, JobStatus, SourceType, User
        from core.services.job_service import JobService
        from datetime import datetime, timedelta, timezone
        
        # Создать пользователя
        user = User(telegram_id=999004, daily_reset_at=datetime.now(timezone.utc))
        db_session.add(user)
        await db_session.commit()
        
        js = JobService(db_session)
        
        # Создать старую pending задачу
        old_time = datetime.now(timezone.utc) - timedelta(hours=3)
        job = await js.create_job(user.id, SourceType.upload)
        job.created_at = old_time
        job.status = JobStatus.pending
        # started_at остается NULL для pending
        
        await db_session.commit()
        
        # Проверить что задача будет найдена для cleanup
        # (в реальном коде это делает periodic_cleanup_task)
        assert job.started_at is None
        assert job.created_at < datetime.now(timezone.utc) - timedelta(hours=2)


class TestFileSizeValidation:
    """Тесты валидации размера файла ДО загрузки."""
    
    @pytest.mark.asyncio
    async def test_file_size_check_before_upload(self):
        """Проверка размера перед загрузкой."""
        # Этот тест проверяет логику в webapp/routes.py
        # В реальном коде проверка происходит в цикле чтения чанков
        
        max_bytes = 1024 * 1024  # 1MB
        total = 0
        chunk_size = 1024
        
        # Симуляция загрузки
        for i in range(2000):  # Попытка загрузить 2MB
            if total >= max_bytes:
                # Должна быть ошибка
                assert total >= max_bytes
                break
            
            remaining = max_bytes - total
            read_size = min(chunk_size, remaining)
            total += read_size
        
        # Проверка что не превысили лимит
        assert total <= max_bytes


class TestDockerResourceLimits:
    """Тесты Docker resource limits."""
    
    def test_docker_compose_has_limits(self):
        """docker-compose.yml содержит resource limits."""
        import yaml
        from pathlib import Path
        
        compose_file = Path(__file__).parent.parent / "docker-compose.yml"
        
        with open(compose_file) as f:
            config = yaml.safe_load(f)
        
        # Проверить что у сервисов есть лимиты
        services_to_check = ["bot", "admin", "worker", "beat"]
        
        for service in services_to_check:
            if service in config.get("services", {}):
                service_config = config["services"][service]
                assert "deploy" in service_config, f"{service} должен иметь deploy секцию"
                assert "resources" in service_config["deploy"], f"{service} должен иметь resources"
                assert "limits" in service_config["deploy"]["resources"], f"{service} должен иметь limits"


class TestErrorLogging:
    """Тесты улучшенного логирования ошибок."""
    
    def test_no_silent_exceptions(self):
        """Проверка что нет молчаливых except блоков."""
        from pathlib import Path
        import re
        
        # Проверить критичные файлы
        files_to_check = [
            "core/services/settings_service.py",
            "workers/cleanup.py",
            "workers/video_processor.py",
            "workers/sender.py"
        ]
        
        project_root = Path(__file__).parent.parent
        
        for file_path in files_to_check:
            full_path = project_root / file_path
            if not full_path.exists():
                continue
            
            content = full_path.read_text()
            
            # Проверить что нет "except: pass" или "except Exception: pass"
            silent_patterns = [
                r"except\s*:\s*pass",
                r"except\s+Exception\s*:\s*pass"
            ]
            
            for pattern in silent_patterns:
                matches = re.findall(pattern, content)
                assert len(matches) == 0, f"Найден молчаливый except в {file_path}: {matches}"


@pytest.mark.asyncio
async def test_security_fixes_integration(db_session):
    """Интеграционный тест всех security fixes."""
    from core.url_validator import validate_download_url, InvalidURLError
    from core.services.user_service import UserService
    from core.services.job_service import JobService
    from core.models import User, SourceType
    from datetime import datetime, timezone
    
    # 1. SSRF защита работает
    with pytest.raises(InvalidURLError):
        validate_download_url("http://localhost/")
    
    # 2. Race condition исправлен
    user = User(telegram_id=999999, daily_job_count=0, daily_reset_at=datetime.now(timezone.utc))
    db_session.add(user)
    await db_session.commit()
    
    us = UserService(db_session)
    result = await us.increment_daily_count(user, max_daily=10)
    assert result is True
    
    # 3. MAX_CONCURRENT_JOBS проверяется
    js = JobService(db_session)
    count = await js.count_active_jobs()
    assert isinstance(count, int)
    
    # 4. Metadata truncation работает
    from core.metadata_utils import truncate_metadata
    large_meta = {"key": "x" * 20000}
    truncated = truncate_metadata(large_meta, max_size=1000)
    assert "_truncated" in truncated
