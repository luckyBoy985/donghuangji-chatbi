from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "东煌纪竞品情报 ChatBI"
    app_env: str = "development"
    app_host: str = "127.0.0.1"
    app_port: int = 8000
    data_dir: Path = ROOT / "data" / "runtime"
    database_url: str = Field(
        default=f"sqlite:///{(ROOT / 'data' / 'database' / 'chatbi.db').as_posix()}",
        repr=False,
    )
    redis_url: str = Field(default="redis://127.0.0.1:6379/0", repr=False)
    secret_key: str = Field(
        default="development-only-change-this-secret-key",
        repr=False,
    )
    mcp_access_token: str = Field(default="", repr=False)
    bootstrap_admin_token: str = Field(default="", repr=False)
    session_cookie_secure: bool = False
    allowed_origin: str = "http://127.0.0.1:8000"
    session_ttl_days: int = 7
    max_login_failures: int = 10
    login_window_seconds: int = 900
    s3_endpoint: str = "http://127.0.0.1:9000"
    s3_access_key: str = Field(default="chatbi", repr=False)
    s3_secret_key: str = Field(default="chatbi-local-secret", repr=False)
    s3_bucket: str = "chatbi"

    bge_m3_path: Path = ROOT / "models" / "bge-m3"
    bge_reranker_path: Path = ROOT / "models" / "bge-reranker-base"
    model_device: str = "cuda"
    embedding_dim: int = 1024

    deepseek_api_key: str = Field(default="", repr=False)
    deepseek_base_url: str = "https://api.deepseek.com/v1"
    llm_model: str = "deepseek-chat"
    llm_temperature: float = 0.2
    llm_timeout_seconds: int = 120

    qa_candidates: int = 40
    qa_top_k: int = 8
    qa_strong_score: float = 0.60
    qa_min_score: float = 0.30
    qa_min_overlap: float = 0.20
    max_message_chars: int = 2000
    audit_retention_days: int = 180
    qa_daily_limit_per_user: int = 200
    report_daily_limit_per_user: int = 30
    admin_data_daily_limit: int = 50
    qa_max_concurrency: int = 2
    qa_queue_timeout_seconds: float = 15.0
    crawl_delay_seconds: float = 1.0
    crawl_timeout_seconds: int = 25
    ingest_soft_time_limit: int = 1800
    ingest_time_limit: int = 1860
    stale_job_hours: int = 6

    cors_origins: str = (
        "http://127.0.0.1:8000,http://localhost:8000,"
        "http://127.0.0.1:5173,http://localhost:5173"
    )

    @property
    def index_path(self) -> Path:
        return self.data_dir / "index" / "local_index.pkl"

    @property
    def platform_index_path(self) -> Path:
        return self.data_dir / "index" / "platform_index.pkl"

    @property
    def platform_manifest_path(self) -> Path:
        return self.data_dir / "index" / "platform_index.manifest.json"

    @property
    def catalog_path(self) -> Path:
        return self.data_dir / "catalog.json"

    @property
    def gold_set_path(self) -> Path:
        return self.data_dir / "gold_set.jsonl"

    @property
    def allowed_origins(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]

    @property
    def use_cuda(self) -> bool:
        return self.model_device.lower().startswith("cuda")

    @model_validator(mode="after")
    def validate_production_secrets(self) -> "Settings":
        if self.app_env != "production":
            return self
        values = {
            "SECRET_KEY": self.secret_key,
            "BOOTSTRAP_ADMIN_TOKEN": self.bootstrap_admin_token,
            "MCP_ACCESS_TOKEN": self.mcp_access_token,
            "DEEPSEEK_API_KEY": self.deepseek_api_key,
        }
        minimums = {
            "SECRET_KEY": 32,
            "BOOTSTRAP_ADMIN_TOKEN": 32,
            "MCP_ACCESS_TOKEN": 32,
            "DEEPSEEK_API_KEY": 20,
        }
        invalid = [
            name
            for name, value in values.items()
            if len(value.strip()) < minimums[name]
            or value.strip().lower().startswith("replace-")
            or value.strip().startswith("development-only")
            or value.strip() == "chatbi-local-secret"
        ]
        if self.database_url.startswith("sqlite:"):
            invalid.append("DATABASE_URL")
        if invalid:
            raise ValueError(
                "生产配置无效，请检查：" + "、".join(invalid)
            )
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
