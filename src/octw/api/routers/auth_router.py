from __future__ import annotations

import secrets
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from octw.api.auth import create_access_token, get_or_create_user, set_session_cookie
from octw.db.engine import get_session

router = APIRouter(prefix="/auth", tags=["auth"])

_pending_tokens: dict[str, dict] = {}


class LoginRequest(BaseModel):
    email: str


class VerifyRequest(BaseModel):
    token: str


class SessionResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str
    email: str


@router.post("/login", status_code=202)
async def login(req: LoginRequest, session: AsyncSession = Depends(get_session)):
    token = secrets.token_urlsafe(32)
    _pending_tokens[token] = {
        "email": req.email,
        "expires": datetime.utcnow() + timedelta(minutes=15),
    }
    # In production: send magic link via email
    return {"message": "Check your email for a login link", "dev_token": token}


@router.post("/verify")
async def verify(
    req: VerifyRequest,
    response: Response,
    session: AsyncSession = Depends(get_session),
):
    pending = _pending_tokens.pop(req.token, None)
    if not pending or pending["expires"] < datetime.utcnow():
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    user = await get_or_create_user(session, pending["email"])
    await session.commit()
    access_token = create_access_token(user.user_id, user.email)
    set_session_cookie(response, access_token)
    return SessionResponse(
        access_token=access_token,
        user_id=str(user.user_id),
        email=user.email,
    )


@router.post("/logout", status_code=204)
async def logout():
    return None
