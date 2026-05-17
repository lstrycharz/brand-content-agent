"""Streamlit UI for the BrandContent agent.

Three tabs:
- 📋 Topics — inline CRUD over the topics backlog
- 🚀 Generate — pick next topic + trigger the agent + live progress
- 📰 Drafts — gallery of generated articles with hero images

Run with: `streamlit run app.py`
"""

from __future__ import annotations

import queue as _queue
import re
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st
from sqlmodel import select

from agent import runner
from agent.db import Run, Topic, session_scope, utcnow
from agent.progress import ProgressEvent, bus


st.set_page_config(page_title="BrandContent", page_icon="📝", layout="wide")

TOPIC_STATUSES = ("pending", "processed", "failed_review_needed", "skipped")
DIFFICULTIES = ("beginner", "intermediate", "advanced")


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

with st.sidebar:
    st.title("📝 BrandContent")
    st.caption("DTC skincare content agent")
    st.divider()
    with session_scope() as s:
        counts = {
            status: len(s.exec(
                select(Topic).where(Topic.status == status)
            ).all())
            for status in TOPIC_STATUSES
        }
        successful_runs_count = len(s.exec(
            select(Run).where(Run.status == "success")
        ).all())
    st.metric("Pending topics", counts["pending"])
    st.metric("Processed", counts["processed"])
    if counts["failed_review_needed"]:
        st.metric("Need review", counts["failed_review_needed"],
                  delta=f"-{counts['failed_review_needed']}",
                  delta_color="inverse")
    st.metric("Drafts generated", successful_runs_count)


# ---------------------------------------------------------------------------
# Tabs
# ---------------------------------------------------------------------------

tab_topics, tab_generate, tab_drafts = st.tabs(
    ["📋 Topics", "🚀 Generate", "📰 Drafts"]
)


# ---------------------------------------------------------------------------
# Topics tab — inline CRUD via st.data_editor
# ---------------------------------------------------------------------------

def _load_topics_df() -> pd.DataFrame:
    with session_scope() as s:
        topics = s.exec(
            select(Topic).order_by(Topic.priority.desc(), Topic.created_at.asc())
        ).all()
        # Materialise inside the session so attributes don't lazy-load
        # after the session has closed (DetachedInstanceError).
        rows = [{
            "id": t.id, "title": t.title, "keyword": t.keyword,
            "category": t.category, "difficulty": t.difficulty,
            "priority": t.priority, "status": t.status,
        } for t in topics]
    if not rows:
        return pd.DataFrame(columns=[
            "id", "title", "keyword", "category", "difficulty", "priority", "status",
        ])
    return pd.DataFrame(rows)


def _persist_topic_edits(original: pd.DataFrame, edited: pd.DataFrame,
                          editor_state: dict) -> tuple[int, int, int]:
    """Apply edited_rows/added_rows/deleted_rows. Returns (added, updated, deleted)."""
    added = updated = deleted = 0

    with session_scope() as s:
        # additions — new rows lack a saved id
        for row_idx in editor_state.get("added_rows", []):
            if isinstance(row_idx, dict):
                row_data = row_idx
            else:
                # newer Streamlit: added_rows is list of dicts already
                continue
            if not row_data.get("title"):
                continue
            topic = Topic(
                title=row_data["title"],
                keyword=row_data.get("keyword", ""),
                category=row_data.get("category", "general"),
                difficulty=row_data.get("difficulty", "intermediate"),
                priority=int(row_data.get("priority", 5)),
                status=row_data.get("status", "pending"),
            )
            s.add(topic)
            added += 1

        # edits
        for row_idx, changes in editor_state.get("edited_rows", {}).items():
            tid = int(original.iloc[int(row_idx)]["id"])
            topic = s.get(Topic, tid)
            if topic is None:
                continue
            for col, value in changes.items():
                if col == "id":
                    continue
                setattr(topic, col, value)
            topic.updated_at = utcnow()
            s.add(topic)
            updated += 1

        # deletions
        for row_idx in editor_state.get("deleted_rows", []):
            tid = int(original.iloc[int(row_idx)]["id"])
            topic = s.get(Topic, tid)
            if topic is not None:
                s.delete(topic)
                deleted += 1

    return added, updated, deleted


def _seed_from_csv() -> int:
    """Import data/seed_topics.csv into the topics table. Returns rows added."""
    from agent.config import settings as _cfg

    path = _cfg.seed_topics_path
    if not path.exists():
        return 0
    seed_df = pd.read_csv(path)
    added = 0
    with session_scope() as s:
        for _, row in seed_df.iterrows():
            existing = s.exec(
                select(Topic).where(Topic.title == row["title"])
            ).first()
            if existing:
                continue
            s.add(Topic(
                title=str(row["title"]),
                keyword=str(row["keyword"]),
                category=str(row["category"]),
                difficulty=str(row.get("difficulty", "intermediate")),
                priority=int(row.get("priority", 5)),
            ))
            added += 1
    return added


