"""Stage 4: expand outline into a full Markdown article."""

from __future__ import annotations

import json
import re
from datetime import date
from typing import Any

from agent.config import settings
from agent.db import Topic
from agent.progress import bus


def run(
    *,
    topic: Topic,
    research: dict[str, Any],
    outline: dict[str, Any],
    brand_voice: dict[str, Any],
    run_id: str,
    feedback: str | None = None,
) -> dict[str, Any]:
    """Return {markdown, word_count, slug, title}."""
    bus.emit(run_id, "draft",
             "Drafting article..." if feedback is None else f"Retrying with feedback: {feedback}",
             level="info")
    body = _call_claude_for_draft(
        topic=topic, research=research, outline=outline,
        brand_voice=brand_voice, feedback=feedback,
    )
    body = body.strip()
    word_count = len(re.findall(r"\b\w+\b", body))
    title = outline.get("h1", topic.title)
    slug = _slugify(title)
    markdown = _wrap_with_frontmatter(
        body=body,
        title=title,
        slug=slug,
        category=topic.category,
        topic_id=topic.id or 0,
        run_id=run_id,
        word_count=word_count,
        seo_meta=outline.get("seo_meta", ""),
    )
    bus.emit(run_id, "draft", f"Drafted {word_count} words", level="success")
    return {"markdown": markdown, "word_count": word_count, "slug": slug, "title": title}


def _call_claude_for_draft(
    *,
    topic: Topic,
    research: dict[str, Any],
    outline: dict[str, Any],
    brand_voice: dict[str, Any],
    feedback: str | None,
) -> str:
    from anthropic import Anthropic

    from agent import prompts

    client = Anthropic(api_key=settings.anthropic_api_key)
    response = client.messages.create(
        model=settings.drafting_model,
        max_tokens=4000,
        system=prompts.draft_system_prompt(brand_voice),
        messages=[{
            "role": "user",
            "content": prompts.draft_user_prompt(
                topic_title=topic.title,
                research=research,
                outline=outline,
                target_words=settings.target_word_count,
                feedback=feedback,
            ),
        }],
    )
    text_blocks = [b.text for b in response.content if getattr(b, "type", None) == "text"]
    if not text_blocks:
        raise ValueError("Claude returned no text for draft")
    return text_blocks[0]


def _slugify(title: str) -> str:
    slug = re.sub(r"[^\w\s-]", "", title.lower())
    slug = re.sub(r"[\s_]+", "-", slug).strip("-")
    return slug[:80]


def _wrap_with_frontmatter(
    *,
    body: str,
    title: str,
    slug: str,
    category: str,
    topic_id: int,
    run_id: str,
    word_count: int,
    seo_meta: str,
) -> str:
    read_time = max(1, round(word_count / 240))
    today = date.today().isoformat()
    frontmatter = (
        "---\n"
        f"title: {title}\n"
        f"slug: {slug}\n"
        f"date: {today}\n"
        f"category: {category}\n"
        f"topic_id: {topic_id}\n"
        f"run_id: {run_id}\n"
        f"word_count: {word_count}\n"
        f"seo_meta: {json.dumps(seo_meta)}\n"
        f"read_time: {read_time} min\n"
        "---\n\n"
    )
    return frontmatter + body
