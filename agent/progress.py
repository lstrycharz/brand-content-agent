"""In-memory progress bus shared between agent and UI."""

from __future__ import annotations

import queue
import threading
from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass
class ProgressEvent:
    run_id: str
    stage: str
    message: str
    timestamp: datetime
    level: str = "info"  # info | warning | error | success


class ProgressBus:
    """Thread-safe pub/sub for stage progress updates."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._subscribers: dict[str, queue.Queue[ProgressEvent]] = {}

    def subscribe(self, run_id: str) -> queue.Queue[ProgressEvent]:
        with self._lock:
            q: queue.Queue[ProgressEvent] = queue.Queue()
            self._subscribers[run_id] = q
            return q

    def unsubscribe(self, run_id: str) -> None:
        with self._lock:
            self._subscribers.pop(run_id, None)

    def emit(self, run_id: str, stage: str, message: str, level: str = "info") -> None:
        event = ProgressEvent(
            run_id=run_id,
            stage=stage,
            message=message,
            timestamp=datetime.now(timezone.utc),
            level=level,
        )
        with self._lock:
            q = self._subscribers.get(run_id)
        if q is not None:
            q.put(event)


bus = ProgressBus()
