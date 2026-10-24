from backend.app.core.database import database_health


def test_database_health_executes_real_session(session_factory):
    result = database_health(session_factory)

    assert result == {"status": "ready", "dialect": "sqlite"}
