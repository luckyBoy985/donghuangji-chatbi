from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.api.auth import _set_session_cookie, _user_out
from backend.app.core.database import get_db
from backend.app.core.security import CurrentUser, create_user_session, hash_password
from backend.app.models.entities import utc_now
from backend.app.models.identity import Invitation, Team, TeamMembership, User
from backend.app.schemas.auth import UserOut
from backend.app.schemas.invite import InviteRegistration
from backend.app.schemas.team import (
    InvitationCreate,
    InvitationCreated,
    InvitationMetadata,
    InvitationPreview,
    MemberRoleUpdate,
    TeamMemberOut,
    TeamOut,
)
from backend.app.services.audit.service import record_audit

router = APIRouter(prefix="/api", tags=["teams"])


def _membership(
    db: Session, team_id: str, user_id: str
) -> TeamMembership | None:
    return db.scalar(
        select(TeamMembership).where(
            TeamMembership.team_id == team_id,
            TeamMembership.user_id == user_id,
        )
    )


def _require_team_manager(
    db: Session, team_id: str, user: User
) -> TeamMembership:
    team = db.get(Team, team_id)
    if not team or team.status != "active":
        raise HTTPException(status_code=404, detail="团队不存在")
    membership = _membership(db, team_id, user.id)
    if not membership or membership.role not in {"owner", "admin"}:
        raise HTTPException(status_code=403, detail="没有团队管理权限")
    return membership


def _invitation_hash(code: str) -> str:
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


def _valid_invitation(db: Session, code: str) -> Invitation:
    invitation = db.scalar(
        select(Invitation)
        .where(Invitation.code_hash == _invitation_hash(code))
        .with_for_update()
    )
    now = datetime.now(timezone.utc)
    if (
        not invitation
        or invitation.revoked_at is not None
        or datetime.fromisoformat(invitation.expires_at) <= now
        or invitation.used_count >= invitation.max_uses
    ):
        raise HTTPException(status_code=400, detail="邀请不可用")
    team = db.get(Team, invitation.team_id)
    if not team or team.status != "active":
        raise HTTPException(status_code=400, detail="邀请不可用")
    return invitation


@router.get("/teams", response_model=list[TeamOut])
def list_teams(
    user: CurrentUser,
    db: Session = Depends(get_db),
) -> list[TeamOut]:
    rows = db.execute(
        select(Team, TeamMembership.role)
        .join(TeamMembership, TeamMembership.team_id == Team.id)
        .where(TeamMembership.user_id == user.id, Team.status == "active")
        .order_by(Team.name)
    ).all()
    return [
        TeamOut(
            id=team.id,
            name=team.name,
            description=team.description,
            role=role,
            member_count=db.scalar(
                select(func.count())
                .select_from(TeamMembership)
                .where(TeamMembership.team_id == team.id)
            )
            or 0,
        )
        for team, role in rows
    ]


@router.get("/teams/{team_id}", response_model=TeamOut)
def get_team(
    team_id: str,
    user: CurrentUser,
    db: Session = Depends(get_db),
) -> TeamOut:
    team = db.get(Team, team_id)
    membership = _membership(db, team_id, user.id)
    if not team or not membership or team.status != "active":
        raise HTTPException(status_code=404, detail="团队不存在")
    member_count = db.scalar(
        select(func.count())
        .select_from(TeamMembership)
        .where(TeamMembership.team_id == team.id)
    )
    return TeamOut(
        id=team.id,
        name=team.name,
        description=team.description,
        role=membership.role,
        member_count=member_count or 0,
    )


@router.get("/teams/{team_id}/members", response_model=list[TeamMemberOut])
def team_members(
    team_id: str,
    user: CurrentUser,
    db: Session = Depends(get_db),
) -> list[TeamMemberOut]:
    if not _membership(db, team_id, user.id):
        raise HTTPException(status_code=404, detail="团队不存在")
    rows = db.execute(
        select(TeamMembership, User)
        .join(User, User.id == TeamMembership.user_id)
        .where(TeamMembership.team_id == team_id)
        .order_by(User.display_name)
    ).all()
    return [
        TeamMemberOut(
            user_id=member.id,
            username=member_user.username,
            display_name=member_user.display_name,
            role=member.role,
            created_at=member.created_at,
        )
        for member, member_user in rows
    ]


