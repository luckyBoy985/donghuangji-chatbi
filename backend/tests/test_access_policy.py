from fastapi.testclient import TestClient

from backend.app.core.security import hash_password
from backend.app.models.entities import Conversation, ConversationShare
from backend.app.models.identity import Team, TeamMembership, User

PASSWORD = "CorrectHorseBatteryStaple"


def _login(app, username: str):
    client = TestClient(app)
    response = client.post(
        "/api/auth/login",
        json={"username": username, "password": PASSWORD},
    )
    assert response.status_code == 200
    return client


def _seed(session_factory):
    db = session_factory()
    owner = User(
        username="owner",
        display_name="Owner",
        password_hash=hash_password(PASSWORD),
        platform_role="user",
    )
    member = User(
        username="member",
        display_name="Member",
        password_hash=hash_password(PASSWORD),
        platform_role="user",
    )
    outsider = User(
        username="outsider",
        display_name="Outsider",
        password_hash=hash_password(PASSWORD),
        platform_role="user",
    )
    platform_admin = User(
        username="platformadmin",
        display_name="Admin",
        password_hash=hash_password(PASSWORD),
        platform_role="admin",
    )
    db.add_all([owner, member, outsider, platform_admin])
    db.flush()
    team = Team(name="产品组", created_by=owner.id)
    db.add(team)
    db.flush()
    db.add_all(
        [
            TeamMembership(team_id=team.id, user_id=owner.id, role="owner"),
            TeamMembership(team_id=team.id, user_id=member.id, role="member"),
        ]
    )
    conversation = Conversation(title="东煌纪分析", owner_user_id=owner.id)
    db.add(conversation)
    db.flush()
    db.add(ConversationShare(conversation_id=conversation.id, team_id=team.id, created_by=owner.id))
    db.commit()
    ids = {
        "team_id": team.id,
        "conversation_id": conversation.id,
        "owner_id": owner.id,
        "member_id": member.id,
    }
    db.close()
    return ids


def test_private_conversation_is_hidden_from_other_users(app, session_factory):
    seed = _seed(session_factory)
    outsider = _login(app, "outsider")

    assert outsider.get(
        f"/api/conversations/{seed['conversation_id']}"
    ).status_code == 404


def test_platform_admin_has_no_private_content_override(app, session_factory):
    seed = _seed(session_factory)
    private = None
    owner = _login(app, "owner")
    private = owner.post("/api/conversations", json={}).json()
    admin = _login(app, "platformadmin")

    assert admin.get(f"/api/conversations/{private['id']}").status_code == 404


def test_team_share_is_read_only_and_cloneable(app, session_factory):
    seed = _seed(session_factory)
    member = _login(app, "member")

    assert member.get(
        f"/api/conversations/{seed['conversation_id']}"
    ).status_code == 200
    shared = member.get("/api/conversations?scope=shared").json()
    assert shared[0]["id"] == seed["conversation_id"]
    assert member.patch(
        f"/api/conversations/{seed['conversation_id']}",
        json={"title": "修改"},
    ).status_code == 403
    assert member.post(
        f"/api/conversations/{seed['conversation_id']}/messages/stream",
        json={"content": "继续", "products": ["东煌纪"], "sections": []},
    ).status_code == 403

    clone = member.post(f"/api/conversations/{seed['conversation_id']}/clone")
    assert clone.status_code == 201
    assert clone.json()["owner_user_id"] == seed["member_id"]
