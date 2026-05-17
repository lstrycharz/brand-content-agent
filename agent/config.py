"""Configuration loaded from .env and environment variables."""

import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict


# Push .env into os.environ so third-party libraries that read directly from
# the environment (notably fal_client, which looks up FAL_KEY) see the values.
# pydantic-settings reads .env into the Settings object but doesn't propagate
# to os.environ.
load_dotenv()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    anthropic_api_key: str = ""
    fal_key: str = ""

    db_path: Path = Path("db/brandcontent.sqlite")
    drafts_dir: Path = Path("drafts")
    brand_guide_path: Path = Path("data/brand_guide.json")
    seed_topics_path: Path = Path("data/seed_topics.csv")
    run_log_path: Path = Path("RUN_LOG.md")

    drafting_model: str = "claude-sonnet-4-6"
    # Word count: aim for 1100, accept 900–1300. The buffer keeps near-miss
    # drafts from triggering the expensive quality-retry loop.
    target_word_count: int = 1100
    word_count_min: int = 900
    word_count_max: int = 1300
    tone_score_threshold: float = 3.5
    research_cache_days: int = 7

    def ensure_dirs(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.drafts_dir.mkdir(parents=True, exist_ok=True)
        self.brand_guide_path.parent.mkdir(parents=True, exist_ok=True)


settings = Settings()

# Belt-and-braces: if .env wasn't found by load_dotenv (e.g. running from a
# different cwd), still ensure the keys we know about reach os.environ.
if settings.fal_key and not os.environ.get("FAL_KEY"):
    os.environ["FAL_KEY"] = settings.fal_key
if settings.anthropic_api_key and not os.environ.get("ANTHROPIC_API_KEY"):
    os.environ["ANTHROPIC_API_KEY"] = settings.anthropic_api_key
