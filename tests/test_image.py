"""Stage 6: hero image generation via fal.ai Flux Schnell."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def _isolated_paths(tmp_path, monkeypatch):
    from agent import config, db

    monkeypatch.setattr(config.settings, "db_path", tmp_path / "test.sqlite")
    monkeypatch.setattr(config.settings, "drafts_dir", tmp_path / "drafts")
    db.reset_engine()
    yield
    db.reset_engine()


@pytest.fixture
def topic_fixture():
    from agent.db import Topic
    return Topic(id=1, title="How to treat hormonal acne",
                 keyword="hormonal acne", category="acne",
                 difficulty="intermediate", priority=10)


PNG_HEADER = b"\x89PNG\r\n\x1a\n" + b"fake_image_bytes" * 100


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------


class TestImagePrompt:
    def test_prompt_includes_topic_category_and_vertical(self, topic_fixture):
        from agent.stages.image import _build_image_prompt

        brand_voice = {"vertical": "skincare"}
        prompt = _build_image_prompt(topic=topic_fixture, brand_voice=brand_voice)

        assert "hormonal acne" in prompt.lower() or "acne" in prompt.lower()
        assert "skincare" in prompt.lower()
        assert "no text" in prompt.lower()

    def test_prompt_works_for_any_vertical(self, topic_fixture):
        """Same builder should drop in for pet food, supplements, etc."""
        from agent.stages.image import _build_image_prompt

        for vertical in ("pet food", "supplements", "fitness apparel"):
            prompt = _build_image_prompt(
                topic=topic_fixture, brand_voice={"vertical": vertical},
            )
            assert vertical in prompt.lower()

    def test_prompt_does_not_reference_models_or_brands(self, topic_fixture):
        from agent.stages.image import _build_image_prompt

        prompt = _build_image_prompt(
            topic=topic_fixture, brand_voice={"vertical": "skincare"},
        )
        lowered = prompt.lower()
        for forbidden in ("celebrity", "model named", "brand:"):
            assert forbidden not in lowered


# ---------------------------------------------------------------------------
# Run stage
# ---------------------------------------------------------------------------


class TestImageStage:
    def test_run_saves_png_to_drafts_dir(self, topic_fixture):
        from agent.config import settings
        from agent.stages import image

        with patch.object(image, "_call_fal_for_image", return_value=PNG_HEADER):
            path = image.run(topic=topic_fixture, slug="test-slug",
                             date_str="2026-05-17", run_id="r1")

        assert path.exists()
        assert path.parent == settings.drafts_dir
        assert path.suffix == ".png"
        assert path.read_bytes() == PNG_HEADER

    def test_filename_uses_date_slug_hero_format(self, topic_fixture):
        from agent.stages import image

        with patch.object(image, "_call_fal_for_image", return_value=PNG_HEADER):
            path = image.run(topic=topic_fixture, slug="hormonal-acne",
                             date_str="2026-05-17", run_id="r1")

        assert path.name == "2026-05-17-hormonal-acne-hero.png"

    def test_returns_path_even_when_drafts_dir_missing(self, topic_fixture, tmp_path):
        from agent.config import settings
        from agent.stages import image

        # remove the (autouse-created) drafts dir to verify auto-creation
        settings.drafts_dir = tmp_path / "fresh-drafts"
        assert not settings.drafts_dir.exists()

        with patch.object(image, "_call_fal_for_image", return_value=PNG_HEADER):
            path = image.run(topic=topic_fixture, slug="x",
                             date_str="2026-05-17", run_id="r1")

        assert path.exists()

    def test_raises_when_fal_returns_empty_bytes(self, topic_fixture):
        from agent.stages import image

        with patch.object(image, "_call_fal_for_image", return_value=b""):
            with pytest.raises(ValueError, match="empty"):
                image.run(topic=topic_fixture, slug="x",
                          date_str="2026-05-17", run_id="r1")


# ---------------------------------------------------------------------------
# Runner integration: image path reaches the frontmatter
# ---------------------------------------------------------------------------


class TestRunnerImageIntegration:
    @pytest.fixture
    def one_topic(self):
        from agent.db import Topic, session_scope
        with session_scope() as s:
            s.add(Topic(title="Hormonal acne basics",
                        keyword="hormonal acne", category="acne", priority=10))

    def test_finished_markdown_references_hero_image(self, one_topic):
        from agent import runner
        from agent.stages import draft, image, outline, quality, research

        good_outline = {
            "h1": "Hormonal Acne Basics",
            "h2_sections": [{"heading": h, "key_points": []}
                            for h in ("A", "B", "C")],
            "cta": "x", "estimated_words": 1200, "seo_meta": "y",
        }
        good_md = (
            "# Hormonal Acne Basics: a Guide\n\n"
            + ("Hormonal acne affects many adults daily. " * 5) + "\n\n"
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
             patch.object(image, "_call_fal_for_image", return_value=PNG_HEADER):
            summary = runner.run_once()

        out_md = Path(summary["output_file"]).read_text(encoding="utf-8")
        assert "hero_image:" in out_md
        # the hero_image value is a sibling .png file
        image_path = Path(summary["image_file"])
        assert image_path.exists()
        assert image_path.name.endswith("-hero.png")
        assert image_path.name in out_md
