"""Unit tests for each agent stage. Mocks at function boundaries (no real LLM/web)."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from sqlmodel import select

from agent.db import Run


# ---------------------------------------------------------------------------
# Stage 1: Init
# ---------------------------------------------------------------------------


class TestInitStage:
    def test_selects_highest_priority_pending_topic(self, sample_topics, db_session):
        from agent.stages import init

        topic, run_id = init.run()

        assert topic.title == "How to treat hormonal acne"  # priority 10
        assert run_id

    def test_creates_run_record_with_in_progress_status(self, sample_topics, db_session):
        from agent.stages import init

        _, run_id = init.run()

        run = db_session.exec(select(Run).where(Run.run_id == run_id)).one()
        assert run.status == "in_progress"
        assert run.current_stage == "init"

    def test_skips_topics_already_processed(self, sample_topics, db_session):
        from agent.stages import init

        # mark highest priority as already processed
        sample_topics[0].status = "processed"
        db_session.add(sample_topics[0])
        db_session.commit()

        topic, _ = init.run()
        assert topic.title == "Retinol vs retinoid explained"  # next priority

    def test_raises_when_no_pending_topics(self, db_session):
        from agent.stages import init

        with pytest.raises(LookupError, match="No pending topics"):
            init.run()

    def test_specific_topic_id_overrides_selection(self, sample_topics, db_session):
        from agent.stages import init

        topic, _ = init.run(topic_id=sample_topics[2].id)
        assert topic.title == "Skincare routine for sensitive skin"


# ---------------------------------------------------------------------------
# Stage 2: Research
# ---------------------------------------------------------------------------


class TestResearchStage:
    def test_returns_structured_findings(self, sample_topics, db_session, fake_research_findings):
        from agent.stages import research

        with patch.object(research, "_call_claude_with_search",
                          return_value=fake_research_findings):
            findings = research.run(topic=sample_topics[0], run_id="r1")

        assert "summary" in findings
        assert "key_points" in findings
        assert "sources" in findings
        assert len(findings["key_points"]) >= 1

    def test_caches_results_for_repeat_lookups(self, sample_topics, db_session,
                                               fake_research_findings):
        from agent.stages import research

        with patch.object(research, "_call_claude_with_search",
                          return_value=fake_research_findings) as spy:
            research.run(topic=sample_topics[0], run_id="r1")
            research.run(topic=sample_topics[0], run_id="r2")

        assert spy.call_count == 1, "second lookup should hit cache, not call Claude"


# ---------------------------------------------------------------------------
# Stage 3: Outline
# ---------------------------------------------------------------------------


class TestOutlineStage:
    def test_returns_parsed_outline_with_required_fields(
        self, sample_topics, fake_research_findings, fake_outline,
    ):
        from agent.stages import outline

        with patch.object(outline, "_call_claude_for_outline", return_value=fake_outline):
            result = outline.run(
                topic=sample_topics[0],
                research=fake_research_findings,
                brand_voice={"tone": "science-backed"},
            )

        assert "h1" in result
        assert "h2_sections" in result
        assert len(result["h2_sections"]) >= 3
        assert "cta" in result
        assert "seo_meta" in result

    def test_raises_on_malformed_llm_response(self, sample_topics, fake_research_findings):
        from agent.stages import outline

        with patch.object(outline, "_call_claude_for_outline",
                          return_value={"not_an_outline": True}):
            with pytest.raises(ValueError, match="outline"):
                outline.run(
                    topic=sample_topics[0],
                    research=fake_research_findings,
                    brand_voice={},
                )


# ---------------------------------------------------------------------------
# Stage 4: Draft
# ---------------------------------------------------------------------------


class TestDraftStage:
    def test_returns_markdown_with_frontmatter(
        self, sample_topics, fake_research_findings, fake_outline,
    ):
        from agent.stages import draft

        fake_markdown = (
            "# How to Treat Hormonal Acne\n\n"
            "## Understanding Hormonal Acne\n\n"
            "Content here. " + ("Lorem ipsum dolor sit amet. " * 200) +
            "\n\n## Root Causes\n\nMore content."
        )
        with patch.object(draft, "_call_claude_for_draft", return_value=fake_markdown):
            result = draft.run(
                topic=sample_topics[0],
                research=fake_research_findings,
                outline=fake_outline,
                brand_voice={"tone": "science-backed"},
                run_id="r1",
                feedback=None,
            )

        assert result["markdown"].startswith("---\n")  # frontmatter present
        assert "title: How to Treat Hormonal Acne" in result["markdown"]
        assert "run_id: r1" in result["markdown"]
        assert result["word_count"] >= 100

    def test_accepts_retry_feedback(self, sample_topics, fake_research_findings, fake_outline):
        from agent.stages import draft

        captured: dict = {}

        def fake_call(*, topic, research, outline, brand_voice, feedback):
            captured["feedback"] = feedback
            return "# Title\n\n" + ("word " * 200)

        with patch.object(draft, "_call_claude_for_draft", side_effect=fake_call):
            draft.run(
                topic=sample_topics[0],
                research=fake_research_findings,
                outline=fake_outline,
                brand_voice={},
                run_id="r1",
                feedback="Expand sections to reach 1200 words",
            )

        assert captured["feedback"] == "Expand sections to reach 1200 words"