def render_topics_tab() -> None:
    st.subheader("Topics backlog")
    st.caption(
        "Edit cells inline, add a new row at the bottom, or check rows to delete. "
        "Press Save to persist. The agent picks the highest-priority `pending` topic."
    )

    df = _load_topics_df()

    if df.empty:
        st.info("No topics yet. Click below to import a starter set, or add rows manually.")
        if st.button("📥 Seed starter topics from CSV", type="primary"):
            added = _seed_from_csv()
            st.success(f"Imported {added} topics from data/seed_topics.csv")
            st.rerun()

    edited_df = st.data_editor(
        df,
        num_rows="dynamic",
        column_config={
            "id": st.column_config.NumberColumn("ID", disabled=True, width="small"),
            "title": st.column_config.TextColumn("Title", required=True, width="large"),
            "keyword": st.column_config.TextColumn("SEO keyword", required=True),
            "category": st.column_config.TextColumn("Category"),
            "difficulty": st.column_config.SelectboxColumn(
                "Difficulty", options=list(DIFFICULTIES),
            ),
            "priority": st.column_config.NumberColumn(
                "Priority", min_value=1, max_value=10, step=1,
            ),
            "status": st.column_config.SelectboxColumn(
                "Status", options=list(TOPIC_STATUSES),
            ),
        },
        hide_index=True,
        key="topics_editor",
    )

    save, _, reset_failed = st.columns([1, 2, 1])
    if save.button("💾 Save changes", type="primary", use_container_width=True):
        state = st.session_state.get("topics_editor", {})
        added, updated, deleted = _persist_topic_edits(df, edited_df, state)
        if added or updated or deleted:
            st.success(
                f"Saved: +{added} added, ~{updated} updated, -{deleted} deleted"
            )
            st.rerun()
        else:
            st.info("No changes to save.")

    if reset_failed.button("↩ Reset failed → pending", use_container_width=True):
        with session_scope() as s:
            failed = s.exec(
                select(Topic).where(Topic.status == "failed_review_needed")
            ).all()
            for t in failed:
                t.status = "pending"
                t.updated_at = utcnow()
                s.add(t)
        st.success(f"Reset {len(failed)} topics to pending")
        st.rerun()


# ---------------------------------------------------------------------------
# Generate tab — trigger agent + live progress
# ---------------------------------------------------------------------------

def _next_pending_topic() -> Topic | None:
    with session_scope() as s:
        topic = s.exec(
            select(Topic)
            .where(Topic.status == "pending")
            .order_by(Topic.priority.desc(), Topic.created_at.asc())
        ).first()
        if topic is not None:
            s.expunge(topic)
        return topic


def _run_agent_thread(run_id: str, topic_id: int,
                       result_holder: dict[str, Any]) -> None:
    try:
        result_holder["summary"] = runner.run_once(
            topic_id=topic_id, run_id=run_id,
        )
    except Exception as exc:  # noqa: BLE001 — propagate to UI via holder
        result_holder["error"] = f"{type(exc).__name__}: {exc}"


def _drain_progress(
    evt_queue: _queue.Queue[ProgressEvent],
    thread: threading.Thread,
    placeholder: Any,
    log: list[str],
) -> None:
    """Block until the thread is done; render events as they arrive."""
    while thread.is_alive() or not evt_queue.empty():
        try:
            event = evt_queue.get(timeout=0.3)
        except _queue.Empty:
            continue
        icon = {"info": "·", "success": "✓", "warning": "⚠", "error": "✗"}.get(
            event.level, "·"
        )
        log.append(f"{icon} **[{event.stage}]** {event.message}")
        placeholder.markdown("\n\n".join(log))
    thread.join()


