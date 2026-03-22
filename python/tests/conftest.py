from __future__ import annotations

import json
from io import StringIO
from typing import Any

from atlas_weave.context import AgentContext, CancellationToken
from atlas_weave.events import EventEmitter
from atlas_weave.tool import ToolRegistry


def make_context(stream: StringIO | None = None) -> tuple[AgentContext, StringIO]:
    output = stream or StringIO()
    ctx = AgentContext(
        run_id="test-run",
        node_id="tool_node",
        config={},
        db=None,
        tools=ToolRegistry(),
        emit=EventEmitter(run_id="test-run", stream=output),
        cancellation=CancellationToken(),
        state={},
    )
    return ctx, output


def read_events(stream: StringIO) -> list[dict[str, Any]]:
    stream.seek(0)
    return [json.loads(line) for line in stream.getvalue().splitlines() if line]
