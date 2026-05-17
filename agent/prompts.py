"""Centralised LLM prompts. Each function returns a string."""

from __future__ import annotations

import json
from typing import Any


def research_user_prompt(*, topic_title: str, keyword: str, category: str) -> str:
    return f"""You are researching for a DTC skincare brand blog post.

Topic: {topic_title}
Target keyword: {keyword}
Category: {category}

Use the web_search tool to find 3-5 authoritative sources (dermatology sites,
peer-reviewed summaries, established beauty publications). Then return ONLY a
JSON object with this exact shape (no prose, no markdown fences):

{{
  "summary": "<2-3 sentence overview of the topic, grounded in sources>",
  "key_points": ["<point 1>", "<point 2>", "<point 3>", ...],
  "sources": [
    {{"url": "<url>", "title": "<page title>"}},
    ...
  ]
}}

Skip marketing fluff. Prefer claims you can attribute to a source."""


def outline_system_prompt(brand_voice: dict[str, Any]) -> str:
    voice_json = json.dumps(brand_voice, indent=2)
    return f"""You are a senior content strategist for a DTC skincare brand.
You write outlines that are accurate, scannable, and aligned with brand voice.

Brand voice profile:
{voice_json}

Your job is to produce a JSON outline. Return ONLY the JSON object, no prose."""


def outline_user_prompt(*, topic_title: str, keyword: str, research: dict[str, Any],
                       target_words: int) -> str:
    research_json = json.dumps(research, indent=2)
    return f"""Create a blog outline for the topic: "{topic_title}"
Target keyword: {keyword}
Target length: {target_words} words

Research findings:
{research_json}

Return JSON with this shape:
{{
  "h1": "<the article H1, includes the keyword naturally>",
  "h2_sections": [
    {{"heading": "<H2 text>", "key_points": ["<point>", "<point>"]}},
    ...4-6 sections...
  ],
  "cta": "<one sentence call-to-action, on-brand, not pushy>",
  "estimated_words": {target_words},
  "seo_meta": "<160-char meta description with the keyword>"
}}"""


def draft_system_prompt(brand_voice: dict[str, Any]) -> str:
    voice_json = json.dumps(brand_voice, indent=2)
    return f"""You are a senior content writer for a DTC skincare brand.
You write clear, science-backed, scannable articles that match brand voice.

Brand voice profile:
{voice_json}

Rules:
- Write in active voice, second person where appropriate.
- Cite research findings inline (e.g., "Studies show..."). Do not invent stats.
- Use the provided H2 structure verbatim.
- No emojis. No clichés. No filler intro paragraphs.
- Return ONLY the Markdown article (no commentary, no frontmatter)."""


def brand_voice_system_prompt() -> str:
    return """You are a brand-voice strategist for a DTC skincare brand.

Your job: take a one-line description of how the brand should sound and
produce a structured JSON brand guide that other prompts will reference
when drafting and reviewing articles.

Return ONLY JSON, no prose, no markdown fences. Schema:
{
  "tone": "<2-4 adjectives + a short qualifier>",
  "vocabulary_level": "<one of: simple, accessible, technical>",
  "values": ["<value 1>", "<value 2>", "<value 3>"],
  "dos": ["<concrete writing rule>", ...4-6 items],
  "donts": ["<concrete writing rule>", ...4-6 items],
  "voice_examples": ["<one short sample sentence>", ...2-4 items]
}"""


def brand_voice_user_prompt(*, description: str) -> str:
    return f"Description of the desired brand voice:\n\n{description}"


def tone_eval_system_prompt(brand_voice: dict[str, Any]) -> str:
    voice_json = json.dumps(brand_voice, indent=2)
    return f"""You are a brand-voice auditor.

Brand voice profile:
{voice_json}

Score how well a draft matches this brand voice. Return ONLY JSON:
{{"score": <0.0-5.0>, "feedback": "<one specific fix if score < 3.5, else empty>"}}"""


def tone_eval_user_prompt(*, draft: str) -> str:
    return f"Evaluate the tone of this draft:\n\n---\n{draft}\n---"


def hallucination_system_prompt() -> str:
    return """You are a fact-checker. The author wrote a blog article using only
the research findings provided. Identify any factual claims in the article that
are NOT supported by the research.

Be strict about specific numbers, percentages, study results, and named studies.
General domain knowledge (e.g., "skin produces sebum") is fine without a source.

Return ONLY JSON:
{
  "passed": <true if every specific claim is supported, false otherwise>,
  "unsupported_claims": ["<verbatim or paraphrased unsupported claim>", ...]
}"""


def hallucination_user_prompt(*, draft: str, research: dict[str, Any]) -> str:
    research_json = json.dumps(research, indent=2)
    return f"""Research findings (the only acceptable sources):
{research_json}

Article to fact-check:
---
{draft}
---"""


def draft_user_prompt(
    *,
    topic_title: str,
    research: dict[str, Any],
    outline: dict[str, Any],
    target_words: int,
    feedback: str | None,
) -> str:
    research_json = json.dumps(research, indent=2)
    outline_json = json.dumps(outline, indent=2)
    feedback_block = f"\n\nRetry feedback (address this): {feedback}" if feedback else ""
    return f"""Write a {target_words}-word blog article.

Topic: {topic_title}

Outline:
{outline_json}

Research (only cite from these findings; do not fabricate):
{research_json}{feedback_block}

Return Markdown only. Start with the H1 from the outline."""
