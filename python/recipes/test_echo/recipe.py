from __future__ import annotations

import asyncio
from typing import Any

from atlas_weave import Agent, AgentContext, AgentResult, Recipe


class EchoAgent(Agent):
    name = "echo_agent"
    description = "Emit 10 timed log messages."

    async def execute(self, ctx: AgentContext) -> AgentResult:
        for index in range(10):
            ctx.raise_if_cancelled()
            step = index + 1
            ctx.emit.log(self.name, "info", f"Echo message {step}/10")
            ctx.emit.progress(self.name, step / 10, f"Processed echo step {step} of 10")
            await asyncio.sleep(1)

        return AgentResult(
            records_processed=10,
            summary={"messages_emitted": 10},
        )


class TestEchoRecipe(Recipe):
    name = "test_echo"
    description = "Test recipe that emits 10 log messages with one-second delays."
    version = "0.2.0"
    agents = [EchoAgent]
    edges: list[tuple[str, str]] = []
    config_schema: dict[str, Any] = {}


RECIPE = TestEchoRecipe()
