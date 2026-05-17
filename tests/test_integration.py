"""End-to-end integration test for Chunk 1: stages 1-4 mocked, output checked.

The plan calls for running the agent 5 times with different mock topics to prove
the pipeline reliably produces valid Markdown. This test does that in <1s.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from sqlmodel import select

from agent.db import Run, Topic, session_scope


@pytest.fixture(autouse=True)
def _isolated_paths(tmp_path, monkeypatch):
    """Redirect the agent's outputs to tmp paths for every test in this module."""
    from agent import config, db

    monkeypatch.setattr(config.settings, "db_path", tmp_path / "test.sqlite")
    monkeypatch.setattr(config.settings, "drafts_dir", tmp_path / "drafts")
    monkeypatch.setattr(config.settings, "brand_guide_path",
                        tmp_path / "brand_guide.json")
    db.reset_engine()
    yield
    db.reset_engine()


@pytest.fixture
def seeded_topics():
    """Five real-feeling topics so we can run the agent 5x in a row."""
    from agent.db import session_scope

    titles = [
        ("How to treat hormonal acne", "hormonal acne treatment", "acne", 10),
        ("Retinol vs retinoid explained", "retinol vs retinoid", "ingredients", 9),
        ("Skincare routine for sensitive skin", "sensitive skin routine", "routine", 8),
        ("Vitamin C serums: what to look for", "vitamin c serum", "ingredients", 7),
        ("How to layer skincare products", "skincare layering", "routine", 6),
    ]
    with session_scope() as session:
        for title, kw, cat, prio in titles:
            session.add(Topic(title=title, keyword=kw, category=cat, priority=prio))


def _fake_findings(topic_title: str) -> dict:
    return {
        "summary": f"Research summary for {topic_title}.",
        "key_points": ["Point A", "Point B", "Point C"],
        "sources": [{"url": "https://example.com/a", "title": "Source A"}],
    }


def _fake_outline(topic_title: str) -> dict:
    return {
        "h1": topic_title.title(),
        "h2_sections": [
            {"heading": "Background", "key_points": ["bg"]},
            {"heading": "Details", "key_points": ["d1", "d2"]},
            {"heading": "Takeaways", "key_points": ["t1"]},
        ],
        "cta": "Build your routine with evidence.",
        "estimated_words": 1200,
        "seo_meta": f"Everything you need to know about {topic_title}.",
    }


def _fake_markdown(topic_title: str, keyword: str) -> str:
    """Realistic-shape Markdown sized to ~1200 words to pass quality checks."""
    h1 = f"# {topic_title}: A Guide to {keyword.title()}\n\n"
    intro = f"{keyword.capitalize()} affects many people. This guide explains it. "
    intro_words = len(intro.split())
    h1_words = len(h1.split())
    h2_overhead = 6  # three "## Heading\n\n" sections
    target = 1200
    filler_target = target - h1_words - h2_overhead - intro_words * 4
    per_section = max(50, filler_target // 3)
    sentence = f"This explains {keyword} clearly. "
    sentence_words = len(sentence.split())
    repeats = max(1, per_section // sentence_words)

    body = h1 + intro * 4 + "\n\n"
    body += "## Background\n\n" + (sentence * repeats) + "\n\n"
    body += "## Details\n\n" + (sentence * repeats) + "\n\n"
    body += "## Takeaways\n\n" + (sentence * repeats)
    return body


def _llm_eval_patches():
    """Patch tone + hallucination evaluators to return pass-grade results."""
    from unittest.mock import patch as _patch

    from agent.stages import quality

    tone_p = _patch.object(
        quality, "_call_claude_for_tone_eval",
        return_value={"score": 4.5, "feedback": ""},
    )
    halluc_p = _patch.object(
        quality, "_call_claude_for_hallucination_check",
        return_value={"passed": True, "unsupported_claims": []},
    )
    return tone_p, halluc_p


def _image_patch():
    """Patch fal.ai boundary so tests never make a real image request."""
    from unittest.mock import patch as _patch

    from agent.stages import image

    return _patch.object(image, "_call_fal_for_image",
                          return_value=b"\x89PNG\r\n\x1a\n" + b"fake" * 100)


class TestFiveSuccessiveRuns:
    def test_pipeline_completes_five_times_without_overlap(self, seeded_topics):
        from agent import runner
        from agent.stages import draft, outline, research

        tone_p, halluc_p = _llm_eval_patches()
        with patch.object(research, "_call_claude_with_search",
                          side_effect=lambda *, topic, brand_voice:
                          _fake_findings(topic.title)), \
             patch.object(outline, "_call_claude_for_outline",
                          side_effect=lambda *, topic, research, brand_voice:
                          _fake_outline(topic.title)), \
             patch.object(draft, "_call_claude_for_draft",
                          side_effect=lambda *, topic, research, outline,
                          brand_voice, feedback:
                          _fake_markdown(topic.title, topic.keyword)), \
             tone_p, halluc_p, _image_patch():
            results = [runner.run_once() for _ in range(5)]

        # All runs succeeded with distinct run_ids and output files
        assert len({r["run_id"] for r in results}) == 5
        assert len({r["output_file"] for r in results}) == 5
        for r in results:
            assert r["status"] == "success"
            assert r["word_count"] >= 100
            assert Path(r["output_file"]).exists()
            content = Path(r["output_file"]).read_text(encoding="utf-8")
            assert content.startswith("---\n")
            assert f"run_id: {r['run_id']}" in content

    def test_run_records_persisted_with_success_status(self, seeded_topics):
        from agent import runner
        from agent.stages import draft, outline, research

        tone_p, halluc_p = _llm_eval_patches()
        with patch.object(research, "_call_claude_with_search",
                          side_effect=lambda *, topic, brand_voice:
                          _fake_findings(topic.title)), \
             patch.object(outline, "_call_claude_for_outline",
                          side_effect=lambda *, topic, research, brand_voice:
                          _fake_outline(topic.title)), \
             patch.object(draft, "_call_claude_for_draft",
                          side_effect=lambda *, topic, research, outline,
                          brand_voice, feedback:
                          _fake_markdown(topic.title, topic.keyword)), \
             tone_p, halluc_p, _image_patch():
            runner.run_once()
            runner.run_once()

        with session_scope() as session:
            runs = session.exec(select(Run)).all()
            assert len(runs) == 2
            for r in runs:
                assert r.status == "success"
                assert r.completed_at is not None
                assert r.output_file is not None
                assert r.error_message is None

    def test_run_record_marked_failed_when_stage_raises(self, seeded_topics):
        from agent import runner
        from agent.stages import research

        with patch.object(research, "_call_claude_with_search",
                          side_effect=RuntimeError("boom")):
            with pytest.raises(RuntimeError):
                runner.run_once()

        with session_scope() as session:
            run = session.exec(select(Run)).one()
            assert run.status == "failed"
            assert run.error_message == "boom"
