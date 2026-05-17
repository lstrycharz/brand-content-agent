"""Stage 2: web research via Claude's web_search tool, with cache."""

from __future__ import annotations

import json
from datetime import timedelta
from typing import Any

from sqlmodel import select

from agent.config import settings
from agent.db import ResearchCache, Topic, session_scope, utcnow
from agent.progress import bus


def run(*, topic: Topic, run_id: str) -> dict[str, Any]:
    """Return research findings for a topic, using cache if fresh."""
    cached = _load_from_cache(topic.title)
    if cached is not None:
        bus.emit(run_id, "research", f"Cache hit for '{topic.title}'", level="info")
        return cached

    bus.emit(run_id, "research", f"Searching the web for '{topic.keyword}'...", level="info")
    findings = _call_claude_with_search(topic=topic)
    _save_to_cache(topic.title, findings)
    bus.emit(run_id, "research",
             f"Got {len(findings.get('key_points', []))} key points, "
             f"{len(findings.get('sources', []))} sources", level="info")
    return findings


def _load_from_cache(topic_title: str) -> dict[str, Any] | None:
    with session_scope() as session:
        row = session.exec(
            select(ResearchCache).where(ResearchCache.topic_title == topic_title)
        ).first()
        if row is None:
            return None
        if row.expires_at < utcnow():
            session.delete(row)
            return None
        return json.loads(row.search_results)


def _save_to_cache(topic_title: str, findings: dict[str, Any]) -> None:
    expires = utcnow() + timedelta(days=settings.research_cache_days)
    with session_scope() as session:
        existing = session.exec(
            select(ResearchCache).where(ResearchCache.topic_title == topic_title)
        ).first()
        if existing:
            existing.search_results = json.dumps(findings)
            existing.cached_at = utcnow()
            existing.expires_at = expires
            session.add(existing)
        else:
            session.add(ResearchCache(
                topic_title=topic_title,
                search_results=json.dumps(findings),
                cached_at=utcnow(),
                expires_at=expires,
            ))


def _call_claude_with_search(*, topic: Topic) -> dict[str, Any]:
    """Boundary: call Claude with web_search tool and return parsed JSON findings.

    Mocked in tests. Live path uses Claude's server-side web_search tool.
    """
    from anthropic import Anthropic

    from agent import prompts

    client = Anthropic(api_key=settings.anthropic_api_key)
    response = client.messages.create(
        model=settings.drafting_model,
        max_tokens=2000,
        tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 5}],
        messages=[{
            "role": "user",
            "content": prompts.research_user_prompt(
                topic_title=topic.title,
                keyword=topic.keyword,
                category=topic.category,
            ),
        }],
    )
    text_blocks = [b.text for b in response.content if getattr(b, "type", None) == "text"]
    if not text_blocks:
        raise ValueError("Claude returned no text after web search")
    return _parse_research_json(text_blocks[-1])


def _parse_research_json(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```", 2)[1].lstrip("json").strip()
        text = text.rsplit("```", 1)[0].strip()
    data = json.loads(text)
    for required in ("summary", "key_points", "sources"):
        if required not in data:
            raise ValueError(f"research response missing '{required}'")
    return data
