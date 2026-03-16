from __future__ import annotations

import asyncio
from time import perf_counter
from typing import Any

from atlas_weave.events import EventEmitter


NAME = "test_echo"
DESCRIPTION = "Test recipe that emits 10 log messages with one-second delays."
VERSION = "0.1.0"


async def run(run_id: str, emitter: EventEmitter, config: dict[str, Any]) -> None:
    del run_id, config

    node_id = "echo_agent"
    started_at = perf_counter()
    emitter.node_started(node_id)

    for index in range(10):
        step = index + 1
        emitter.log(node_id, "info", f"Echo message {step}/10")
        emitter.progress(node_id, step / 10, f"Processed echo step {step} of 10")
        await asyncio.sleep(1)

    duration_ms = int((perf_counter() - started_at) * 1000)
    emitter.node_completed(
        node_id,
        duration_ms=duration_ms,
        summary={"messages_emitted": 10},
    )
    emitter.run_completed({"recipe": NAME, "messages_emitted": 10})
