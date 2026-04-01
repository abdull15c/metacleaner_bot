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
    assert p1 != p2 and p1.endswith(".mp4")


def test_supported_extensions():
    assert {".mp4",".mkv",".mov",".avi",".webm"}.issubset(SUPPORTED_EXTENSIONS)
