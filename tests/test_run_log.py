"""RUN_LOG.md regeneration from the runs table."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def _isolated_paths(tmp_path, monkeypatch):
    from agent import config, db

    monkeypatch.setattr(config.settings, "db_path", tmp_path / "test.sqlite")
    monkeypatch.setattr(config.settings, "drafts_dir", tmp_path / "drafts")
    monkeypatch.setattr(config.settings, "run_log_path", tmp_path / "RUN_LOG.md")
    db.reset_engine()
    yield
    db.reset_engine()


def _seed_topic(title: str = "How to treat hormonal acne", keyword: str = "hormonal acne"):
    from agent.db import Topic, session_scope

    with session_scope() as s:
        t = Topic(title=title, keyword=keyword, category="acne", priority=10)
        s.add(t)
        s.flush()
        s.refresh(t)
        s.expunge(t)
    return t


def _seed_run(run_id: str, topic_id: int, *, status: str = "success",
              word_count: int | None = 1200, output_file: str | None = None,
              image_file: str | None = None, error: str | None = None,
              completed_at: datetime | None = None):
    from agent.db import Draft, Run, session_scope, utcnow

    completed_at = completed_at or utcnow()
    with session_scope() as s:
        s.add(Run(
            run_id=run_id, topic_id=topic_id, status=status,
            started_at=utcnow(), completed_at=completed_at,
            output_file=output_file, image_file=image_file,
            error_message=error,
        ))
        if status == "success" and output_file:
            s.add(Draft(
                run_id=run_id, file_path=output_file,
                image_path=image_file, title="t",
                word_count=word_count or 0,
                tone_score=4.5, seo_score=4.0,
            ))


class TestRunLogFormatter:
    def test_empty_runs_produces_placeholder(self):
        from agent.run_log import _format_run_log

        md = _format_run_log(runs=[], topics_by_id={})
        assert "Run Log" in md
        assert "No runs yet" in md

    def test_renders_latest_run_section_and_table(self):
        from agent.run_log import regenerate

        topic = _seed_topic()
        _seed_run("r1", topic.id, output_file="drafts/a.md",
                  image_file="drafts/a-hero.png", word_count=1210)

        path = regenerate()
        text = path.read_text(encoding="utf-8")

        assert "# Run Log" in text
        assert "## Latest run" in text
        assert topic.title in text
        assert "1210" in text
        assert "drafts/a.md" in text
        assert "drafts/a-hero.png" in text
        assert "| Date | Topic | Status | Words | Output |" in text

    def test_latest_run_is_most_recently_completed(self):
        from agent.run_log import regenerate

        topic = _seed_topic()
        # older completion
        _seed_run("r-old", topic.id, output_file="drafts/old.md",
                  completed_at=datetime(2026, 1, 1, 10, 0))
        # newer completion
        _seed_run("r-new", topic.id, output_file="drafts/new.md",
                  completed_at=datetime(2026, 5, 17, 6, 0))

        text = regenerate().read_text(encoding="utf-8")
        latest_section = text.split("## All runs")[0]
        assert "drafts/new.md" in latest_section
        assert "drafts/old.md" not in latest_section
        # both appear in the all-runs table (basename only)
        all_runs = text.split("## All runs")[1]
        assert "new.md" in all_runs
        assert "old.md" in all_runs

    def test_failed_runs_show_error_and_no_output_columns(self):
        from agent.run_log import regenerate

        topic = _seed_topic()
        _seed_run("r-fail", topic.id, status="failed", word_count=None,
                  output_file=None, error="quality retry exhausted")

        text = regenerate().read_text(encoding="utf-8")
        assert "failed" in text.lower()
        assert "quality retry exhausted" in text


class TestRunnerWritesRunLog:
    """The runner regenerates RUN_LOG.md after every run, success or fail."""

    def test_success_run_writes_run_log(self):
        from agent import runner
        from agent.config import settings
        from agent.db import Topic, session_scope
        from agent.stages import draft, image, outline, quality, research

        with session_scope() as s:
            s.add(Topic(title="A topic about hormonal acne",
                        keyword="hormonal acne", category="acne", priority=10))

        good_outline = {
            "h1": "A Topic about Hormonal Acne",
            "h2_sections": [{"heading": h, "key_points": []}
                            for h in ("A", "B", "C")],
            "cta": "x", "estimated_words": 1200, "seo_meta": "y",
        }
        good_md = (
            "# A Topic about Hormonal Acne\n\n"
            + ("Hormonal acne info here every paragraph. " * 6) + "\n\n"
            "## A\n\n" + ("Studies show hormonal acne is treatable. " * 80) + "\n\n"
            "## B\n\n" + ("Hormonal acne treatments include retinoids. " * 80) + "\n\n"
            "## C\n\n" + ("Hormonal acne can be managed daily. " * 40)
        )

        with patch.object(research, "_call_claude_with_search",
                          return_value={"summary": "s", "key_points": ["k"],
                                        "sources": []}), \
             patch.object(outline, "_call_claude_for_outline", return_value=good_outline), \
             patch.object(draft, "_call_claude_for_draft", return_value=good_md), \
             patch.object(quality, "_call_claude_for_tone_eval",
                          return_value={"score": 4.5, "feedback": ""}), \
             patch.object(quality, "_call_claude_for_hallucination_check",
                          return_value={"passed": True, "unsupported_claims": []}), \
             patch.object(image, "_call_fal_for_image",
                          return_value=b"\x89PNG" + b"x" * 100):
            runner.run_once()

        log = Path(settings.run_log_path).read_text(encoding="utf-8")
        # log uses the topic title (not the h1), which we seeded lowercase
        assert "A topic about hormonal acne" in log
        assert "## Latest run" in log

    def test_failed_run_also_writes_run_log_with_error(self):
        from agent import runner
        from agent.config import settings
        from agent.db import Topic, session_scope
        from agent.stages import research

        with session_scope() as s:
            s.add(Topic(title="x", keyword="x", category="x", priority=1))

        with patch.object(research, "_call_claude_with_search",
                          side_effect=RuntimeError("boom")):
            with pytest.raises(RuntimeError):
                runner.run_once()

        log = Path(settings.run_log_path).read_text(encoding="utf-8")
        assert "failed" in log.lower()
        assert "boom" in log
