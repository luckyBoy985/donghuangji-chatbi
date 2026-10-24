from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models.entities import Conversation, ConversationShare
from backend.app.models.identity import Team, TeamMembership, User


def user_team_ids(db: Session, user_id: str) -> set[str]:
    return set(
        db.scalars(
            select(TeamMembership.team_id)
            .join(Team, Team.id == TeamMembership.team_id)
            .where(
                TeamMembership.user_id == user_id,
                Team.status == "active",
            )
        ).all()
    )


def conversation_permission(
    db: Session, conversation: Conversation, user: User
) -> str | None:
    if conversation.owner_user_id == user.id:
        return "owner"
    shared = db.scalar(
        select(ConversationShare.id)
        .join(TeamMembership, TeamMembership.team_id == ConversationShare.team_id)
        .join(Team, Team.id == ConversationShare.team_id)
        .where(
            ConversationShare.conversation_id == conversation.id,
            TeamMembership.user_id == user.id,
            Team.status == "active",
        )
        .limit(1)
    )
    return "read" if shared else None


def shared_conversation_ids(db: Session, user_id: str) -> set[str]:
    return set(
        db.scalars(
            select(ConversationShare.conversation_id)
            .join(TeamMembership, TeamMembership.team_id == ConversationShare.team_id)
            .join(Team, Team.id == ConversationShare.team_id)
            .where(
                TeamMembership.user_id == user_id,
                Team.status == "active",
            )
        ).all()
    )
