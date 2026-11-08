"""Application settings (pydantic-settings, read from environment / .env)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

API_ROOT = Path(__file__).resolve().parents[1]  # apps/api
REPO_ROOT = API_ROOT.parents[1]  # repository root

APP_VERSION = "0.1.0"


def _resolve(path: str) -> Path:
    """Relative paths are resolved against apps/api (not the current working directory)."""
    p = Path(path)
    return p if p.is_absolute() else (API_ROOT / p).resolve()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(API_ROOT / ".env"), extra="ignore")

    # Default = local SQLite file so the API runs on Windows without Docker.
    database_url: str = f"sqlite+aiosqlite:///{(API_ROOT / 'fieldshift.db').as_posix()}"
    packs_dir: str = "../../packs"
    data_dir: str = "../../data"
    frontend_origin: str = "http://localhost:3000"
    rate_limit_per_min: int = 60
    log_level: str = "info"

    @property
    def cors_origins(self) -> list[str]:
        """FRONTEND_ORIGIN, comma-separated for several origins (e.g. production + preview).

        A trailing "/" is removed: browsers send the Origin header without it, so
        "https://app.example.org/" would never match and every request would be blocked by CORS.
        """
        return [o.strip().rstrip("/") for o in self.frontend_origin.split(",") if o.strip()]

    @property
    def packs_path(self) -> Path:
        return _resolve(self.packs_dir)

    @property
    def data_path(self) -> Path:
        return _resolve(self.data_dir)

    @property
    def seed_path(self) -> Path:
        return self.data_path / "seed"


@lru_cache
def get_settings() -> Settings:
    return Settings()
