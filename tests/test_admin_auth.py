import pytest
from admin.auth import hash_password, verify_password, create_token, decode_token


def test_hash_differs_from_plain():
    assert hash_password("pass") != "pass"


def test_verify_correct():
    h = hash_password("secret")
    assert verify_password("secret", h) is True
    assert verify_password("wrong",  h) is False


def test_token_roundtrip():
    t = create_token(42); assert decode_token(t) == 42


def test_invalid_token_none():
    assert decode_token("garbage.token.here") is None


def test_tampered_token_none():
    t = create_token(1); assert decode_token(t[:-4] + "XXXX") is None


def test_decode_token_invalid_payload_none():
    assert decode_token("") is None


@pytest.mark.asyncio
async def test_authenticate_ok(db_session):
    from core.models import Admin
    from admin.auth import authenticate
    db_session.add(Admin(username="adm", password_hash=hash_password("pw123"), is_active=True))
    await db_session.commit()
    result = await authenticate(db_session, "adm", "pw123")
    assert result is not None and result.username == "adm"


@pytest.mark.asyncio
async def test_authenticate_wrong_pass(db_session):
    from core.models import Admin
    from admin.auth import authenticate
    db_session.add(Admin(username="adm2", password_hash=hash_password("right"), is_active=True))
    await db_session.commit()
    assert await authenticate(db_session, "adm2", "wrong") is None
