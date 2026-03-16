from __future__ import annotations

import asyncio
from typing import Any

from atlas_weave import Agent, AgentContext, AgentResult, Recipe


class SourceAgent(Agent):
    name = "source_agent"
    description = "Generate source records for downstream agents."
    outputs = ["source_records"]

    async def execute(self, ctx: AgentContext) -> AgentResult:
        records = [1, 2, 3]
        ctx.state[self.name] = {"records": records}
        ctx.emit.log(self.name, "info", "Generated source records")
        ctx.emit.progress(self.name, 1.0, "Source records ready")
        await asyncio.sleep(0.05)
        return AgentResult(
            records_created=len(records),
            summary={"records": records},
        )


class TransformAgent(Agent):
    name = "transform_agent"
    description = "Transform records from the source agent."
    inputs = ["source_records"]
    outputs = ["transformed_records"]

    async def execute(self, ctx: AgentContext) -> AgentResult:
        source_records = ctx.state["source_agent"]["records"]
        ctx.emit.progress(self.name, 0.5, "Loaded source records")
        await asyncio.sleep(0.05)

        if bool(ctx.config.get("fail_b", False)):
            raise RuntimeError("forced transform failure via fail_b")

        transformed_records = [value * 2 for value in source_records]
        ctx.state[self.name] = {"records": transformed_records}
        ctx.emit.log(self.name, "info", "Transformed records")
        ctx.emit.progress(self.name, 1.0, "Transform complete")

        return AgentResult(
            records_processed=len(source_records),
            records_updated=len(transformed_records),
            summary={"records": transformed_records},
        )


class ValidateAgent(Agent):
    name = "validate_agent"
    description = "Validate transformed records."
    inputs = ["transformed_records"]

    async def execute(self, ctx: AgentContext) -> AgentResult:
        transformed_records = ctx.state["transform_agent"]["records"]
        is_valid = all(value % 2 == 0 for value in transformed_records)
        ctx.emit.log(self.name, "info", "Validated transformed records")
        ctx.emit.progress(self.name, 1.0, "Validation complete")
        await asyncio.sleep(0.05)

        return AgentResult(
            records_processed=len(transformed_records),
            summary={
                "is_valid": is_valid,
                "record_count": len(transformed_records),
            },
        )


class TestPipelineRecipe(Recipe):
    name = "test_pipeline"
    description = "Three-agent DAG for success and failure-path validation."
    version = "0.1.0"
    agents = [SourceAgent, TransformAgent, ValidateAgent]
    edges = [
        ("source_agent", "transform_agent"),
        ("transform_agent", "validate_agent"),
    ]
    config_schema: dict[str, Any] = {
        "fail_b": {"type": "boolean", "default": False},
    }


RECIPE = TestPipelineRecipe()
