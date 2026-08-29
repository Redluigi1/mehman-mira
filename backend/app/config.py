from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "mira-backend"
    debug: bool = False

    data_dir: Path = BACKEND_ROOT / "data"
    sqlite_path: Path = BACKEND_ROOT / "data" / "runtime" / "mira.db"

    llm_backend: str = "claude_cli"  # claude_cli | anthropic_api | replay
    llm_model: str = "haiku"
    llm_timeout_s: float = 30.0
    anthropic_api_key: str | None = None

    today_override: str | None = None  # ISO date; lets demos anchor "today" deterministically

    cors_origins: list[str] = ["http://localhost:5173"]


@lru_cache
def get_settings() -> Settings:
    return Settings()
