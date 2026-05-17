"""SQLite schema and session helpers using sqlmodel."""

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from sqlmodel import Field, Session, SQLModel, create_engine


def utcnow() -> datetime:
    """Return naive UTC datetime. SQLite stores datetimes without tzinfo, so we
    keep everything naive-but-UTC to avoid mixed-tz comparison errors."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Topic(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    title: str = Field(unique=True, index=True)
    keyword: str
    category: str
    difficulty: str = "intermediate"
    priority: int = 5
    status: str = Field(default="pending", index=True)
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class Run(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    run_id: str = Field(unique=True, index=True)
    topic_id: int = Field(foreign_key="topic.id")
    status: str
    current_stage: str | None = None
    started_at: datetime = Field(default_factory=utcnow)
    completed_at: datetime | None = None
    error_message: str | None = None
    output_file: str | None = None
    image_file: str | None = None


class Draft(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    run_id: str = Field(unique=True, foreign_key="run.run_id")
    file_path: str
    image_path: str | None = None
    title: str
    word_count: int
    tone_score: float = 0.0
    seo_score: float = 0.0
    created_at: datetime = Field(default_factory=utcnow)


class ResearchCache(SQLModel, table=True):
    topic_title: str = Field(primary_key=True)
    search_results: str
    cached_at: datetime = Field(default_factory=utcnow)
    expires_at: datetime


_engine = None


def get_engine(db_path: Path | None = None):
    global _engine
    if _engine is None or db_path is not None:
        from agent.config import settings

        path = db_path or settings.db_path
        path.parent.mkdir(parents=True, exist_ok=True)
        _engine = create_engine(f"sqlite:///{path}", echo=False)
        SQLModel.metadata.create_all(_engine)
    return _engine


def reset_engine() -> None:
    """Reset the global engine; used between tests."""
    global _engine
    _engine = None


@contextmanager
def session_scope(db_path: Path | None = None) -> Iterator[Session]:
    engine = get_engine(db_path)
    session = Session(engine)
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
