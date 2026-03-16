from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from atlas_weave.events import EventEmitter
from atlas_weave.tool import ToolRegistry


@dataclass(slots=True)
class AgentContext:
    run_id: str
    config: dict[str, Any]
    db: Any | None
    tools: ToolRegistry
    emit: EventEmitter
    state: dict[str, Any] = field(default_factory=dict)
