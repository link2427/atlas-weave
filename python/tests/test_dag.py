from __future__ import annotations

import asyncio
import json

import pytest

from atlas_weave.dag import build_execution_plan
from atlas_weave.recipe import Recipe
from atlas_weave.runner import describe_recipe, run_recipe
from recipes.test_pipeline.recipe import TestPipelineRecipe


def test_build_execution_plan_for_pipeline_recipe() -> None:
    plan = build_execution_plan(TestPipelineRecipe())

    assert plan.levels == [
        ["source_agent"],
        ["transform_agent"],
        ["validate_agent"],
    ]


def test_build_execution_plan_rejects_cycles() -> None:
    class CyclicRecipe(Recipe):
        name = "cyclic"
        description = "cyclic"
        agents = TestPipelineRecipe.agents
        edges = [
            ("source_agent", "transform_agent"),
            ("transform_agent", "source_agent"),
        ]

    with pytest.raises(ValueError, match="cycle"):
        build_execution_plan(CyclicRecipe())


def test_run_recipe_success_emits_completion_summary(capsys) -> None:
    asyncio.run(run_recipe("test_pipeline", "run-success", {"fail_b": False}))
    events = [line for line in capsys.readouterr().out.splitlines() if line]

    assert any(
        '"type":"node_completed"' in event and '"node_id":"validate_agent"' in event
        for event in events
    )
    assert any(
        '"type":"run_completed"' in event and '"completed_nodes":3' in event
        for event in events
    )


def test_run_recipe_failure_skips_downstream_nodes(capsys) -> None:
    asyncio.run(run_recipe("test_pipeline", "run-failure", {"fail_b": True}))
    events = [line for line in capsys.readouterr().out.splitlines() if line]

    assert any(
        '"type":"node_failed"' in event and '"node_id":"transform_agent"' in event
        for event in events
    )
    assert any(
        '"type":"node_skipped"' in event and '"node_id":"validate_agent"' in event
        for event in events
    )
    assert any('"type":"run_failed"' in event for event in events)


def test_describe_recipe_returns_real_metadata() -> None:
    metadata = describe_recipe("test_pipeline")

    assert metadata["name"] == "test_pipeline"
    assert metadata["dag"]["edges"] == [
        ["source_agent", "transform_agent"],
        ["transform_agent", "validate_agent"],
    ]
    assert metadata["config_schema"]["fail_b"]["default"] is False


def test_run_recipe_protocol_cancel_emits_cancel_events(capsys, monkeypatch) -> None:
    stdin_lines = iter(
        [json.dumps({"type": "cancel_run", "run_id": "run-cancel"}) + "\n", ""]
    )
    monkeypatch.setattr("sys.stdin.readline", lambda: next(stdin_lines))

    async def run() -> None:
        task = asyncio.create_task(
            run_recipe("test_echo", "run-cancel", {}, protocol_mode=True)
        )
        await asyncio.sleep(0.15)
        await task

    asyncio.run(run())
    events = [line for line in capsys.readouterr().out.splitlines() if line]

    assert any('"type":"node_cancelled"' in event for event in events)
    assert any('"type":"run_cancelled"' in event for event in events)
