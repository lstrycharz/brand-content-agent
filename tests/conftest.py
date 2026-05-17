"""Shared pytest fixtures."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from sqlmodel import Session, SQLModel, create_engine

from agent import db as db_module
from agent.db import Topic


@pytest.fixture
def temp_db(tmp_path: Path) -> Iterator[Path]:
    """Provide a temporary SQLite DB for a single test."""
    db_path = tmp_path / "test.sqlite"
    db_module.reset_engine()
    engine = create_engine(f"sqlite:///{db_path}", echo=False)
    SQLModel.metadata.create_all(engine)
    db_module._engine = engine
    yield db_path
    db_module.reset_engine()


@pytest.fixture
def db_session(temp_db: Path) -> Iterator[Session]:
    with Session(db_module._engine) as session:
        yield session


@pytest.fixture
def sample_topics(db_session: Session) -> list[Topic]:
    """Seed the DB with three topics of varying priority."""
    topics = [
        Topic(title="How to treat hormonal acne", keyword="hormonal acne treatment",
              category="acne", difficulty="intermediate", priority=10),
        Topic(title="Retinol vs retinoid explained", keyword="retinol vs retinoid",
              category="ingredients", difficulty="advanced", priority=7),
        Topic(title="Skincare routine for sensitive skin", keyword="sensitive skin routine",
              category="routine", difficulty="beginner", priority=5),
    ]
    for t in topics:
        db_session.add(t)
    db_session.commit()
    for t in topics:
        db_session.refresh(t)
    return topics


@pytest.fixture
def fake_anthropic_client() -> MagicMock:
    """Mock Anthropic SDK client; tests configure return values per stage."""
    client = MagicMock()
    return client


@pytest.fixture
def fake_research_findings() -> dict:
    return {
        "summary": "Hormonal acne is caused by androgen fluctuations affecting sebum production.",
        "key_points": [
            "Androgens trigger excess sebum",
            "Common in adult women aged 25-40",
            "Topical retinoids and spironolactone are first-line treatments",
        ],
        "sources": [
            {"url": "https://example.com/derm", "title": "Hormonal Acne Overview"},
            {"url": "https://example.com/treatment", "title": "Treatment Options"},
        ],
    }


@pytest.fixture
def fake_outline() -> dict:
    return {
        "h1": "How to Treat Hormonal Acne: A Complete Guide",
        "h2_sections": [
            {"heading": "Understanding Hormonal Acne",
             "key_points": ["Definition", "Who gets it"]},
            {"heading": "Root Causes",
             "key_points": ["Androgens", "Stress", "Diet"]},
            {"heading": "Treatment Options",
             "key_points": ["Topical retinoids", "Spironolactone", "Lifestyle"]},
            {"heading": "When to See a Dermatologist",
             "key_points": ["Severity signs", "Scarring risk"]},
        ],
        "cta": "Build your evidence-based routine with our ingredient guide.",
        "estimated_words": 1200,
        "seo_meta": "Hormonal acne is treatable. Learn the science-backed causes and treatments.",
    }
