from fastapi.testclient import TestClient
from sqlalchemy import select

from backend.app.core.security import hash_password
from backend.app.models.audit import AuditLog
from backend.app.models.identity import User

PASSWORD = "CorrectHorseBatteryStaple"


def _seed_member(session_factory) -> str:
    db = session_factory()
    user = User(
        username="member",
        display_name="普通成员",
        password_hash=hash_password(PASSWORD),
        platform_role="user",
    )
    db.add(user)
    db.commit()
    user_id = user.id
    db.close()
    return user_id


def test_disabling_user_revokes_sessions_and_writes_audit(
    app, auth_client, session_factory
):
    user_id = _seed_member(session_factory)
    member = TestClient(app)
    assert member.post(
        "/api/auth/login",
        json={"username": "member", "password": PASSWORD},
    ).status_code == 200

    response = auth_client.patch(
        f"/api/admin/users/{user_id}",
        json={"status": "disabled"},
    )

    assert response.status_code == 200
    assert member.get("/api/me").status_code == 401
    db = session_factory()
    audit = db.scalar(
        select(AuditLog).where(
            AuditLog.action == "user.disable",
            AuditLog.resource_id == user_id,
        )
    )
    assert audit is not None
    db.close()


def test_admin_creates_team_with_owner(auth_client, session_factory):
    user_id = _seed_member(session_factory)

    response = auth_client.post(
        "/api/admin/teams",
        json={
            "name": "发行团队",
            "description": "发行与运营",
            "owner_user_id": user_id,
        },
    )

    assert response.status_code == 201
    teams = auth_client.get("/api/admin/teams").json()
    assert teams[0]["name"] == "发行团队"
    assert teams[0]["owner_count"] == 1


def test_admin_reset_password_returns_temporary_password_and_revokes_sessions(
    app,
    auth_client,
    session_factory,
):
    user_id = _seed_member(session_factory)
    member = TestClient(app)
    assert member.post(
        "/api/auth/login",
        json={"username": "member", "password": PASSWORD},
    ).status_code == 200

    reset = auth_client.post(f"/api/admin/users/{user_id}/reset-password")

    assert reset.status_code == 200
    temporary_password = reset.json()["temporary_password"]
    assert len(temporary_password) >= 20
    assert member.get("/api/me").status_code == 401

    temporary_login = TestClient(app)
    logged_in = temporary_login.post(
        "/api/auth/login",
        json={"username": "member", "password": temporary_password},
    )
    assert logged_in.status_code == 200
    assert logged_in.json()["must_change_password"] is True
    assert temporary_login.get("/api/catalog").status_code == 428


def test_admin_cannot_reset_own_password(auth_client):
    current = auth_client.get("/api/me").json()

    response = auth_client.post(
        f"/api/admin/users/{current['id']}/reset-password"
    )

    assert response.status_code == 409


def test_audit_filters_by_action_actor_and_time(
    auth_client, session_factory
):
    db = session_factory()
    db.add_all(
        [
            AuditLog(
                action="custom.event",
                resource_type="test",
                resource_id="old",
                actor_user_id=None,
                created_at="2025-01-01T00:00:00+00:00",
            ),
            AuditLog(
                action="custom.event",
                resource_type="test",
                resource_id="current",
                actor_user_id=None,
                created_at="2026-10-24T00:00:00+00:00",
            ),
        ]
    )
    db.commit()
    db.close()

    response = auth_client.get(
        "/api/admin/audit",
        params={
            "action": "custom.event",
            "start_at": "2026-01-01T00:00:00+00:00",
        },
    )

    assert response.status_code == 200
    assert [row["resource_id"] for row in response.json()] == ["current"]
