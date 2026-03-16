from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from atlas_weave.events import EventEmitter
from atlas_weave.tool import ToolRegistry


class RunCancelledError(RuntimeError):
    """Raised when a run is cancelled cooperatively."""


@dataclass(slots=True)
class CancellationToken:
    cancelled: bool = False
    message: str = "Run cancelled"

    def cancel(self, message: str = "Run cancelled") -> None:
        self.cancelled = True
        self.message = message

    def raise_if_cancelled(self) -> None:
        if self.cancelled:
            raise RunCancelledError(self.message)


@dataclass(slots=True)
class AgentContext:
    run_id: str
    node_id: str
    config: dict[str, Any]
    db: Any | None
    tools: ToolRegistry
    emit: EventEmitter
    cancellation: CancellationToken
    state: dict[str, Any] = field(default_factory=dict)

    @property
    def is_cancelled(self) -> bool:
        return self.cancellation.cancelled

    def raise_if_cancelled(self) -> None:
        self.cancellation.raise_if_cancelled()
