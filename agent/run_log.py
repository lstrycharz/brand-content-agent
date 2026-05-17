"""Generate RUN_LOG.md from the runs table.

Single source of truth: every value in RUN_LOG.md is read from SQLite, so
deleting or hand-editing the file is harmless — the next agent run regenerates
it. This is called from the runner at the end of every run, success or fail.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from sqlmodel import select

from agent.config import settings
from agent.db import Draft, Run, Topic, session_scope


STATUS_ICON = {
    "success": "✅",
    "in_progress": "⏳",
    "failed": "❌",
}


def regenerate() -> Path:
    """Read every run from SQLite, write RUN_LOG.md, return its path."""
    with session_scope() as s:
        runs = s.exec(select(Run)).all()
        topics = s.exec(select(Topic)).all()
        topics_by_id = {t.id: {"title": t.title, "category": t.category} for t in topics}
        drafts_by_run_id = {
            d.run_id: {"word_count": d.word_count,
                       "tone_score": d.tone_score, "seo_score": d.seo_score}
            for d in s.exec(select(Draft)).all()
        }
        # Detach plain dicts so we can format outside the session
        run_views = [{
            "run_id": r.run_id,
            "topic_id": r.topic_id,
            "status": r.status,
            "started_at": r.started_at,
            "completed_at": r.completed_at,
            "error_message": r.error_message,
            "output_file": r.output_file,
            "image_file": r.image_file,
        } for r in runs]

    body = _format_run_log(
        runs=run_views, topics_by_id=topics_by_id, drafts_by_run_id=drafts_by_run_id,
    )
    settings.run_log_path.parent.mkdir(parents=True, exist_ok=True)
    settings.run_log_path.write_text(body, encoding="utf-8")
    return settings.run_log_path


def _format_run_log(
    *,
    runs: list[dict],
    topics_by_id: dict[int, dict],
    drafts_by_run_id: dict[str, dict] | None = None,
) -> str:
    drafts_by_run_id = drafts_by_run_id or {}
    header = (
        "# Run Log\n\n"
        "_Generated automatically by the BrandContent agent. "
        "Do not edit by hand — it gets overwritten on every run._\n\n"
    )

    if not runs:
        return header + "No runs yet.\n"

    # Sort by completion (fall back to start time so in-progress rows still sort)
    sorted_runs = sorted(
        runs,
        key=lambda r: r["completed_at"] or r["started_at"] or datetime.min,
        reverse=True,
    )
    latest = sorted_runs[0]

    return header + _latest_section(latest, topics_by_id, drafts_by_run_id) \
        + _runs_table(sorted_runs, topics_by_id, drafts_by_run_id)


def _latest_section(run: dict, topics: dict, drafts: dict) -> str:
    icon = STATUS_ICON.get(run["status"], "·")
    topic = topics.get(run["topic_id"], {})
    title = topic.get("title", "(unknown topic)")
    draft = drafts.get(run["run_id"], {})
    ts = _fmt_dt(run["completed_at"] or run["started_at"])

    lines = [
        "## Latest run\n",
        f"- **When:** {ts}",
        f"- **Topic:** {title}",
        f"- **Status:** {icon} {run['status']}",
        f"- **Run ID:** `{run['run_id']}`",
    ]
    if run["status"] == "success":
        lines.append(f"- **Word count:** {draft.get('word_count', '—')}")
        lines.append(f"- **Tone score:** {draft.get('tone_score', '—')} / 5")
        lines.append(f"- **SEO score:** {draft.get('seo_score', '—')} / 5")
        if run.get("output_file"):
            lines.append(f"- **Draft:** `{run['output_file']}`")
        if run.get("image_file"):
            lines.append(f"- **Hero image:** `{run['image_file']}`")
    elif run["status"] == "failed":
        if run.get("error_message"):
            lines.append(f"- **Error:** {run['error_message']}")
    lines.append("")
    return "\n".join(lines) + "\n"


def _runs_table(runs: list[dict], topics: dict, drafts: dict) -> str:
    lines = [
        "## All runs\n",
        "| Date | Topic | Status | Words | Output |",
        "|------|-------|--------|-------|--------|",
    ]
    for r in runs:
        topic_title = topics.get(r["topic_id"], {}).get("title", "(unknown)")
        # truncate long titles for the table
        if len(topic_title) > 50:
            topic_title = topic_title[:47] + "…"
        date = _fmt_date(r["completed_at"] or r["started_at"])
        icon = STATUS_ICON.get(r["status"], "·")
        status = f"{icon} {r['status']}"
        word_count = drafts.get(r["run_id"], {}).get("word_count", "—")
        output = r.get("output_file") or "—"
        if output != "—":
            output = f"`{Path(output).name}`"
        lines.append(f"| {date} | {topic_title} | {status} | {word_count} | {output} |")
    return "\n".join(lines) + "\n"


def _fmt_dt(dt: datetime | None) -> str:
    return dt.strftime("%Y-%m-%d %H:%M UTC") if dt else "—"


def _fmt_date(dt: datetime | None) -> str:
    return dt.strftime("%Y-%m-%d") if dt else "—"
