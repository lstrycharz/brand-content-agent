"""Generate a structured brand guide from a one-line description.

Claude turns a sentence like
    "Science-backed and no-nonsense, like The Ordinary. Educate, don't sell."
into a structured JSON file that every Draft and Tone-eval prompt later
references. Stored at `settings.brand_guide_path` (default
`data/brand_guide.json`) — gitignored so each install is local.
"""

from __future__ import annotations

import json
from typing import Any

from agent.config import settings


REQUIRED_FIELDS = ("tone", "vocabulary_level", "values", "dos", "donts",
                   "voice_examples")


def generate(description: str) -> dict[str, Any]:
    """Build a brand guide from a one-line description, persist it, return it."""
    description = (description or "").strip()
    if not description:
        raise ValueError("brand voice description cannot be empty")

    guide = _call_claude_for_brand_guide(description=description)
    for field in REQUIRED_FIELDS:
        if field not in guide:
            raise ValueError(f"brand guide missing required field '{field}'")

    settings.brand_guide_path.parent.mkdir(parents=True, exist_ok=True)
    settings.brand_guide_path.write_text(
        json.dumps(guide, indent=2), encoding="utf-8",
    )
    return guide


def load() -> dict[str, Any] | None:
    """Return the saved brand guide, or None if not yet generated."""
    path = settings.brand_guide_path
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _call_claude_for_brand_guide(*, description: str) -> dict[str, Any]:
    """Boundary: turn a description into a brand guide dict via Claude."""
    from anthropic import Anthropic

    from agent import prompts

    client = Anthropic(api_key=settings.anthropic_api_key)
    response = client.messages.create(
        model=settings.drafting_model,
        max_tokens=1200,
        system=prompts.brand_voice_system_prompt(),
        messages=[{
            "role": "user",
            "content": prompts.brand_voice_user_prompt(description=description),
        }],
    )
    text_blocks = [b.text for b in response.content
                   if getattr(b, "type", None) == "text"]
    if not text_blocks:
        raise ValueError("brand voice call returned no text")
    return _parse_json(text_blocks[0])


def _parse_json(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```", 2)[1].lstrip("json").strip()
        text = text.rsplit("```", 1)[0].strip()
    return json.loads(text)