def render_generate_tab() -> None:
    st.subheader("Generate next article")

    topic = _next_pending_topic()
    if topic is None:
        st.info(
            "No pending topics. Add some in the **📋 Topics** tab "
            "(or reset failed ones back to pending)."
        )
        return

    cols = st.columns([3, 1])
    with cols[0]:
        st.markdown(f"### {topic.title}")
        st.caption(
            f"**Keyword:** `{topic.keyword}` · "
            f"**Category:** {topic.category} · "
            f"**Difficulty:** {topic.difficulty} · "
            f"**Priority:** {topic.priority}"
        )
    with cols[1]:
        clicked = st.button(
            "🚀 Generate article", type="primary", use_container_width=True,
        )

    if not clicked:
        return

    run_id = str(uuid.uuid4())
    evt_queue = bus.subscribe(run_id)
    result_holder: dict[str, Any] = {}
    thread = threading.Thread(
        target=_run_agent_thread,
        args=(run_id, topic.id, result_holder),
        daemon=True,
    )
    log: list[str] = []

    try:
        with st.status(
            f"Running agent on '{topic.title}'...", expanded=True,
        ) as status:
            thread.start()
            placeholder = st.empty()
            _drain_progress(evt_queue, thread, placeholder, log)

            if "error" in result_holder:
                status.update(
                    label=f"❌ Failed: {result_holder['error']}", state="error",
                )
                return

            summary = result_holder["summary"]
            status.update(
                label=f"✅ Done — {summary['word_count']} words "
                f"(tone {summary['tone_score']:.1f}, "
                f"SEO {summary['seo_score']:.1f}, "
                f"{summary['retry_count']} retries)",
                state="complete",
            )
    finally:
        bus.unsubscribe(run_id)

    summary = result_holder.get("summary", {})
    if summary:
        st.success("Draft saved.")
        c1, c2 = st.columns([1, 1])
        c1.markdown(f"**Markdown:** `{summary['output_file']}`")
        c2.markdown(f"**Image:** `{summary['image_file']}`")
        st.info("Switch to the **📰 Drafts** tab to preview.")


# ---------------------------------------------------------------------------
# Drafts tab — gallery
# ---------------------------------------------------------------------------

_FRONTMATTER_RE = re.compile(r"^---\n(.+?)\n---\n", re.DOTALL)


def _parse_frontmatter(md: str) -> dict[str, str]:
    """Tiny YAML-ish parser — handles flat scalar key: value frontmatter only."""
    match = _FRONTMATTER_RE.match(md)
    if not match:
        return {}
    fm: dict[str, str] = {}
    for line in match.group(1).splitlines():
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        fm[key.strip()] = value.strip().strip('"')
    return fm


def _strip_frontmatter(md: str) -> str:
    return _FRONTMATTER_RE.sub("", md, count=1).lstrip("\n")


def _draft_records() -> list[Run]:
    with session_scope() as s:
        runs = s.exec(
            select(Run)
            .where(Run.status == "success")
            .order_by(Run.completed_at.desc())
        ).all()
        for r in runs:
            s.expunge(r)
        return runs


def render_drafts_tab() -> None:
    st.subheader("Drafts")
    runs = _draft_records()
    if not runs:
        st.info("No drafts yet. Generate one in the **🚀 Generate** tab.")
        return

    for run in runs:
        if not run.output_file or not Path(run.output_file).exists():
            continue
        md = Path(run.output_file).read_text(encoding="utf-8")
        fm = _parse_frontmatter(md)
        body = _strip_frontmatter(md)

        with st.container(border=True):
            cols = st.columns([1, 3])
            with cols[0]:
                if run.image_file and Path(run.image_file).exists():
                    st.image(run.image_file, use_container_width=True)
                else:
                    st.caption("(no hero image)")
            with cols[1]:
                st.markdown(f"### {fm.get('title', '(untitled)')}")
                meta_chips = []
                if (date := fm.get("date")):
                    meta_chips.append(f"📅 {date}")
                if (wc := fm.get("word_count")):
                    meta_chips.append(f"📝 {wc} words")
                if (tone := fm.get("tone_score")):
                    meta_chips.append(f"🎙 tone {tone}/5")
                if (seo := fm.get("seo_score")):
                    meta_chips.append(f"🔍 SEO {seo}/5")
                if (rt := fm.get("read_time")):
                    meta_chips.append(f"⏱ {rt}")
                st.caption(" · ".join(meta_chips))
                if (seo_meta := fm.get("seo_meta")):
                    st.caption(f"*{seo_meta}*")

                with st.expander("📄 View article"):
                    st.markdown(body)

                st.caption(
                    f"`{Path(run.output_file).name}` · "
                    f"run `{run.run_id[:8]}` · "
                    f"completed {_fmt_dt(run.completed_at)}"
                )


def _fmt_dt(dt: datetime | None) -> str:
    if dt is None:
        return "?"
    return dt.strftime("%Y-%m-%d %H:%M")


# ---------------------------------------------------------------------------
# Render
# ---------------------------------------------------------------------------

with tab_topics:
    render_topics_tab()

with tab_generate:
    render_generate_tab()

with tab_drafts:
    render_drafts_tab()
