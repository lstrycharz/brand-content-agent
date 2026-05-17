"""Brand voice generator: turns a one-line description into brand_guide.json."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def _isolated_paths(tmp_path, monkeypatch):
    from agent import config

    monkeypatch.setattr(config.settings, "brand_guide_path",
                        tmp_path / "brand_guide.json")
    yield


FAKE_GUIDE = {
    "vertical": "skincare",
    "target_audience": "adults building an evidence-based routine",
    "tone": "science-backed, no-nonsense, educational",
    "vocabulary_level": "accessible",
    "values": ["transparency", "evidence-first"],
    "dos": ["cite research", "use active voice"],
    "donts": ["no clickbait", "no fabricated stats"],
    "voice_examples": [
        "Niacinamide reduces sebum production at concentrations of 2-5%.",
        "Skip the toner step if your cleanser already does its job.",
    ],
}


class TestBrandVoiceGenerate:
    def test_returns_structured_guide_with_required_fields(self):
        from agent import brand_voice

        with patch.object(brand_voice, "_call_claude_for_brand_guide",
                          return_value=FAKE_GUIDE):
            guide = brand_voice.generate("Science-backed and no-nonsense.")

        for required in ("tone", "vocabulary_level", "values", "dos",
                         "donts", "voice_examples"):
            assert required in guide, f"missing field {required}"

    def test_writes_guide_to_disk(self):
        from agent import brand_voice
        from agent.config import settings

        with patch.object(brand_voice, "_call_claude_for_brand_guide",
                          return_value=FAKE_GUIDE):
            brand_voice.generate("Science-backed and no-nonsense.")

        assert settings.brand_guide_path.exists()
        stored = json.loads(settings.brand_guide_path.read_text(encoding="utf-8"))
        assert stored == FAKE_GUIDE

    def test_raises_when_description_is_blank(self):
        from agent import brand_voice

        with pytest.raises(ValueError, match="description"):
            brand_voice.generate("   ")

    def test_raises_when_llm_response_missing_required_field(self):
        from agent import brand_voice

        with patch.object(brand_voice, "_call_claude_for_brand_guide",
                          return_value={"tone": "x"}):
            with pytest.raises(ValueError, match="brand guide"):
                brand_voice.generate("anything")


class TestBrandVoiceLoad:
    def test_load_returns_none_when_no_file(self):
        from agent import brand_voice
        from agent.config import settings

        assert not settings.brand_guide_path.exists()
        assert brand_voice.load() is None

    def test_load_returns_dict_when_file_exists(self):
        from agent import brand_voice
        from agent.config import settings

        settings.brand_guide_path.write_text(
            json.dumps(FAKE_GUIDE), encoding="utf-8",
        )
        assert brand_voice.load() == FAKE_GUIDE
