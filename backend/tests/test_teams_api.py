from fastapi.testclient import TestClient

from backend.app.core.config import settings
from backend.app.core.security import hash_password
from backend.app.models.identity import Team, TeamMembership, User

PASSWORD = "CorrectHorseBatteryStaple"


def _seed_team(session_factory, *, viewer_role: str = "admin"):
    db = session_factory()
    owner = User(
        username="owner",
        display_name="Owner",
        password_hash=hash_password(PASSWORD),
        platform_role="user",
    )
    viewer = User(
        username="viewer",
        display_name="Viewer",
        password_hash=hash_password(PASSWORD),
        platform_role="user",
    )
    db.add_all([owner, viewer])
    db.flush()
    team = Team(name="产品组", created_by=owner.id)
    db.add(team)
    db.flush()
    db.add_all(
        [
            TeamMembership(team_id=team.id, user_id=owner.id, role="owner"),
            TeamMembership(team_id=team.id, user_id=viewer.id, role=viewer_role),
        ]
    )
    db.commit()
    result = {
        "team_id": team.id,
        "owner_id": owner.id,
        "viewer_id": viewer.id,
    }
    db.close()
    return result


def _login(app, username: str):
    client = TestClient(app)
    response = client.post(
        "/api/auth/login",
        json={"username": username, "password": PASSWORD},
    )
    assert response.status_code == 200
    return client


def test_team_admin_cannot_create_owner_invitation(app, session_factory):
    fixture = _seed_team(session_factory, viewer_role="admin")
    viewer = _login(app, "viewer")

    response = viewer.post(
        f"/api/teams/{fixture['team_id']}/invitations",
        json={"role": "owner", "max_uses": 1, "expires_in_days": 7},
    )

    assert response.status_code == 403


def test_last_owner_cannot_be_demoted(app, session_factory):
    fixture = _seed_team(session_factory)
    owner = _login(app, "owner")

    response = owner.patch(
        f"/api/teams/{fixture['team_id']}/members/{fixture['owner_id']}",
        json={"role": "member"},
    )

    assert response.status_code == 409


def test_invitation_registers_new_user_into_team(
    app, session_factory, monkeypatch
):
    monkeypatch.setattr(settings, "bootstrap_admin_token", "bootstrap")
    fixture = _seed_team(session_factory)
    owner = _login(app, "owner")
    invitation = owner.post(
        f"/api/teams/{fixture['team_id']}/invitations",
        json={"role": "member", "max_uses": 1, "expires_in_days": 7},
    )
    assert invitation.status_code == 201
    code = invitation.json()["code"]

    new_user = TestClient(app)
    registered = new_user.post(
        "/api/auth/register-with-invite",
        json={
            "code": code,
            "username": "newmember",
            "display_name": "新成员",
            "password": PASSWORD,
        },
    )

    assert registered.status_code == 201
    assert registered.json()["teams"][0]["role"] == "member"
    assert new_user.get("/api/me").status_code == 200
