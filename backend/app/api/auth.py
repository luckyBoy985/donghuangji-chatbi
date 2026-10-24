from __future__ import annotations

import hmac
import hashlib
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from backend.app.core.config import settings
from backend.app.core.database import get_db
from backend.app.core.security import (
    CurrentUser,
    SESSION_COOKIE,
    create_user_session,
    hash_password,
    revoke_session,
    verify_password,
)
from backend.app.models.entities import utc_now
from backend.app.models.identity import (
    LoginAttempt,
    Team,
    TeamMembership,
    User,
    UserSession,
)
from backend.app.schemas.auth import (
    LoginRequest,
    PasswordChange,
    ProfileUpdate,
    SetupRequest,
    SetupStatus,
    TeamRoleInfo,
    UserOut,
)
from backend.app.services.audit.service import record_audit

router = APIRouter(prefix="/api", tags=["auth"])


def _user_out(db: Session, user: User) -> UserOut:
    rows = db.execute(
        select(Team, TeamMembership.role)
        .join(TeamMembership, TeamMembership.team_id == Team.id)
        .where(TeamMembership.user_id == user.id)
        .order_by(Team.name)
    ).all()
    return UserOut(
        id=user.id,
        username=user.username,
        display_name=user.display_name,
        platform_role=user.platform_role,
        status=user.status,
        must_change_password=user.must_change_password,
        teams=[
            TeamRoleInfo(id=team.id, name=team.name, role=role)
            for team, role in rows
        ],
    )


def _set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=settings.session_ttl_days * 24 * 3600,
        httponly=True,
        samesite="lax",
        secure=settings.session_cookie_secure,
        path="/",
    )


@router.get("/auth/setup-status", response_model=SetupStatus)
def setup_status(db: Session = Depends(get_db)) -> SetupStatus:
    return SetupStatus(
        setup_required=db.scalar(select(User.id).limit(1)) is None
    )


@router.post("/auth/setup", response_model=UserOut, status_code=201)
def setup_admin(
    payload: SetupRequest,
    response: Response,
    db: Session = Depends(get_db),
) -> UserOut:
    if db.scalar(select(User.id).limit(1)) is not None:
        raise HTTPException(status_code=410, detail="系统已完成初始化")
    expected = settings.bootstrap_admin_token.strip()
    if not expected or not hmac.compare_digest(
        payload.bootstrap_token.encode(), expected.encode()
    ):
        raise HTTPException(status_code=403, detail="初始化令牌无效")
    user = User(
        username=payload.username,
        display_name=payload.display_name,
        password_hash=hash_password(payload.password),
        platform_role="admin",
    )
    db.add(user)
    db.flush()
    record_audit(
        db,
        actor_user_id=user.id,
        action="auth.setup",
        resource_type="user",
        resource_id=user.id,
    )
    db.commit()
    db.refresh(user)
    token, _record = create_user_session(db, user)
    _set_session_cookie(response, token)
    return _user_out(db, user)


@router.post("/auth/login", response_model=UserOut)
def login(
    payload: LoginRequest,
    response: Response,
    request: Request,
    db: Session = Depends(get_db),
) -> UserOut:
    client_ip = request.headers.get("x-real-ip") or (
        request.client.host if request.client else ""
    )
    attempt_key = hashlib.sha256(
        f"{payload.username}\0{client_ip}".encode("utf-8")
    ).hexdigest()
    cutoff = (
        datetime.now(timezone.utc)
        - timedelta(seconds=settings.login_window_seconds)
    ).isoformat()
    recent_failures = (
        db.scalar(
            select(func.count())
            .select_from(LoginAttempt)
            .where(
                LoginAttempt.attempt_key == attempt_key,
                LoginAttempt.failed_at >= cutoff,
            )
        )
        or 0
    )
    if recent_failures >= settings.max_login_failures:
        record_audit(
            db,
            actor_user_id=None,
            action="auth.login_throttled",
            resource_type="user",
            result="denied",
            ip_address=client_ip,
            commit=True,
        )
        raise HTTPException(status_code=429, detail="登录尝试过多，请稍后重试")

    user = db.scalar(select(User).where(User.username == payload.username))
    if (
        not user
        or user.status != "active"
        or not verify_password(payload.password, user.password_hash)
    ):
        db.add(LoginAttempt(attempt_key=attempt_key))
        record_audit(
            db,
            actor_user_id=user.id if user else None,
            action="auth.login_failed",
            resource_type="user",
            result="denied",
            ip_address=client_ip,
            commit=True,
        )
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    record_audit(
        db,
        actor_user_id=user.id,
        action="auth.login",
        resource_type="user",
        resource_id=user.id,
        ip_address=client_ip,
    )
    db.execute(
        delete(LoginAttempt).where(LoginAttempt.attempt_key == attempt_key)
    )
    token, _record = create_user_session(db, user)
    _set_session_cookie(response, token)
    return _user_out(db, user)


@router.post("/auth/logout", status_code=204)
def logout(
    db: Session = Depends(get_db),
    token: str | None = Cookie(default=None, alias=SESSION_COOKIE),
) -> Response:
    revoke_session(db, token)
    record_audit(
        db,
        actor_user_id=None,
        action="auth.logout",
        resource_type="session",
        commit=True,
    )
    response = Response(status_code=204)
    response.delete_cookie(SESSION_COOKIE, path="/")
    return response


@router.get("/me", response_model=UserOut)
def me(user: CurrentUser, db: Session = Depends(get_db)) -> UserOut:
    return _user_out(db, user)


@router.patch("/me", response_model=UserOut)
def update_me(
    payload: ProfileUpdate,
    user: CurrentUser,
    db: Session = Depends(get_db),
) -> UserOut:
    user.display_name = payload.display_name
    db.commit()
    return _user_out(db, user)


@router.post("/auth/password", status_code=204)
def change_password(
    payload: PasswordChange,
    user: CurrentUser,
    db: Session = Depends(get_db),
    token: str | None = Cookie(default=None, alias=SESSION_COOKIE),
) -> Response:
    if not verify_password(payload.current_password, user.password_hash):
        raise HTTPException(status_code=400, detail="当前密码不正确")
    if payload.current_password == payload.new_password:
        raise HTTPException(status_code=422, detail="新密码不能与当前密码相同")
    user.password_hash = hash_password(payload.new_password)
    user.must_change_password = False
    for record in db.scalars(
        select(UserSession).where(
            UserSession.user_id == user.id,
            UserSession.revoked_at.is_(None),
        )
    ).all():
        record.revoked_at = utc_now()
    record_audit(
        db,
        actor_user_id=user.id,
        action="auth.password_change",
        resource_type="user",
        resource_id=user.id,
    )
    db.commit()
    response = Response(status_code=204)
    response.delete_cookie(SESSION_COOKIE, path="/")
    return response
