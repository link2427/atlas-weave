from __future__ import annotations

import json
import sys
from collections.abc import Callable
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
    hooks: list[Callable[[dict[str, Any]], None]] = field(default_factory=list)

    def emit(self, event_type: str, **payload: Any) -> None:
        event = {
            "type": event_type,
            "run_id": self.run_id,
            "timestamp": payload.pop("timestamp", _utc_now()),
            **payload,
        }
        self.stream.write(json.dumps(event, separators=(",", ":")) + "\n")
        self.stream.flush()
        for hook in self.hooks:
            hook(dict(event))

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

    def node_failed(self, node_id: str, error: str) -> None:
        self.emit("node_failed", node_id=node_id, error=error)

    def node_skipped(self, node_id: str, message: str) -> None:
        self.emit("node_skipped", node_id=node_id, message=message)

    def node_cancelled(self, node_id: str, message: str) -> None:
        self.emit("node_cancelled", node_id=node_id, message=message)

    def tool_call(
        self,
        node_id: str,
        tool: str,
        request_id: str,
        input: dict[str, Any],
    ) -> None:
        self.emit(
            "tool_call",
            node_id=node_id,
            tool=tool,
            request_id=request_id,
            input=input,
        )

    def tool_result(
        self,
        node_id: str,
        tool: str,
        request_id: str,
        output: Any,
        duration_ms: int,
        cache_hit: bool | None = None,
        error: str | None = None,
    ) -> None:
        payload: dict[str, Any] = {
            "node_id": node_id,
            "tool": tool,
            "request_id": request_id,
            "output": output,
            "duration_ms": duration_ms,
        }
        if cache_hit is not None:
            payload["cache_hit"] = cache_hit
        if error is not None:
            payload["error"] = error
        self.emit("tool_result", **payload)

    def llm_call(
        self,
        node_id: str,
        provider: str,
        model: str,
        request_id: str,
        input: dict[str, Any],
        prompt_tokens: int | None = None,
    ) -> None:
        payload: dict[str, Any] = {
            "node_id": node_id,
            "provider": provider,
            "model": model,
            "request_id": request_id,
            "input": input,
        }
        if prompt_tokens is not None:
            payload["prompt_tokens"] = prompt_tokens
        self.emit("llm_call", **payload)

    def llm_result(
        self,
        node_id: str,
        provider: str,
        model: str,
        request_id: str,
        output: Any,
        duration_ms: int,
        completion_tokens: int,
        estimated_cost_usd: float,
        prompt_tokens: int | None = None,
        error: str | None = None,
    ) -> None:
        payload: dict[str, Any] = {
            "node_id": node_id,
            "provider": provider,
            "model": model,
            "request_id": request_id,
            "output": output,
            "duration_ms": duration_ms,
            "completion_tokens": completion_tokens,
            "estimated_cost_usd": estimated_cost_usd,
        }
        if prompt_tokens is not None:
            payload["prompt_tokens"] = prompt_tokens
        if error is not None:
            payload["error"] = error
        self.emit("llm_result", **payload)

    def run_completed(self, summary: dict[str, Any]) -> None:
        self.emit("run_completed", summary=summary)

    def run_failed(self, error: str) -> None:
        self.emit("run_failed", error=error)

    def run_cancelled(self, message: str) -> None:
        self.emit("run_cancelled", message=message)
