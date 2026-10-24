from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from typing import Annotated

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import Cookie, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.config import settings
from backend.app.core.database import get_db
from backend.app.models.entities import utc_now
from backend.app.models.identity import User, UserSession

SESSION_COOKIE = "chatbi_session"
_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except VerifyMismatchError:
        return False


def new_session_token() -> str:
    return secrets.token_urlsafe(48)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def session_expiry() -> str:
    return (
        datetime.now(timezone.utc) + timedelta(days=settings.session_ttl_days)
    ).isoformat()


def create_user_session(db: Session, user: User) -> tuple[str, UserSession]:
    token = new_session_token()
    record = UserSession(
        user_id=user.id,
        token_hash=hash_token(token),
        expires_at=session_expiry(),
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return token, record


def revoke_session(db: Session, token: str | None) -> None:
    if not token:
        return
    record = db.scalar(
        select(UserSession).where(UserSession.token_hash == hash_token(token))
    )
    if record and record.revoked_at is None:
        record.revoked_at = utc_now()
        db.commit()


def get_current_user(
    request: Request,
    token: Annotated[str | None, Cookie(alias=SESSION_COOKIE)] = None,
    db: Session = Depends(get_db),
) -> User:
    if not token:
        raise HTTPException(status_code=401, detail="请先登录")
    now = datetime.now(timezone.utc)
    record = db.scalar(
        select(UserSession).where(
            UserSession.token_hash == hash_token(token),
            UserSession.revoked_at.is_(None),
        )
    )
    if not record or datetime.fromisoformat(record.expires_at) <= now:
        raise HTTPException(status_code=401, detail="请先登录")
    user = db.get(User, record.user_id)
    if not user or user.status != "active":
        raise HTTPException(status_code=401, detail="请先登录")
    if user.must_change_password and request.url.path not in {
        "/api/me",
        "/api/auth/password",
        "/api/auth/logout",
    }:
        raise HTTPException(
            status_code=428,
            detail="首次登录必须先修改临时密码",
        )
    return user


def require_admin(
    user: Annotated[User, Depends(get_current_user)],
) -> User:
    if user.platform_role != "admin":
        raise HTTPException(status_code=403, detail="需要平台管理员权限")
    return user


def origin_is_allowed(origin: str | None) -> bool:
    if not origin:
        return False
    return hmac.compare_digest(origin, settings.allowed_origin.rstrip("/"))


CurrentUser = Annotated[User, Depends(get_current_user)]
AdminUser = Annotated[User, Depends(require_admin)]
