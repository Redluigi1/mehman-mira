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

    llm_backend: str = "codex_cli"  # codex_cli | claude_cli | vertex
    llm_model: str = "gpt-5.6-terra"
    llm_reasoning_effort: str = "low"
    llm_timeout_s: float = 90.0

    vertex_project: str | None = None
    vertex_location: str = "global"
    vertex_api_key: str | None = None
    google_application_credentials: str | None = None

    today_override: str | None = None  # ISO date; lets demos anchor "today" deterministically

    cors_origins: list[str] = ["http://localhost:5173"]


@lru_cache
def get_settings() -> Settings:
    return Settings()
