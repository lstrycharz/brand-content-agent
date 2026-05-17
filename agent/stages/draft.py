"""Stage 4: expand outline into a full Markdown article body."""

from __future__ import annotations

import re
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
    """Return {body, word_count, slug, title}.

    `body` is the Markdown article only (no YAML frontmatter). The runner
    composes the final file by prepending frontmatter once the hero image
    path is known.
    """
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
    slug = slugify(title)
    bus.emit(run_id, "draft", f"Drafted {word_count} words", level="success")
    return {"body": body, "word_count": word_count, "slug": slug, "title": title}


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


def slugify(title: str) -> str:
    slug = re.sub(r"[^\w\s-]", "", title.lower())
    slug = re.sub(r"[\s_]+", "-", slug).strip("-")
    return slug[:80]
