"""Stage 1: load state, select next pending topic, create Run record."""

from __future__ import annotations

import uuid

from sqlmodel import select

from agent.db import Run, Topic, session_scope, utcnow
from agent.progress import bus


def run(topic_id: int | None = None, run_id: str | None = None) -> tuple[Topic, str]:
    """Select a topic and start a new run.

    If `topic_id` is provided, that topic is used regardless of status.
    Otherwise selects the highest-priority pending topic.

    If `run_id` is provided, it is used as the run identifier. This lets the
    UI subscribe to the progress bus before the agent thread starts.
    """
    with session_scope() as session:
        if topic_id is not None:
            topic = session.get(Topic, topic_id)
            if topic is None:
                raise LookupError(f"Topic id={topic_id} not found")
        else:
            stmt = (
                select(Topic)
                .where(Topic.status == "pending")
                .order_by(Topic.priority.desc(), Topic.created_at.asc())
            )
            topic = session.exec(stmt).first()
            if topic is None:
                raise LookupError("No pending topics available")

        run_id = run_id or str(uuid.uuid4())
        run_row = Run(
            run_id=run_id,
            topic_id=topic.id,
            status="in_progress",
            current_stage="init",
            started_at=utcnow(),
        )
        session.add(run_row)
        session.flush()
        session.refresh(topic)

        # detach so the caller can use these outside the session
        session.expunge(topic)

        bus.emit(run_id, "init", f"Selected topic: {topic.title}", level="info")
        return topic, run_id
