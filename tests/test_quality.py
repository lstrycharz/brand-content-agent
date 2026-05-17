"""Stage 5: quality validators + auto-retry behavior (in runner)."""

from __future__ import annotations

from unittest.mock import patch

import pytest


def _make_draft_md(
    *,
    h1: str = "How to Treat Hormonal Acne",
    keyword: str = "hormonal acne",
    h2_headings: tuple[str, ...] = ("Understanding Hormonal Acne", "Treatments",
                                    "When to See a Derm"),
    body_word_target: int = 1200,
) -> str:
    """Build a Markdown article roughly matching the target word count."""
    intro = (
        f"# {h1}\n\n"
        f"{keyword.capitalize()} affects millions of adults. "
        f"This guide explains what {keyword} is and how to treat it.\n\n"
    )
    sections = []
    per_section_words = max(50, (body_word_target - 30) // max(1, len(h2_headings)))
    for h in h2_headings:
        body = ("Studies show this consistently. " * (per_section_words // 4 + 1))
        sections.append(f"## {h}\n\n{body}\n")
    return intro + "\n".join(sections)


@pytest.fixture
def research_fixture():
    return {
        "summary": "Hormonal acne overview.",
        "key_points": [
            "Androgens trigger sebum overproduction",
            "Topical retinoids are first-line treatment",
        ],
        "sources": [{"url": "https://example.com/a", "title": "Source A"}],
    }


@pytest.fixture
def topic_fixture():
    from agent.db import Topic
    return Topic(id=1, title="How to treat hormonal acne",
                 keyword="hormonal acne", category="acne",
                 difficulty="intermediate", priority=10)


@pytest.fixture
def outline_fixture():
    return {
        "h1": "How to Treat Hormonal Acne",
        "h2_sections": [
            {"heading": "Understanding Hormonal Acne", "key_points": []},
            {"heading": "Treatments", "key_points": []},
            {"heading": "When to See a Derm", "key_points": []},
        ],
        "cta": "Build your routine.",
        "estimated_words": 1200,
        "seo_meta": "Treat hormonal acne with evidence-based steps.",
    }


def _patch_llm_evaluators(*, tone_score: float, hallucination_passed: bool,
                          hallucinated_claims: list[str] | None = None):
    """Convenience: patch both LLM-backed evaluators with given outcomes."""
    from agent.stages import quality

    tone_patch = patch.object(
        quality, "_call_claude_for_tone_eval",
        return_value={"score": tone_score,
                      "feedback": "more conversational" if tone_score < 3.5 else ""},
    )
    halluc_patch = patch.object(
        quality, "_call_claude_for_hallucination_check",
        return_value={"passed": hallucination_passed,
                      "unsupported_claims": hallucinated_claims or []},
    )
    return tone_patch, halluc_patch


# ---------------------------------------------------------------------------
# Stage 5 unit tests
# ---------------------------------------------------------------------------


class TestQualityStage:
    def test_passes_when_all_validators_pass(self, topic_fixture, research_fixture,
                                              outline_fixture):
        from agent.stages import quality

        draft_md = _make_draft_md(body_word_target=1200)
        tone_p, halluc_p = _patch_llm_evaluators(tone_score=4.5,
                                                  hallucination_passed=True)
        with tone_p, halluc_p:
            report = quality.run(
                draft_markdown=draft_md, topic=topic_fixture,
                research=research_fixture, outline=outline_fixture,
                brand_voice={"tone": "science-backed"}, run_id="r1",
            )

        assert report.passed is True
        assert report.feedback is None
        assert report.failures == []
        assert 1000 <= report.word_count <= 1400
        assert report.tone_score >= 3.5

    def test_fails_when_word_count_too_low(self, topic_fixture, research_fixture,
                                            outline_fixture):
        from agent.stages import quality

        draft_md = _make_draft_md(body_word_target=400)  # way under 1000
        tone_p, halluc_p = _patch_llm_evaluators(tone_score=4.5,
                                                  hallucination_passed=True)
        with tone_p, halluc_p:
            report = quality.run(
                draft_markdown=draft_md, topic=topic_fixture,
                research=research_fixture, outline=outline_fixture,
                brand_voice={}, run_id="r1",
            )

        assert report.passed is False
        assert "word_count_too_low" in report.failures
        assert report.feedback is not None
        assert "1200" in report.feedback or "word" in report.feedback.lower()

    def test_fails_when_keyword_missing_from_h1(self, topic_fixture, research_fixture,
                                                 outline_fixture):
        from agent.stages import quality

        draft_md = _make_draft_md(h1="A Generic Title", keyword="hormonal acne",
                                   body_word_target=1200)
        tone_p, halluc_p = _patch_llm_evaluators(tone_score=4.5,
                                                  hallucination_passed=True)
        with tone_p, halluc_p:
            report = quality.run(
                draft_markdown=draft_md, topic=topic_fixture,
                research=research_fixture, outline=outline_fixture,
                brand_voice={}, run_id="r1",
            )

        assert report.passed is False
        assert "keyword_missing_from_h1" in report.failures

    def test_fails_when_tone_score_below_threshold(self, topic_fixture, research_fixture,
                                                    outline_fixture):
        from agent.stages import quality

        draft_md = _make_draft_md(body_word_target=1200)
        tone_p, halluc_p = _patch_llm_evaluators(tone_score=2.0,
                                                  hallucination_passed=True)
        with tone_p, halluc_p:
            report = quality.run(
                draft_markdown=draft_md, topic=topic_fixture,
                research=research_fixture, outline=outline_fixture,
                brand_voice={}, run_id="r1",
            )

        assert report.passed is False
        assert "tone_below_threshold" in report.failures

    def test_fails_when_hallucination_detected(self, topic_fixture, research_fixture,
                                                outline_fixture):
        from agent.stages import quality

        draft_md = _make_draft_md(body_word_target=1200)
        tone_p, halluc_p = _patch_llm_evaluators(
            tone_score=4.5, hallucination_passed=False,
            hallucinated_claims=["80% of people see results in 3 days"],
        )
        with tone_p, halluc_p:
            report = quality.run(
                draft_markdown=draft_md, topic=topic_fixture,
                research=research_fixture, outline=outline_fixture,
                brand_voice={}, run_id="r1",
            )

        assert report.passed is False
        assert "hallucination_detected" in report.failures
        assert "80%" in report.feedback

    def test_concatenates_feedback_from_multiple_failures(self, topic_fixture,
                                                          research_fixture, outline_fixture):
        from agent.stages import quality

        draft_md = _make_draft_md(h1="A Generic Title", body_word_target=400)
        tone_p, halluc_p = _patch_llm_evaluators(tone_score=4.5,
                                                  hallucination_passed=True)
        with tone_p, halluc_p:
            report = quality.run(
                draft_markdown=draft_md, topic=topic_fixture,
                research=research_fixture, outline=outline_fixture,
                brand_voice={}, run_id="r1",
            )

        assert report.passed is False
        assert len(report.failures) >= 2  # word count + keyword missing
        assert report.feedback is not None


# ---------------------------------------------------------------------------
# Runner retry behavior
# ---------------------------------------------------------------------------


class TestRunnerRetry:
    @pytest.fixture(autouse=True)
    def _isolated_paths(self, tmp_path, monkeypatch):
        from agent import config, db
        monkeypatch.setattr(config.settings, "db_path", tmp_path / "test.sqlite")
        monkeypatch.setattr(config.settings, "drafts_dir", tmp_path / "drafts")
        monkeypatch.setattr(config.settings, "brand_guide_path",
                            tmp_path / "brand_guide.json")
        db.reset_engine()
        yield
        db.reset_engine()

    @pytest.fixture
    def one_topic(self):
        from agent.db import Topic, session_scope
        with session_scope() as s:
            s.add(Topic(title="How to treat hormonal acne",
                        keyword="hormonal acne", category="acne", priority=10))

    def test_retries_draft_once_on_quality_fail_then_succeeds(self, one_topic):
        from agent import runner
        from agent.stages import draft, outline, research

        good_outline = {
            "h1": "How to Treat Hormonal Acne",
            "h2_sections": [{"heading": h, "key_points": []}
                            for h in ("A", "B", "C")],
            "cta": "x", "estimated_words": 1200, "seo_meta": "y",
        }

        # First draft is too short; second is full length with proper structure.
        good_md = _make_draft_md(h1="How to Treat Hormonal Acne",
                                  keyword="hormonal acne",
                                  body_word_target=1200)
        drafts_to_return = [
            "# How to Treat Hormonal Acne\n\n" + ("word " * 200),  # ~200 words → fail
            good_md,                                                # passes
        ]
        draft_call_count = {"n": 0}

        def _fake_draft(**_):
            i = draft_call_count["n"]
            draft_call_count["n"] += 1
            return drafts_to_return[i]

        tone_p, halluc_p = _patch_llm_evaluators(tone_score=4.5,
                                                  hallucination_passed=True)
        with patch.object(research, "_call_claude_with_search",
                          return_value={"summary": "s", "key_points": ["k"],
                                        "sources": []}), \
             patch.object(outline, "_call_claude_for_outline", return_value=good_outline), \
             patch.object(draft, "_call_claude_for_draft", side_effect=_fake_draft), \
             tone_p, halluc_p:
            summary = runner.run_once()

        assert summary["status"] == "success"
        assert draft_call_count["n"] == 2, "draft should run twice (initial + retry)"
        assert summary["retry_count"] == 1

    def test_marks_topic_failed_review_when_retry_also_fails(self, one_topic):
        from agent import runner
        from agent.db import Topic, session_scope
        from agent.stages import draft, outline, research
        from sqlmodel import select

        good_outline = {
            "h1": "How to Treat Hormonal Acne",
            "h2_sections": [{"heading": h, "key_points": []}
                            for h in ("A", "B", "C")],
            "cta": "x", "estimated_words": 1200, "seo_meta": "y",
        }

        always_short = "# How to Treat Hormonal Acne\n\n" + ("word " * 100)

        tone_p, halluc_p = _patch_llm_evaluators(tone_score=4.5,
                                                  hallucination_passed=True)
        with patch.object(research, "_call_claude_with_search",
                          return_value={"summary": "s", "key_points": ["k"],
                                        "sources": []}), \
             patch.object(outline, "_call_claude_for_outline", return_value=good_outline), \
             patch.object(draft, "_call_claude_for_draft", return_value=always_short), \
             tone_p, halluc_p:
            with pytest.raises(runner.QualityRetryExhausted):
                runner.run_once()

        with session_scope() as s:
            topic = s.exec(select(Topic).where(
                Topic.title == "How to treat hormonal acne")).one()
            assert topic.status == "failed_review_needed"
