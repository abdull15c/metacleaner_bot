import json, subprocess, pytest
from unittest.mock import MagicMock, patch
from core.exceptions import FFmpegError, FFmpegNotFoundError
from workers.video_processor import check_ffmpeg, extract_metadata, strip_metadata, get_output_path, SUPPORTED_EXTENSIONS


def mock_run(returncode=0, stdout="", stderr=""):
    r = MagicMock(); r.returncode = returncode; r.stdout = stdout; r.stderr = stderr; return r


def test_check_ffmpeg_ok():
    with patch("subprocess.run", return_value=mock_run(0, "ffmpeg version 6")):
        assert check_ffmpeg() == ("ffmpeg", "ffprobe")


def test_check_ffmpeg_missing():
    with patch("subprocess.run", side_effect=FileNotFoundError):
        with pytest.raises(FFmpegNotFoundError): check_ffmpeg()


def test_extract_metadata_parses():
    out = json.dumps({"format": {"tags": {"title": "Test"}}, "streams": []})
    with patch("subprocess.run", return_value=mock_run(0, out)):
        meta = extract_metadata("/f.mp4")
    assert meta["format_tags"]["title"] == "Test"


def test_extract_metadata_error_returns_empty():
    with patch("subprocess.run", return_value=mock_run(1)):
        assert extract_metadata("/f.mp4") == {}


def test_strip_metadata_ok():
    with patch("subprocess.run", return_value=mock_run(0)):
        ok, _ = strip_metadata("/in.mp4", "/out.mp4")
    assert ok is True


def test_strip_metadata_raises():
    with patch("subprocess.run", return_value=mock_run(1, stderr="Error")):
        with pytest.raises(FFmpegError): strip_metadata("/in.mp4", "/out.mp4")


def test_output_path_unique():
    p1 = get_output_path("/v.mp4"); p2 = get_output_path("/v.mp4")
    assert p1 != p2
    assert p1.endswith("_clean.mp4")

def test_supported_extensions():
    assert {".mp4",".mkv",".mov",".avi",".webm"}.issubset(SUPPORTED_EXTENSIONS)

@pytest.mark.asyncio
async def test_process_video_task_with_mock_ffmpeg(mocker, app_schema):
    from workers.video_processor import process_video_task
    from core.database import get_db_session
    from core.models import Job, JobStatus, SourceType, User
    from core.services.job_service import JobService
    import uuid
    import asyncio
    from unittest.mock import AsyncMock
    
    mocker.patch("workers.video_processor.extract_metadata", return_value={"mock": "data"})
    mocker.patch("workers.video_processor.run_ffmpeg_action", return_value=(True, ""))
    mocker.patch("workers.video_processor.Path.exists", return_value=True)
    mocker.patch("workers.video_processor.Path.stat", return_value=mocker.MagicMock(st_size=1024))
    
    redis_mock = AsyncMock()
    redis_mock.scard.return_value = 0
    mocker.patch("redis.asyncio.from_url", return_value=redis_mock)
    
    sender_mock = mocker.patch("workers.sender.send_result_task.delay")
    mocker.patch("workers.sender.notify_failure_task.delay")

    async with get_db_session() as session:
        u = User(telegram_id=987654321)
        session.add(u)
        await session.flush()
        js = JobService(session)
        job = await js.create_job(u.id, SourceType.upload, original_filename="test.mp4")
        job.temp_original_path = "/tmp/test.mp4"
        job_uuid = job.uuid
        await session.commit()
    
    async def mock_run(coro):
        return await coro
        
    mocker.patch("asyncio.run", mock_run)
    
    # Process it directly
    result = await process_video_task(job_uuid)
    
    assert result == {"status": "ok"}
    
    async with get_db_session() as session:
        js = JobService(session)
        job2 = await js.get_by_uuid(job_uuid)
        assert job2.status == JobStatus.done
        assert job2.temp_processed_path is not None
        
    sender_mock.assert_called_once_with(job_uuid)