@router.patch(
    "/teams/{team_id}/members/{target_user_id}",
    response_model=TeamMemberOut,
)
def update_member_role(
    team_id: str,
    target_user_id: str,
    payload: MemberRoleUpdate,
    user: CurrentUser,
    db: Session = Depends(get_db),
) -> TeamMemberOut:
    actor = _require_team_manager(db, team_id, user)
    target = _membership(db, team_id, target_user_id)
    target_user = db.get(User, target_user_id)
    if not target or not target_user:
        raise HTTPException(status_code=404, detail="团队成员不存在")
    if actor.role == "admin" and (
        target.role == "owner" or payload.role == "owner"
    ):
        raise HTTPException(status_code=403, detail="只有 owner 可以管理 owner 角色")
    if target.role == "owner" and payload.role != "owner":
        owner_count = db.scalar(
            select(func.count())
            .select_from(TeamMembership)
            .where(
                TeamMembership.team_id == team_id,
                TeamMembership.role == "owner",
            )
        )
        if (owner_count or 0) <= 1:
            raise HTTPException(status_code=409, detail="团队必须保留至少一名 owner")
    target.role = payload.role
    target.updated_at = utc_now()
    record_audit(
        db,
        actor_user_id=user.id,
        action="team.member_role",
        resource_type="team_member",
        resource_id=target.id,
        metadata={"team_id": team_id, "role": target.role},
    )
    db.commit()
    return TeamMemberOut(
        user_id=target_user.id,
        username=target_user.username,
        display_name=target_user.display_name,
        role=target.role,
        created_at=target.created_at,
    )


@router.delete("/teams/{team_id}/members/{target_user_id}", status_code=204)
def remove_member(
    team_id: str,
    target_user_id: str,
    user: CurrentUser,
    db: Session = Depends(get_db),
) -> Response:
    actor = _require_team_manager(db, team_id, user)
    target = _membership(db, team_id, target_user_id)
    if not target:
        raise HTTPException(status_code=404, detail="团队成员不存在")
    if actor.role == "admin" and target.role != "member":
        raise HTTPException(status_code=403, detail="admin 只能移除普通成员")
    if target.role == "owner":
        owner_count = db.scalar(
            select(func.count())
            .select_from(TeamMembership)
            .where(
                TeamMembership.team_id == team_id,
                TeamMembership.role == "owner",
            )
        )
        if (owner_count or 0) <= 1:
            raise HTTPException(status_code=409, detail="团队必须保留至少一名 owner")
    db.delete(target)
    record_audit(
        db,
        actor_user_id=user.id,
        action="team.member_remove",
        resource_type="team_member",
        resource_id=target.id,
        metadata={"team_id": team_id},
    )
    db.commit()
    return Response(status_code=204)


@router.post(
    "/teams/{team_id}/invitations",
    response_model=InvitationCreated,
    status_code=201,
)
def create_invitation(
    team_id: str,
    payload: InvitationCreate,
    user: CurrentUser,
    db: Session = Depends(get_db),
) -> InvitationCreated:
    actor = _require_team_manager(db, team_id, user)
    if actor.role != "owner" and payload.role == "owner":
        raise HTTPException(status_code=403, detail="只有 owner 可以邀请 owner")
    code = secrets.token_urlsafe(32)
    invitation = Invitation(
        code_hash=_invitation_hash(code),
        team_id=team_id,
        team_role=payload.role,
        created_by=user.id,
        expires_at=(
            datetime.now(timezone.utc)
            + timedelta(days=payload.expires_in_days)
        ).isoformat(),
        max_uses=payload.max_uses,
    )
    db.add(invitation)
    record_audit(
        db,
        actor_user_id=user.id,
        action="team.invitation_create",
        resource_type="invitation",
        metadata={"team_id": team_id, "role": payload.role},
    )
    db.commit()
    db.refresh(invitation)
    return InvitationCreated(
        id=invitation.id,
        code=code,
        team_id=invitation.team_id,
        role=invitation.team_role,
        max_uses=invitation.max_uses,
        used_count=invitation.used_count,
        expires_at=invitation.expires_at,
    )


