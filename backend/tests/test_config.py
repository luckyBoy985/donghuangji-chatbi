import pytest
from pydantic import ValidationError

from backend.app.core.config import Settings


def test_settings_repr_hides_sensitive_values():
    settings = Settings(
        _env_file=None,
        database_url="postgresql+psycopg://chatbi:db-secret@db/chatbi",
        secret_key="session-secret-value",
        mcp_access_token="mcp-secret-value",
        bootstrap_admin_token="bootstrap-secret-value",
        deepseek_api_key="sk-sensitive-value",
        s3_secret_key="s3-secret-value",
    )

    rendered = repr(settings)

    for secret in (
        "db-secret",
        "session-secret-value",
        "mcp-secret-value",
        "bootstrap-secret-value",
        "sk-sensitive-value",
        "s3-secret-value",
    ):
        assert secret not in rendered


def test_production_rejects_placeholder_secrets():
    with pytest.raises(ValidationError, match="生产配置"):
        Settings(
            _env_file=None,
            app_env="production",
            secret_key="replace-with-at-least-32-random-bytes",
            bootstrap_admin_token="replace-with-at-least-32-random-bytes",
            mcp_access_token="replace-with-at-least-32-random-bytes",
            deepseek_api_key="replace-with-deepseek-key",
        )
