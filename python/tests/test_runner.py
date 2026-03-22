from __future__ import annotations

import asyncio
import json
from typing import Any

from atlas_weave import Agent, AgentContext, AgentResult, Recipe
from atlas_weave.dag import build_execution_plan
from atlas_weave.runner import RunMetrics, _collect_descendants, run_recipe


# -- Four-node recipe: A → B → C, A → B → D ----------------------------------


class AgentA(Agent):
    name = "a"
    description = "root"

    async def execute(self, ctx: AgentContext) -> AgentResult:
        return AgentResult(records_processed=1, summary={"ok": True})


class AgentB(Agent):
    name = "b"
    description = "middle (fails if configured)"

    async def execute(self, ctx: AgentContext) -> AgentResult:
        if ctx.config.get("fail_b"):
            raise RuntimeError("forced failure")
        return AgentResult(records_processed=1, summary={"ok": True})


class AgentC(Agent):
    name = "c"
    description = "leaf 1"

    async def execute(self, ctx: AgentContext) -> AgentResult:
        return AgentResult(records_processed=1, summary={"ok": True})


class AgentD(Agent):
    name = "d"
    description = "leaf 2"

    async def execute(self, ctx: AgentContext) -> AgentResult:
        return AgentResult(records_processed=1, summary={"ok": True})


class FourNodeRecipe(Recipe):
    name = "four_node"
    description = "A→B→C, A→B→D"
    version = "0.1.0"
    agents = [AgentA, AgentB, AgentC, AgentD]
    edges = [("a", "b"), ("b", "c"), ("b", "d")]
    config_schema: dict[str, Any] = {"fail_b": {"type": "boolean", "default": False}}


RECIPE = FourNodeRecipe()


# -- Helpers -------------------------------------------------------------------


def _parse_events(capsys) -> list[dict[str, Any]]:
    return [json.loads(line) for line in capsys.readouterr().out.splitlines() if line]


# -- Tests ---------------------------------------------------------------------


def test_resume_state_skips_completed_nodes(capsys, monkeypatch) -> None:
    monkeypatch.setattr("atlas_weave.runner._load_recipe", lambda name: RECIPE)

    asyncio.run(
        run_recipe("four_node", "run-resume", {}, resume_state={"a": "completed"})
    )
    events = _parse_events(capsys)

    skipped = [e for e in events if e["type"] == "node_skipped" and e["node_id"] == "a"]
    assert len(skipped) == 1
    assert "Retained from prior run" in skipped[0]["message"]

    completed_ids = {e["node_id"] for e in events if e["type"] == "node_completed"}
    assert "b" in completed_ids
    assert "c" in completed_ids
    assert "d" in completed_ids


def test_resume_state_ignores_unknown_nodes(capsys, monkeypatch) -> None:
    monkeypatch.setattr("atlas_weave.runner._load_recipe", lambda name: RECIPE)

    asyncio.run(
        run_recipe(
            "four_node", "run-unknown", {}, resume_state={"nonexistent": "completed"}
        )
    )
    events = _parse_events(capsys)

    completed_ids = {e["node_id"] for e in events if e["type"] == "node_completed"}
    assert "a" in completed_ids
    assert "b" in completed_ids
    assert "c" in completed_ids
    assert "d" in completed_ids


def test_failure_propagation_skips_all_descendants(capsys, monkeypatch) -> None:
    monkeypatch.setattr(
        "atlas_weave.runner._load_recipe",
        lambda name: RECIPE,
    )

    asyncio.run(run_recipe("four_node", "run-fail", {"fail_b": True}))
    events = _parse_events(capsys)

    failed_ids = {e["node_id"] for e in events if e["type"] == "node_failed"}
    assert "b" in failed_ids

    skipped_ids = {e["node_id"] for e in events if e["type"] == "node_skipped"}
    assert "c" in skipped_ids
    assert "d" in skipped_ids

    assert any(e["type"] == "run_failed" for e in events)


def test_collect_descendants() -> None:
    # Diamond: A→B, A→C, B→D, C→D
    class DiamondRecipe(Recipe):
        name = "diamond"
        description = "diamond"
        version = "0.1.0"
        agents = [AgentA, AgentB, AgentC, AgentD]
        edges = [("a", "b"), ("a", "c"), ("b", "d"), ("c", "d")]

    plan = build_execution_plan(DiamondRecipe())
    descendants = _collect_descendants("a", plan)
    assert set(descendants) == {"b", "c", "d"}

    descendants_b = _collect_descendants("b", plan)
    assert set(descendants_b) == {"d"}


def test_run_metrics_records_events() -> None:
    metrics = RunMetrics()

    metrics.record({"type": "tool_call", "tool": "http"})
    metrics.record({"type": "tool_call", "tool": "http"})
    metrics.record({"type": "llm_call", "provider": "openrouter"})
    metrics.record(
        {
            "type": "llm_result",
            "prompt_tokens": 100,
            "completion_tokens": 50,
            "estimated_cost_usd": 0.005,
        }
    )
    metrics.record(
        {
            "type": "llm_result",
            "prompt_tokens": 200,
            "completion_tokens": 30,
            "estimated_cost_usd": 0.003,
        }
    )

    s = metrics.summary()
    assert s["tool_calls"] == 2
    assert s["llm_calls"] == 1
    assert s["llm_prompt_tokens"] == 300
    assert s["llm_completion_tokens"] == 80
    assert s["llm_cost_usd"] == 0.008
