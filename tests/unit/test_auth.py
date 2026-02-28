from __future__ import annotations

import uuid

import pytest

from octw.api.auth import create_access_token, decode_token


class TestJWT:
    def test_create_and_decode(self):
        uid = uuid.uuid4()
        token = create_access_token(uid, "test@example.com")
        payload = decode_token(token)
        assert payload.user_id == uid
        assert payload.email == "test@example.com"
        assert payload.tid is None

    def test_with_tenant_id(self):
        uid = uuid.uuid4()
        tid = uuid.uuid4()
        token = create_access_token(uid, "test@example.com", tenant_id=tid)
        payload = decode_token(token)
        assert payload.tid == tid

    def test_invalid_token(self):
        from fastapi import HTTPException
        with pytest.raises(HTTPException):
            decode_token("invalid.token.here")

    def test_expired_token(self):
        from fastapi import HTTPException
        uid = uuid.uuid4()
        token = create_access_token(uid, "test@example.com", expires_minutes=-1)
        with pytest.raises(HTTPException):
            decode_token(token)
