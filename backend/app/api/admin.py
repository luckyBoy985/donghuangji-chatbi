from __future__ import annotations

import json
import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.core.database import get_db
from backend.app.core.security import AdminUser, hash_password
from backend.app.models.audit import AuditLog
from backend.app.models.entities import utc_now
from backend.app.models.identity import Invitation, Team, TeamMembership, User, UserSession
from backend.app.schemas.admin import (
    AdminTeamCreate,
    AdminTeamOut,
    AdminTeamUpdate,
    AdminPasswordReset,
    AdminUserOut,
    AdminUserUpdate,
    AuditOut,
)
from backend.app.schemas.team import InvitationCreate, InvitationCreated
from backend.app.services.audit.service import record_audit

router = APIRouter(prefix="/api/admin", tags=["admin"])


def _user_out(user: User) -> AdminUserOut:
    return AdminUserOut(
        id=user.id,
        username=user.username,
        display_name=user.display_name,
        platform_role=user.platform_role,
        status=user.status,
        must_change_password=user.must_change_password,
        created_at=user.created_at,
    )


def _team_out(db: Session, team: Team) -> AdminTeamOut:
    owner_count = db.scalar(
        select(func.count())
        .select_from(TeamMembership)
        .where(
            TeamMembership.team_id == team.id,
            TeamMembership.role == "owner",
        )
    )
    member_count = db.scalar(
        select(func.count())
        .select_from(TeamMembership)
        .where(TeamMembership.team_id == team.id)
    )
    return AdminTeamOut(
        id=team.id,
        name=team.name,
        description=team.description,
        status=team.status,
        owner_count=owner_count or 0,
        member_count=member_count or 0,
        created_at=team.created_at,
    )


@router.get("/users", response_model=list[AdminUserOut])
def list_users(
    _admin: AdminUser,
    q: str = "",
    db: Session = Depends(get_db),
) -> list[AdminUserOut]:
    statement = select(User).order_by(User.created_at.desc()).limit(200)
    if q.strip():
        pattern = f"%{q.strip()}%"
        statement = statement.where(
            or_(User.username.ilike(pattern), User.display_name.ilike(pattern))
        )
    return [_user_out(user) for user in db.scalars(statement).all()]


@router.patch("/users/{user_id}", response_model=AdminUserOut)
def update_user(
    user_id: str,
    payload: AdminUserUpdate,
    admin: AdminUser,
    db: Session = Depends(get_db),
) -> AdminUserOut:
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    if user.id == admin.id and payload.status == "disabled":
        raise HTTPException(status_code=409, detail="不能停用当前管理员")
    if (
        user.platform_role == "admin"
        and payload.platform_role == "user"
        and db.scalar(
            select(func.count())
            .select_from(User)
            .where(User.platform_role == "admin", User.status == "active")
        )
        == 1
    ):
        raise HTTPException(status_code=409, detail="系统必须保留至少一名管理员")
    if payload.display_name is not None:
        user.display_name = payload.display_name
    if payload.platform_role is not None:
        user.platform_role = payload.platform_role
    if payload.status is not None:
        user.status = payload.status
        if payload.status == "disabled":
            for session in db.scalars(
                select(UserSession).where(
                    UserSession.user_id == user.id,
                    UserSession.revoked_at.is_(None),
                )
            ).all():
                session.revoked_at = utc_now()
    user.updated_at = utc_now()
    record_audit(
        db,
        actor_user_id=admin.id,
        action="user.disable" if payload.status == "disabled" else "user.update",
        resource_type="user",
        resource_id=user.id,
        metadata={"status": user.status, "platform_role": user.platform_role},
    )
    db.commit()
    db.refresh(user)
    return _user_out(user)


@router.post("/users/{user_id}/revoke-sessions", status_code=204)
def revoke_user_sessions(
    user_id: str,
    admin: AdminUser,
    db: Session = Depends(get_db),
) -> None:
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    for session in db.scalars(
        select(UserSession).where(
            UserSession.user_id == user.id,
            UserSession.revoked_at.is_(None),
        )
    ).all():
        session.revoked_at = utc_now()
    record_audit(
        db,
        actor_user_id=admin.id,
        action="user.revoke_sessions",
        resource_type="user",
        resource_id=user.id,
    )
    db.commit()


@router.post(
    "/users/{user_id}/reset-password",
    response_model=AdminPasswordReset,
)
def reset_user_password(
    user_id: str,
    admin: AdminUser,
    db: Session = Depends(get_db),
) -> AdminPasswordReset:
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    if user.id == admin.id:
        raise HTTPException(
            status_code=409,
            detail="请使用个人密码修改功能更新当前管理员密码",
        )
    temporary_password = secrets.token_urlsafe(24)
    user.password_hash = hash_password(temporary_password)
    user.must_change_password = True
    user.updated_at = utc_now()
    for session in db.scalars(
        select(UserSession).where(
            UserSession.user_id == user.id,
            UserSession.revoked_at.is_(None),
        )
    ).all():
        session.revoked_at = utc_now()
    record_audit(
        db,
        actor_user_id=admin.id,
        action="user.password_reset",
        resource_type="user",
        resource_id=user.id,
    )
    db.commit()
    return AdminPasswordReset(
        user_id=user.id,
        temporary_password=temporary_password,
    )


@router.get("/teams", response_model=list[AdminTeamOut])
def list_teams(
    _admin: AdminUser,
    db: Session = Depends(get_db),
) -> list[AdminTeamOut]:
    return [
        _team_out(db, team)
        for team in db.scalars(select(Team).order_by(Team.created_at.desc())).all()
    ]


