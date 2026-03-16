from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(slots=True)
class EventEmitter:
    """Writes newline-delimited JSON messages to stdout."""

    run_id: str
    stream: Any = field(default_factory=lambda: sys.stdout)

    def emit(self, event_type: str, **payload: Any) -> None:
        event = {
            "type": event_type,
            "run_id": self.run_id,
            "timestamp": payload.pop("timestamp", _utc_now()),
            **payload,
        }
        self.stream.write(json.dumps(event, separators=(",", ":")) + "\n")
        self.stream.flush()

    def log(self, node_id: str, level: str, message: str) -> None:
        self.emit("node_log", node_id=node_id, level=level, message=message)

    def progress(self, node_id: str, progress: float, message: str) -> None:
        self.emit("node_progress", node_id=node_id, progress=progress, message=message)

    def node_started(self, node_id: str) -> None:
        self.emit("node_started", node_id=node_id)

    def node_completed(self, node_id: str, duration_ms: int, summary: dict[str, Any]) -> None:
        self.emit(
            "node_completed",
            node_id=node_id,
            duration_ms=duration_ms,
            summary=summary,
        )

    def run_completed(self, summary: dict[str, Any]) -> None:
        self.emit("run_completed", summary=summary)

    def run_failed(self, error: str) -> None:
        self.emit("run_failed", error=error)