@router.get(
    "/teams/{team_id}/invitations",
    response_model=list[InvitationMetadata],
)
def list_invitations(
    team_id: str,
    user: CurrentUser,
    db: Session = Depends(get_db),
) -> list[InvitationMetadata]:
    _require_team_manager(db, team_id, user)
    rows = db.scalars(
        select(Invitation)
        .where(Invitation.team_id == team_id)
        .order_by(Invitation.created_at.desc())
    ).all()
    return [
        InvitationMetadata(
            id=item.id,
            team_id=item.team_id,
            role=item.team_role,
            max_uses=item.max_uses,
            used_count=item.used_count,
            expires_at=item.expires_at,
            revoked_at=item.revoked_at,
            created_at=item.created_at,
        )
        for item in rows
    ]


@router.delete("/teams/{team_id}/invitations/{invitation_id}", status_code=204)
def revoke_invitation(
    team_id: str,
    invitation_id: str,
    user: CurrentUser,
    db: Session = Depends(get_db),
) -> Response:
    _require_team_manager(db, team_id, user)
    invitation = db.get(Invitation, invitation_id)
    if not invitation or invitation.team_id != team_id:
        raise HTTPException(status_code=404, detail="邀请不存在")
    invitation.revoked_at = utc_now()
    record_audit(
        db,
        actor_user_id=user.id,
        action="team.invitation_revoke",
        resource_type="invitation",
        resource_id=invitation.id,
        metadata={"team_id": team_id},
    )
    db.commit()
    return Response(status_code=204)


@router.get("/invitations/{code}", response_model=InvitationPreview)
def preview_invitation(
    code: str,
    db: Session = Depends(get_db),
) -> InvitationPreview:
    invitation = _valid_invitation(db, code)
    team = db.get(Team, invitation.team_id)
    if not team or team.status != "active":
        raise HTTPException(status_code=400, detail="邀请不可用")
    return InvitationPreview(
        team_id=team.id,
        team_name=team.name,
        role=invitation.team_role,
    )


def _join_invitation(db: Session, invitation: Invitation, user: User) -> None:
    if _membership(db, invitation.team_id, user.id):
        raise HTTPException(status_code=409, detail="已加入该团队")
    db.add(
        TeamMembership(
            team_id=invitation.team_id,
            user_id=user.id,
            role=invitation.team_role,
        )
    )
    invitation.used_count += 1


@router.post(
    "/auth/register-with-invite",
    response_model=UserOut,
    status_code=201,
)
def register_with_invite(
    payload: InviteRegistration,
    response: Response,
    db: Session = Depends(get_db),
) -> UserOut:
    invitation = _valid_invitation(db, payload.code)
    user = User(
        username=payload.username,
        display_name=payload.display_name,
        password_hash=hash_password(payload.password),
        platform_role="user",
    )
    db.add(user)
    try:
        db.flush()
        _join_invitation(db, invitation, user)
        record_audit(
            db,
            actor_user_id=user.id,
            action="auth.register_invite",
            resource_type="team",
            resource_id=invitation.team_id,
        )
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(status_code=409, detail="用户名已被使用") from error
    token, _record = create_user_session(db, user)
    _set_session_cookie(response, token)
    return _user_out(db, user)


@router.post("/invitations/{code}/redeem")
def redeem_invitation(
    code: str,
    user: CurrentUser,
    db: Session = Depends(get_db),
) -> dict:
    invitation = _valid_invitation(db, code)
    _join_invitation(db, invitation, user)
    record_audit(
        db,
        actor_user_id=user.id,
        action="team.invitation_redeem",
        resource_type="team",
        resource_id=invitation.team_id,
    )
    db.commit()
    return {"success": True, "team_id": invitation.team_id}
