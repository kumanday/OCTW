from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from octw.common.config import settings
from octw.db.tables import UserRow

security = HTTPBearer(auto_error=False)


class TokenPayload:
    def __init__(self, user_id: uuid.UUID, email: str, tid: uuid.UUID | None = None) -> None:
        self.user_id = user_id
        self.email = email
        self.tid = tid


def create_access_token(
    user_id: uuid.UUID,
    email: str,
    tenant_id: uuid.UUID | None = None,
    expires_minutes: int | None = None,
) -> str:
    exp = datetime.utcnow() + timedelta(minutes=expires_minutes or settings.jwt_expire_minutes)
    payload: dict = {
        "sub": str(user_id),
        "email": email,
        "exp": exp,
    }
    if tenant_id:
        payload["tid"] = str(tenant_id)
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> TokenPayload:
    try:
        data = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except jwt.PyJWTError as e:
        raise HTTPException(status_code=401, detail="Invalid token") from e
    tid = uuid.UUID(data["tid"]) if data.get("tid") else None
    return TokenPayload(user_id=uuid.UUID(data["sub"]), email=data["email"], tid=tid)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> TokenPayload:
    if not credentials:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return decode_token(credentials.credentials)


async def get_or_create_user(
    session: AsyncSession, email: str
) -> UserRow:
    row = (
        await session.execute(select(UserRow).where(UserRow.email == email))
    ).scalar_one_or_none()
    if row:
        return row
    row = UserRow(email=email)
    session.add(row)
    await session.flush()
    return row