@router.post("/teams", response_model=AdminTeamOut, status_code=201)
def create_team(
    payload: AdminTeamCreate,
    admin: AdminUser,
    db: Session = Depends(get_db),
) -> AdminTeamOut:
    owner = db.get(User, payload.owner_user_id)
    if not owner or owner.status != "active":
        raise HTTPException(status_code=404, detail="活动 owner 用户不存在")
    team = Team(
        name=payload.name,
        description=payload.description.strip(),
        created_by=admin.id,
    )
    db.add(team)
    try:
        db.flush()
        db.add(TeamMembership(team_id=team.id, user_id=owner.id, role="owner"))
        record_audit(
            db,
            actor_user_id=admin.id,
            action="team.create",
            resource_type="team",
            resource_id=team.id,
        )
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(status_code=409, detail="团队名称已存在") from error
    db.refresh(team)
    return _team_out(db, team)


@router.patch("/teams/{team_id}", response_model=AdminTeamOut)
def update_team(
    team_id: str,
    payload: AdminTeamUpdate,
    admin: AdminUser,
    db: Session = Depends(get_db),
) -> AdminTeamOut:
    team = db.get(Team, team_id)
    if not team:
        raise HTTPException(status_code=404, detail="团队不存在")
    if payload.name is not None:
        team.name = payload.name.strip()
    if payload.description is not None:
        team.description = payload.description.strip()
    team.updated_at = utc_now()
    record_audit(
        db,
        actor_user_id=admin.id,
        action="team.update",
        resource_type="team",
        resource_id=team.id,
    )
    db.commit()
    return _team_out(db, team)


def _set_team_status(
    team_id: str, status: str, admin: User, db: Session
) -> AdminTeamOut:
    team = db.get(Team, team_id)
    if not team:
        raise HTTPException(status_code=404, detail="团队不存在")
    team.status = status
    team.updated_at = utc_now()
    record_audit(
        db,
        actor_user_id=admin.id,
        action=f"team.{status}",
        resource_type="team",
        resource_id=team.id,
    )
    db.commit()
    return _team_out(db, team)


@router.post("/teams/{team_id}/archive", response_model=AdminTeamOut)
def archive_team(
    team_id: str, admin: AdminUser, db: Session = Depends(get_db)
) -> AdminTeamOut:
    return _set_team_status(team_id, "archived", admin, db)


@router.post(
    "/teams/{team_id}/invitations",
    response_model=InvitationCreated,
    status_code=201,
)
def create_admin_invitation(
    team_id: str,
    payload: InvitationCreate,
    admin: AdminUser,
    db: Session = Depends(get_db),
) -> InvitationCreated:
    team = db.get(Team, team_id)
    if not team or team.status != "active":
        raise HTTPException(status_code=404, detail="团队不存在")
    code = secrets.token_urlsafe(32)
    invitation = Invitation(
        code_hash=hashlib.sha256(code.encode("utf-8")).hexdigest(),
        team_id=team.id,
        team_role=payload.role,
        created_by=admin.id,
        expires_at=(
            datetime.now(timezone.utc)
            + timedelta(days=payload.expires_in_days)
        ).isoformat(),
        max_uses=payload.max_uses,
    )
    db.add(invitation)
    record_audit(
        db,
        actor_user_id=admin.id,
        action="team.invitation_create",
        resource_type="invitation",
        metadata={"team_id": team.id, "role": payload.role},
    )
    db.commit()
    db.refresh(invitation)
    return InvitationCreated(
        id=invitation.id,
        code=code,
        team_id=team.id,
        role=invitation.team_role,
        max_uses=invitation.max_uses,
        used_count=invitation.used_count,
        expires_at=invitation.expires_at,
    )


@router.post("/teams/{team_id}/restore", response_model=AdminTeamOut)
def restore_team(
    team_id: str, admin: AdminUser, db: Session = Depends(get_db)
) -> AdminTeamOut:
    return _set_team_status(team_id, "active", admin, db)


@router.get("/audit", response_model=list[AuditOut])
def list_audit(
    _admin: AdminUser,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    action: str = "",
    actor_user_id: str = "",
    start_at: datetime | None = Query(default=None),
    end_at: datetime | None = Query(default=None),
    db: Session = Depends(get_db),
) -> list[AuditOut]:
    statement = select(AuditLog).order_by(AuditLog.created_at.desc())
    if action:
        statement = statement.where(AuditLog.action == action)
    if actor_user_id:
        statement = statement.where(
            AuditLog.actor_user_id == actor_user_id
        )
    if start_at:
        if start_at.tzinfo is None:
            start_at = start_at.replace(tzinfo=timezone.utc)
        statement = statement.where(
            AuditLog.created_at >= start_at.isoformat()
        )
    if end_at:
        if end_at.tzinfo is None:
            end_at = end_at.replace(tzinfo=timezone.utc)
        statement = statement.where(
            AuditLog.created_at <= end_at.isoformat()
        )
    rows = db.scalars(
        statement.offset((page - 1) * page_size).limit(page_size)
    ).all()
    return [
        AuditOut(
            id=row.id,
            actor_user_id=row.actor_user_id,
            action=row.action,
            resource_type=row.resource_type,
            resource_id=row.resource_id,
            result=row.result,
            metadata=json.loads(row.metadata_json or "{}"),
            ip_address=row.ip_address,
            created_at=row.created_at,
        )
        for row in rows
    ]
