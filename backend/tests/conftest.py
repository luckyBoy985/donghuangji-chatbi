from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from backend.app.core.database import get_db
from backend.app.core.config import settings
from backend.app.main import create_app
from backend.app.models.base import Base


@pytest.fixture(autouse=True)
def test_environment(monkeypatch):
    monkeypatch.setattr(settings, "app_env", "development")
    monkeypatch.setattr(settings, "bootstrap_admin_token", "test-bootstrap-token")


@pytest.fixture
def session_factory(tmp_path) -> sessionmaker[Session]:
    engine = create_engine(
        f"sqlite:///{(tmp_path / 'test.db').as_posix()}",
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(connection, _record):
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


@pytest.fixture
def app(session_factory):
    app = create_app(init_database=False)

    def _test_db():
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = _test_db
    yield app


@pytest.fixture
def client(app) -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def auth_client(app, monkeypatch) -> Iterator[TestClient]:
    monkeypatch.setattr(settings, "bootstrap_admin_token", "test-bootstrap-token")
    with TestClient(app) as test_client:
        response = test_client.post(
            "/api/auth/setup",
            json={
                "bootstrap_token": "test-bootstrap-token",
                "username": "testadmin",
                "display_name": "测试管理员",
                "password": "CorrectHorseBatteryStaple",
            },
        )
        assert response.status_code == 201
        yield test_client
