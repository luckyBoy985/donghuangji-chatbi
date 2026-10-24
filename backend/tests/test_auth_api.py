from backend.app.core.config import settings


PASSWORD = "CorrectHorseBatteryStaple"


def _setup(client, token="test-bootstrap-token"):
    return client.post(
        "/api/auth/setup",
        json={
            "bootstrap_token": token,
            "username": "admin",
            "display_name": "平台管理员",
            "password": PASSWORD,
        },
    )


def test_setup_creates_one_admin_and_disables_itself(client, monkeypatch):
    monkeypatch.setattr(settings, "bootstrap_admin_token", "test-bootstrap-token")

    first = _setup(client)

    assert first.status_code == 201
    assert first.json()["username"] == "admin"
    assert first.json()["platform_role"] == "admin"
    assert "chatbi_session" in first.cookies
    second = _setup(client, token="another-token")
    assert second.status_code == 410


def test_login_cookie_is_httponly_and_logout_revokes(client, monkeypatch):
    monkeypatch.setattr(settings, "bootstrap_admin_token", "test-bootstrap-token")
    _setup(client)
    client.post("/api/auth/logout")
    client.cookies.clear()

    response = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": PASSWORD},
    )

    assert response.status_code == 200
    set_cookie = response.headers["set-cookie"].lower()
    assert "httponly" in set_cookie
    assert "samesite=lax" in set_cookie
    assert client.get("/api/me").status_code == 200
    assert client.post("/api/auth/logout").status_code == 204
    assert client.get("/api/me").status_code == 401


def test_login_failure_does_not_reveal_account_state(client, monkeypatch):
    monkeypatch.setattr(settings, "bootstrap_admin_token", "test-bootstrap-token")
    _setup(client)
    client.cookies.clear()

    unknown = client.post(
        "/api/auth/login",
        json={"username": "missing", "password": PASSWORD},
    )
    wrong = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "WrongPasswordValue"},
    )

    assert unknown.status_code == wrong.status_code == 401
    assert unknown.json()["detail"] == wrong.json()["detail"]


def test_profile_and_password_change_revoke_old_session(client, monkeypatch):
    monkeypatch.setattr(settings, "bootstrap_admin_token", "test-bootstrap-token")
    _setup(client)
    new_password = "NewCorrectHorseBatteryStaple"

    assert client.patch(
        "/api/me", json={"display_name": "新管理员"}
    ).status_code == 200
    changed = client.post(
        "/api/auth/password",
        json={
            "current_password": PASSWORD,
            "new_password": new_password,
        },
    )

    assert changed.status_code == 204
    assert client.get("/api/me").status_code == 401
    logged_in = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": new_password},
    )
    assert logged_in.status_code == 200


def test_production_rejects_missing_or_wrong_origin(client, monkeypatch):
    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(settings, "bootstrap_admin_token", "test-bootstrap-token")
    monkeypatch.setattr(settings, "allowed_origin", "http://127.0.0.1")

    missing = _setup(client)
    wrong = client.post(
        "/api/auth/setup",
        headers={"Origin": "https://evil.example"},
        json={
            "bootstrap_token": "test-bootstrap-token",
            "username": "admin",
            "display_name": "平台管理员",
            "password": PASSWORD,
        },
    )
    accepted = client.post(
        "/api/auth/setup",
        headers={"Origin": "http://127.0.0.1"},
        json={
            "bootstrap_token": "test-bootstrap-token",
            "username": "admin",
            "display_name": "平台管理员",
            "password": PASSWORD,
        },
    )

    assert missing.status_code == 403
    assert wrong.status_code == 403
    assert accepted.status_code == 201


def test_login_locks_after_repeated_failures(client, monkeypatch):
    monkeypatch.setattr(settings, "bootstrap_admin_token", "test-bootstrap-token")
    monkeypatch.setattr(settings, "max_login_failures", 2)
    _setup(client)
    client.post("/api/auth/logout")
    client.cookies.clear()

    for _ in range(2):
        failed = client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "WrongPasswordValue"},
        )
        assert failed.status_code == 401

    locked = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": PASSWORD},
    )

    assert locked.status_code == 429
    assert client.get("/api/me").status_code == 401


def test_login_failure_audit_records_client_ip(
    client, session_factory, monkeypatch
):
    from backend.app.models.audit import AuditLog

    monkeypatch.setattr(settings, "bootstrap_admin_token", "test-bootstrap-token")
    _setup(client)
    client.post("/api/auth/logout")
    client.cookies.clear()
    client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "WrongPasswordValue"},
    )

    db = session_factory()
    audit = db.query(AuditLog).filter(
        AuditLog.action == "auth.login_failed"
    ).first()

    assert audit is not None
    assert audit.ip_address
    db.close()
