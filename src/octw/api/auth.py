from __future__ import annotations

import ipaddress
import uuid
from datetime import datetime, timedelta
from typing import Any

import jwt
from fastapi import Depends, HTTPException, Request, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from octw.common.config import settings
from octw.db.tables import UserRow

security = HTTPBearer(auto_error=False)
SESSION_COOKIE_NAME = "octw_session"


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
    payload: dict[str, Any] = {
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


def _extract_cookie_token(request: Request) -> str | None:
    token = request.cookies.get(SESSION_COOKIE_NAME)
    return token.strip() if token else None


def _client_host(request: Request) -> str:
    if request.client and request.client.host:
        return request.client.host
    return ""


def _ip_in_networks(host: str, configured: list[str]) -> bool:
    if not host:
        return False
    try:
        addr = ipaddress.ip_address(host)
    except ValueError:
        return False
    for raw in configured:
        try:
            network = ipaddress.ip_network(raw, strict=False)
        except ValueError:
            continue
        if addr in network:
            return True
    return False


def get_trusted_proxy_email(request: Request) -> str | None:
    if not settings.trusted_proxy_enabled:
        return None
    host = _client_host(request)
    if settings.trusted_proxy_ips and not _ip_in_networks(host, settings.trusted_proxy_ips):
        return None
    header = settings.trusted_proxy_user_header
    email = request.headers.get(header, "").strip()
    return email or None


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> TokenPayload:
    token: str | None = None
    if credentials:
        token = credentials.credentials
    if not token:
        token = _extract_cookie_token(request)
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return decode_token(token)


async def get_browser_user(
    request: Request,
    session: AsyncSession,
) -> tuple[TokenPayload, bool]:
    token = _extract_cookie_token(request)
    if token:
        return decode_token(token), False

    forwarded_email = get_trusted_proxy_email(request)
    if not forwarded_email:
        raise HTTPException(status_code=401, detail="Not authenticated")

    user = await get_or_create_user(session, forwarded_email)
    return TokenPayload(user.user_id, user.email), True


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


def set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        httponly=True,
        secure=settings.public_base_url.startswith("https://"),
        samesite="lax",
        path="/",
        max_age=settings.jwt_expire_minutes * 60,
    )
