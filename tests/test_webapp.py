"""Mini App: токены скачивания, initData, HTTP-роуты (интеграция с общей БД)."""
import asyncio
import uuid

import core.models  # noqa: F401
import pytest
from starlette.testclient import TestClient

from webapp.result_token import create_result_download_token, parse_result_download_token
from webapp.tg_init_data import validate_webapp_init_data


def test_result_download_token_roundtrip():
    jid = str(uuid.uuid4())
    t = create_result_download_token(jid, 999888777)
    d = parse_result_download_token(t)
    assert d is not None
    assert d["j"] == jid
    assert d["tg"] == 999888777


def test_result_token_rejects_tamper():
    jid = str(uuid.uuid4())
    t = create_result_download_token(jid, 1)
    d = parse_result_download_token(t[:-3] + "xxx")
    assert d is None


def test_validate_init_data_rejects_garbage():
    assert validate_webapp_init_data("not=valid&hash=abc", "tok") is None


def _schema_up_down():
    from core.database import Base, engine

    async def up():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def down():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)

    return up, down


@pytest.fixture
def web_schema():
    up, down = _schema_up_down()
    asyncio.run(up())
    yield
    asyncio.run(down())


@pytest.fixture
def wclient(web_schema):
    from admin.main import app

    with TestClient(app) as c:
        yield c


@pytest.mark.integration
def test_webapp_upload_invalid_init(wclient):
    r = wclient.post(
        "/api/webapp/upload",
        data={"init_data": "user=%7B%22id%22%3A1%7D&hash=bad"},
        files={"file": ("a.mp4", b"x", "video/mp4")},
    )
    assert r.status_code == 401


@pytest.mark.integration
def test_webapp_upload_unsupported_format(wclient, monkeypatch):
    import webapp.routes as wr

    monkeypatch.setattr(wr, "_require_telegram_user", lambda s: (1, {"id": 1}))
    r = wclient.post(
        "/api/webapp/upload",
        data={"init_data": "dummy"},
        files={"file": ("a.exe", b"x", "application/octet-stream")},
    )
    assert r.status_code == 400
    assert r.json().get("detail") == "unsupported_format"


@pytest.mark.integration
def test_webapp_job_missing_header(wclient):
    r = wclient.get("/api/webapp/job/" + str(uuid.uuid4()))
    assert r.status_code == 401


@pytest.mark.integration
def test_webapp_result_requires_auth(wclient):
    r = wclient.get("/api/webapp/result/" + str(uuid.uuid4()))
    assert r.status_code == 401


@pytest.mark.integration
def test_webapp_result_invalid_token(wclient):
    r = wclient.get(
        "/api/webapp/result/" + str(uuid.uuid4()),
        params={"t": "invalid"},
    )
    assert r.status_code == 401
