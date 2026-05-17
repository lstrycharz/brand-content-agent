"""Stage 5: validate the draft and produce actionable retry feedback."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from agent.config import settings
from agent.db import Topic
from agent.progress import bus


@dataclass
class QualityReport:
    passed: bool
    word_count: int
    seo_score: float  # 0-5
    tone_score: float  # 0-5
    hallucination_check_passed: bool
    failures: list[str] = field(default_factory=list)
    feedback: str | None = None


def run(
    *,
    draft_markdown: str,
    topic: Topic,
    research: dict[str, Any],
    outline: dict[str, Any],
    brand_voice: dict[str, Any],
    run_id: str,
) -> QualityReport:
    """Validate the draft and return a structured QualityReport."""
    bus.emit(run_id, "quality", "Validating draft...", level="info")
    body = _strip_frontmatter(draft_markdown)

    failures: list[str] = []
    feedback_parts: list[str] = []

    word_count = _count_words(body)
    if word_count < settings.word_count_min:
        failures.append("word_count_too_low")
        feedback_parts.append(
            f"Expand sections to reach ~{settings.target_word_count} words "
            f"(current: {word_count})."
        )
    elif word_count > settings.word_count_max:
        failures.append("word_count_too_high")
        feedback_parts.append(
            f"Tighten the article to ~{settings.target_word_count} words "
            f"(current: {word_count})."
        )

    seo_score, seo_failures, seo_feedback = _check_seo(
        body=body, keyword=topic.keyword,
    )
    failures.extend(seo_failures)
    feedback_parts.extend(seo_feedback)

    tone_result = _call_claude_for_tone_eval(
        draft=body, brand_voice=brand_voice,
    )
    tone_score = float(tone_result.get("score", 0.0))
    if tone_score < settings.tone_score_threshold:
        failures.append("tone_below_threshold")
        tone_fb = tone_result.get("feedback") or "make tone more on-brand"
        feedback_parts.append(f"Tone scored {tone_score}/5: {tone_fb}.")

    halluc_result = _call_claude_for_hallucination_check(
        draft=body, research=research,
    )
    halluc_passed = bool(halluc_result.get("passed", True))
    if not halluc_passed:
        failures.append("hallucination_detected")
        bad_claims = halluc_result.get("unsupported_claims", [])
        feedback_parts.append(
            "Remove or rephrase these unsupported claims: "
            + "; ".join(bad_claims)
        )

    passed = not failures
    feedback = " ".join(feedback_parts) if feedback_parts else None
    report = QualityReport(
        passed=passed,
        word_count=word_count,
        seo_score=seo_score,
        tone_score=tone_score,
        hallucination_check_passed=halluc_passed,
        failures=failures,
        feedback=feedback,
    )
    level = "success" if passed else "warning"
    bus.emit(run_id, "quality",
             "Passed all checks" if passed else f"Failed: {', '.join(failures)}",
             level=level)
    return report


# ---------------------------------------------------------------------------
# pure validators (no LLM)
# ---------------------------------------------------------------------------


def _strip_frontmatter(markdown: str) -> str:
    if not markdown.startswith("---\n"):
        return markdown
    end = markdown.find("\n---\n", 4)
    if end == -1:
        return markdown
    return markdown[end + len("\n---\n"):].lstrip("\n")


def _count_words(text: str) -> int:
    return len(re.findall(r"\b\w+\b", text))


def _check_seo(*, body: str, keyword: str) -> tuple[float, list[str], list[str]]:
    """Return (score 0-5, failures, feedback)."""
    failures: list[str] = []
    feedback: list[str] = []
    score = 5.0

    h1_match = re.search(r"^#\s+(.+)$", body, re.MULTILINE)
    h1_text = h1_match.group(1).lower() if h1_match else ""
    keyword_lower = keyword.lower()

    if keyword_lower not in h1_text:
        failures.append("keyword_missing_from_h1")
        feedback.append(f"Include the keyword '{keyword}' in the H1.")
        score -= 1.5

    # first 100 words
    first_100 = " ".join(re.findall(r"\b\w+\b", body)[:100]).lower()
    if keyword_lower not in first_100:
        failures.append("keyword_missing_from_intro")
        feedback.append(
            f"Mention the keyword '{keyword}' within the first 100 words."
        )
        score -= 1.0

    # at least 2 H2 sections that include the keyword OR ≥3 H2s overall
    h2_matches = re.findall(r"^##\s+(.+)$", body, re.MULTILINE)
    if len(h2_matches) < 3:
        failures.append("too_few_h2_sections")
        feedback.append("Use at least 3 H2 sections to improve scannability.")
        score -= 1.0

    return max(0.0, score), failures, feedback


# ---------------------------------------------------------------------------
# LLM-backed evaluators (mock points)
# ---------------------------------------------------------------------------


def _call_claude_for_tone_eval(
    *, draft: str, brand_voice: dict[str, Any],
) -> dict[str, Any]:
    """Score the draft's tone vs the brand voice. Returns {score, feedback}."""
    from anthropic import Anthropic

    from agent import prompts

    client = Anthropic(api_key=settings.anthropic_api_key)
    response = client.messages.create(
        model=settings.drafting_model,
        max_tokens=400,
        system=prompts.tone_eval_system_prompt(brand_voice),
        messages=[{"role": "user",
                   "content": prompts.tone_eval_user_prompt(draft=draft)}],
    )
    text_blocks = [b.text for b in response.content
                   if getattr(b, "type", None) == "text"]
    if not text_blocks:
        raise ValueError("tone eval returned no text")
    return _parse_json(text_blocks[0])


def _call_claude_for_hallucination_check(
    *, draft: str, research: dict[str, Any],
) -> dict[str, Any]:
    """Check claims in draft against research sources. Returns {passed, unsupported_claims}."""
    from anthropic import Anthropic

    from agent import prompts

    client = Anthropic(api_key=settings.anthropic_api_key)
    response = client.messages.create(
        model=settings.drafting_model,
        max_tokens=600,
        system=prompts.hallucination_system_prompt(),
        messages=[{"role": "user",
                   "content": prompts.hallucination_user_prompt(
                       draft=draft, research=research)}],
    )
    text_blocks = [b.text for b in response.content
                   if getattr(b, "type", None) == "text"]
    if not text_blocks:
        raise ValueError("hallucination check returned no text")
    return _parse_json(text_blocks[0])


def _parse_json(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```", 2)[1].lstrip("json").strip()
        text = text.rsplit("```", 1)[0].strip()
    return json.loads(text)
