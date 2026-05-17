"""Stage 3: generate JSON outline via Claude."""

from __future__ import annotations

import json
from typing import Any

from agent.config import settings
from agent.db import Topic
from agent.progress import bus


REQUIRED_FIELDS = ("h1", "h2_sections", "cta", "seo_meta")


def run(
    *,
    topic: Topic,
    research: dict[str, Any],
    brand_voice: dict[str, Any],
    run_id: str = "",
) -> dict[str, Any]:
    if run_id:
        bus.emit(run_id, "outline", "Generating outline...", level="info")
    outline = _call_claude_for_outline(
        topic=topic, research=research, brand_voice=brand_voice,
    )
    for field in REQUIRED_FIELDS:
        if field not in outline:
            raise ValueError(f"outline missing required field '{field}'")
    if len(outline.get("h2_sections", [])) < 3:
        raise ValueError("outline needs at least 3 H2 sections")
    if run_id:
        bus.emit(run_id, "outline",
                 f"Outline ready ({len(outline['h2_sections'])} sections)", level="success")
    return outline


def _call_claude_for_outline(
    *, topic: Topic, research: dict[str, Any], brand_voice: dict[str, Any],
) -> dict[str, Any]:
    from anthropic import Anthropic

    from agent import prompts

    client = Anthropic(api_key=settings.anthropic_api_key)
    response = client.messages.create(
        model=settings.drafting_model,
        max_tokens=1500,
        system=prompts.outline_system_prompt(brand_voice),
        messages=[{
            "role": "user",
            "content": prompts.outline_user_prompt(
                topic_title=topic.title,
                keyword=topic.keyword,
                research=research,
                target_words=settings.target_word_count,
            ),
        }],
    )
    text_blocks = [b.text for b in response.content if getattr(b, "type", None) == "text"]
    if not text_blocks:
        raise ValueError("Claude returned no text for outline")
    return _parse_json(text_blocks[0])


def _parse_json(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```", 2)[1].lstrip("json").strip()
        text = text.rsplit("```", 1)[0].strip()
    return json.loads(text)
