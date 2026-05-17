"""Orchestrates the agent's stages for a single run.

Chunk 1 wires Stages 1-4 (Init → Research → Outline → Draft) and writes the
draft to disk. Stages 5-7 (Quality, Image, Persist) land in later chunks.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from sqlmodel import select

from agent.config import settings
from agent.db import Run, Topic, session_scope, utcnow
from agent.progress import bus
from agent.stages import draft, init, outline, quality, research


class QualityRetryExhausted(RuntimeError):
    """Raised when the draft fails quality checks even after a retry."""


MAX_DRAFT_ATTEMPTS = 2  # initial + 1 retry


DEFAULT_BRAND_VOICE: dict[str, Any] = {
    "tone": "science-backed, no-nonsense, educational",
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
}


def run_once(topic_id: int | None = None) -> dict[str, Any]:
    """Run the agent end-to-end for one topic. Returns summary dict."""
    settings.ensure_dirs()
    topic, run_id = init.run(topic_id=topic_id)

    try:
        _mark_stage(run_id, "research")
        findings = research.run(topic=topic, run_id=run_id)

        _mark_stage(run_id, "outline")
        brand_voice = _load_brand_voice()
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
            raise QualityRetryExhausted(report.feedback or "quality check failed")

        output_path = _write_draft(
            slug=draft_result["slug"], markdown=draft_result["markdown"],
        )
        _finish_run(run_id, status="success", output_file=str(output_path))
        _mark_topic_processed(topic.id)
        bus.emit(run_id, "done", f"Draft written to {output_path}", level="success")

        return {
            "run_id": run_id,
            "topic_title": topic.title,
            "word_count": draft_result["word_count"],
            "output_file": str(output_path),
            "tone_score": report.tone_score,
            "seo_score": report.seo_score,
            "retry_count": retry_count,
            "status": "success",
        }
    except QualityRetryExhausted:
        raise
    except Exception as exc:
        _finish_run(run_id, status="failed", error_message=str(exc))
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
            draft_markdown=draft_result["markdown"], topic=topic,
            research=research, outline=outline_result,
            brand_voice=brand_voice, run_id=run_id,
        )
        if report.passed:
            return draft_result, report, attempt - 1
        feedback = report.feedback

    assert report is not None
    return draft_result, report, MAX_DRAFT_ATTEMPTS - 1


def _load_brand_voice() -> dict[str, Any]:
    path = settings.brand_guide_path
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return DEFAULT_BRAND_VOICE


def _write_draft(*, slug: str, markdown: str) -> Path:
    settings.drafts_dir.mkdir(parents=True, exist_ok=True)
    today = utcnow().date().isoformat()
    path = settings.drafts_dir / f"{today}-{slug}.md"
    path.write_text(markdown, encoding="utf-8")
    return path


def _mark_stage(run_id: str, stage: str) -> None:
    with session_scope() as session:
        row = session.exec(select(Run).where(Run.run_id == run_id)).one()
        row.current_stage = stage
        session.add(row)


def _finish_run(
    run_id: str, *, status: str,
    output_file: str | None = None, error_message: str | None = None,
) -> None:
    with session_scope() as session:
        row = session.exec(select(Run).where(Run.run_id == run_id)).one()
        row.status = status
        row.completed_at = utcnow()
        if output_file is not None:
            row.output_file = output_file
        if error_message is not None:
            row.error_message = error_message
        session.add(row)


def _mark_topic_processed(topic_id: int | None) -> None:
    _set_topic_status(topic_id, "processed")


def _mark_topic_failed_review(topic_id: int | None) -> None:
    _set_topic_status(topic_id, "failed_review_needed")


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
    except Exception as exc:
        print(f"[error] Run failed: {exc}", file=sys.stderr)
        return 1

    print(f"[done] {summary['topic_title']}")
    print(f"       run_id     {summary['run_id']}")
    print(f"       words      {summary['word_count']}")
    print(f"       output     {summary['output_file']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
