"""Orchestrates the agent's stages for a single run.

Currently wires Stages 1-6 (Init → Research → Outline → Draft → Quality →
Image), with auto-retry inside the Draft/Quality loop. The final Markdown is
written to disk by `_write_draft_file` (a minimal Stage 7 stub — full RUN_LOG
generation arrives in a later chunk).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from sqlmodel import select

from agent import brand_voice, run_log
from agent.config import settings
from agent.db import Run, Topic, session_scope, utcnow
from agent.progress import bus
from agent.stages import draft, image, init, outline, quality, research


class QualityRetryExhausted(RuntimeError):
    """Raised when the draft fails quality checks even after a retry."""


MAX_DRAFT_ATTEMPTS = 2  # initial + 1 retry


DEFAULT_BRAND_VOICE: dict[str, Any] = {
    "vertical": "consumer",
    "target_audience": "informed readers seeking practical, evidence-backed guidance",
    "tone": "clear, helpful, evidence-backed",
    "vocabulary_level": "accessible (avoid jargon, explain terms inline)",
    "values": ["transparency", "evidence-first", "no over-promising"],
    "dos": [
        "cite research findings",
        "use active voice and second person",
        "explain mechanisms simply",
    ],
    "donts": [
        "no emojis",
        "no clickbait",
        "no fabricated stats",
        "no aggressive selling",
    ],
    "voice_examples": [
        "Here's what the evidence actually shows.",
        "Skip the marketing — these are the steps that move the needle.",
    ],
}


def run_once(
    topic_id: int | None = None, run_id: str | None = None,
) -> dict[str, Any]:
    """Run the agent end-to-end for one topic. Returns summary dict.

    `run_id` may be provided by the UI so it can subscribe to the progress
    bus before this function (and the agent thread) actually start.
    """
    settings.ensure_dirs()
    topic, run_id = init.run(topic_id=topic_id, run_id=run_id)

    try:
        brand_voice = _load_brand_voice()

        _mark_stage(run_id, "research")
        findings = research.run(topic=topic, run_id=run_id, brand_voice=brand_voice)

        _mark_stage(run_id, "outline")
        outline_result = outline.run(
            topic=topic, research=findings,
            brand_voice=brand_voice, run_id=run_id,
        )

        draft_result, report, retry_count = _draft_with_retry(
            topic=topic, research=findings, outline_result=outline_result,
            brand_voice=brand_voice, run_id=run_id,
        )

        if not report.passed:
            _mark_topic_failed_review(topic.id)
            _finish_run(run_id, status="failed",
                        error_message=f"quality failed: {report.feedback}")
            bus.emit(run_id, "error",
                     "Quality checks failed after retry — topic queued for review.",
                     level="error")
            _safe_regenerate_run_log()
            raise QualityRetryExhausted(report.feedback or "quality check failed")

        date_str = utcnow().date().isoformat()
        _mark_stage(run_id, "image")
        image_path = image.run(
            topic=topic, slug=draft_result["slug"],
            date_str=date_str, run_id=run_id, brand_voice=brand_voice,
        )

        _mark_stage(run_id, "persist")
        output_path = _write_draft_file(
            slug=draft_result["slug"], body=draft_result["body"],
            title=draft_result["title"], topic=topic, run_id=run_id,
            word_count=draft_result["word_count"],
            seo_meta=outline_result.get("seo_meta", ""),
            image_path=image_path, date_str=date_str,
            tone_score=report.tone_score, seo_score=report.seo_score,
        )
        _finish_run(run_id, status="success", output_file=str(output_path),
                    image_file=str(image_path))
        _mark_topic_processed(topic.id)
        _safe_regenerate_run_log()
        bus.emit(run_id, "done", f"Draft written to {output_path}", level="success")

        return {
            "run_id": run_id,
            "topic_title": topic.title,
            "word_count": draft_result["word_count"],
            "output_file": str(output_path),
            "image_file": str(image_path),
            "tone_score": report.tone_score,
            "seo_score": report.seo_score,
            "retry_count": retry_count,
            "status": "success",
        }
    except QualityRetryExhausted:
        raise
    except Exception as exc:
        _finish_run(run_id, status="failed", error_message=str(exc))
        _safe_regenerate_run_log()
        bus.emit(run_id, "error", f"Run failed: {exc}", level="error")
        raise


def _draft_with_retry(
    *,
    topic: Topic,
    research: dict,
    outline_result: dict,
    brand_voice: dict,
    run_id: str,
) -> tuple[dict, quality.QualityReport, int]:
    """Draft → quality, retry once with feedback on failure.

    Returns (draft_result, last_quality_report, retry_count). If the second
    attempt also fails, the caller decides whether to raise.
    """
    feedback: str | None = None
    draft_result: dict = {}
    report: quality.QualityReport | None = None

    for attempt in range(1, MAX_DRAFT_ATTEMPTS + 1):
        _mark_stage(run_id, "draft" if attempt == 1 else "draft_retry")
        draft_result = draft.run(
            topic=topic, research=research, outline=outline_result,
            brand_voice=brand_voice, run_id=run_id, feedback=feedback,
        )
        _mark_stage(run_id, "quality")
        report = quality.run(
            draft_markdown=draft_result["body"], topic=topic,
            research=research, outline=outline_result,
            brand_voice=brand_voice, run_id=run_id,
        )
        if report.passed:
            return draft_result, report, attempt - 1
        feedback = report.feedback

    assert report is not None
    return draft_result, report, MAX_DRAFT_ATTEMPTS - 1


def _load_brand_voice() -> dict[str, Any]:
    return brand_voice.load() or DEFAULT_BRAND_VOICE


def _write_draft_file(
    *,
    slug: str,
    body: str,
    title: str,
    topic: Topic,
    run_id: str,
    word_count: int,
    seo_meta: str,
    image_path: Path,
    date_str: str,
    tone_score: float,
    seo_score: float,
) -> Path:
    settings.drafts_dir.mkdir(parents=True, exist_ok=True)
    output_path = settings.drafts_dir / f"{date_str}-{slug}.md"
    frontmatter = _build_frontmatter(
        title=title, slug=slug, date_str=date_str, category=topic.category,
        topic_id=topic.id or 0, run_id=run_id, word_count=word_count,
        seo_meta=seo_meta, hero_image=image_path.name,
        tone_score=tone_score, seo_score=seo_score,
    )
    output_path.write_text(frontmatter + body, encoding="utf-8")
    return output_path


def _build_frontmatter(
    *,
    title: str,
    slug: str,
    date_str: str,
    category: str,
    topic_id: int,
    run_id: str,
    word_count: int,
    seo_meta: str,
    hero_image: str,
    tone_score: float,
    seo_score: float,
) -> str:
    read_time = max(1, round(word_count / 240))
    return (
        "---\n"
        f"title: {title}\n"
        f"slug: {slug}\n"
        f"date: {date_str}\n"
        f"category: {category}\n"
        f"topic_id: {topic_id}\n"
        f"run_id: {run_id}\n"
        f"word_count: {word_count}\n"
        f"tone_score: {tone_score:.2f}\n"
        f"seo_score: {seo_score:.2f}\n"
        f"seo_meta: {json.dumps(seo_meta)}\n"
        f"hero_image: ./{hero_image}\n"
        f"read_time: {read_time} min\n"
        "---\n\n"
    )


def _mark_stage(run_id: str, stage: str) -> None:
    with session_scope() as session:
        row = session.exec(select(Run).where(Run.run_id == run_id)).one()
        row.current_stage = stage
        session.add(row)


def _finish_run(
    run_id: str, *, status: str,
    output_file: str | None = None,
    image_file: str | None = None,
    error_message: str | None = None,
) -> None:
    with session_scope() as session:
        row = session.exec(select(Run).where(Run.run_id == run_id)).one()
        row.status = status
        row.completed_at = utcnow()
        if output_file is not None:
            row.output_file = output_file
        if image_file is not None:
            row.image_file = image_file
        if error_message is not None:
            row.error_message = error_message
        session.add(row)


def _mark_topic_processed(topic_id: int | None) -> None:
    _set_topic_status(topic_id, "processed")


def _mark_topic_failed_review(topic_id: int | None) -> None:
    _set_topic_status(topic_id, "failed_review_needed")


def _safe_regenerate_run_log() -> None:
    """Best-effort RUN_LOG.md regeneration; never let a log failure mask the
    original exception or success path."""
    try:
        run_log.regenerate()
    except Exception:  # noqa: BLE001 — log writing is not load-bearing
        pass


def _set_topic_status(topic_id: int | None, status: str) -> None:
    if topic_id is None:
        return
    with session_scope() as session:
        topic = session.get(Topic, topic_id)
        if topic is not None:
            topic.status = status
            topic.updated_at = utcnow()
            session.add(topic)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the BrandContent agent once.")
    parser.add_argument("--topic-id", type=int, default=None,
                        help="Specific topic id (default: highest-priority pending)")
    args = parser.parse_args(argv)

    try:
        summary = run_once(topic_id=args.topic_id)
    except LookupError as exc:
        print(f"[error] {exc}", file=sys.stderr)
        return 2
    except QualityRetryExhausted as exc:
        print(f"[failed_review_needed] quality retry exhausted: {exc}", file=sys.stderr)
        return 3
    except Exception as exc:
        print(f"[error] Run failed: {exc}", file=sys.stderr)
        return 1

    print(f"[done] {summary['topic_title']}")
    print(f"       run_id     {summary['run_id']}")
    print(f"       words      {summary['word_count']}")
    print(f"       tone       {summary['tone_score']:.2f}/5")
    print(f"       seo        {summary['seo_score']:.2f}/5")
    print(f"       retries    {summary['retry_count']}")
    print(f"       draft      {summary['output_file']}")
    print(f"       image      {summary['image_file']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
