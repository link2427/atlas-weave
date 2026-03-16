from __future__ import annotations

import argparse
import asyncio
import importlib
import json
import sys
from time import perf_counter
from typing import Any

from atlas_weave.context import AgentContext
from atlas_weave.dag import DagPlan, build_execution_plan
from atlas_weave.events import EventEmitter
from atlas_weave.recipe import Recipe
from atlas_weave.tool import ToolRegistry


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Atlas Weave recipe runner")
    parser.add_argument("--recipe", type=str, default=None)
    parser.add_argument("--run-id", type=str, default=None)
    parser.add_argument("--config-json", type=str, default=None)
    parser.add_argument("--describe-recipe", type=str, default=None)
    return parser.parse_args()


def _command_from_args_or_stdin(args: argparse.Namespace) -> dict[str, Any]:
    if args.recipe and args.run_id:
        return {
            "type": "start_run",
            "recipe": args.recipe,
            "run_id": args.run_id,
            "config": json.loads(args.config_json) if args.config_json else {},
        }

    line = sys.stdin.readline().strip()
    if not line:
        raise ValueError("expected start_run command on stdin")

    command = json.loads(line)
    if command.get("type") != "start_run":
        raise ValueError("unsupported command type")

    return command


def _load_recipe(recipe_name: str) -> Recipe:
    module = importlib.import_module(f"recipes.{recipe_name}.recipe")
    recipe = getattr(module, "RECIPE", None)
    if recipe is None or not isinstance(recipe, Recipe):
        raise AttributeError(f"recipe {recipe_name} does not export a Recipe instance named RECIPE")
    return recipe


def describe_recipe(recipe_name: str) -> dict[str, Any]:
    return _load_recipe(recipe_name).metadata()


def _collect_descendants(root: str, plan: DagPlan) -> list[str]:
    queue = list(plan.downstream[root])
    descendants: list[str] = []
    seen = set(queue)

    while queue:
        node = queue.pop(0)
        descendants.append(node)
        for child in plan.downstream[node]:
            if child not in seen:
                seen.add(child)
                queue.append(child)

    return descendants


async def _execute_agent(
    recipe: Recipe,
    agent_name: str,
    run_id: str,
    config: dict[str, Any],
    state: dict[str, Any],
    tools: ToolRegistry,
    emitter: EventEmitter,
) -> tuple[str, dict[str, Any] | None, str | None]:
    agent_type = recipe.agent_type_map()[agent_name]
    agent = agent_type()
    context = AgentContext(
        run_id=run_id,
        config=config,
        db=None,
        tools=tools,
        emit=emitter,
        state=state,
    )
    started_at = perf_counter()
    emitter.node_started(agent_name)

    try:
        result = await agent.execute(context)
    except Exception as error:  # noqa: BLE001
        emitter.node_failed(agent_name, str(error))
        return agent_name, None, str(error)

    duration_ms = int((perf_counter() - started_at) * 1000)
    summary = result.model_dump(mode="json")
    emitter.node_completed(agent_name, duration_ms=duration_ms, summary=summary)
    return agent_name, summary, None


async def run_recipe(recipe_name: str, run_id: str, config: dict[str, Any]) -> None:
    recipe = _load_recipe(recipe_name)
    plan = build_execution_plan(recipe)
    emitter = EventEmitter(run_id=run_id)
    tools = ToolRegistry()
    state: dict[str, Any] = {}
    status_by_node = {name: "pending" for name in recipe.agent_type_map()}
    summary_by_node: dict[str, dict[str, Any]] = {}
    failure_messages: dict[str, str] = {}

    for level in plan.levels:
        runnable = [name for name in level if status_by_node[name] == "pending"]
        if not runnable:
            continue

        outcomes = await asyncio.gather(
            *[
                _execute_agent(recipe, agent_name, run_id, config, state, tools, emitter)
                for agent_name in runnable
            ]
        )

        failed_nodes: list[str] = []
        for agent_name, summary, error in outcomes:
            if error is None and summary is not None:
                status_by_node[agent_name] = "completed"
                summary_by_node[agent_name] = summary
            else:
                status_by_node[agent_name] = "failed"
                failure_messages[agent_name] = error or "agent failed"
                failed_nodes.append(agent_name)

        for failed_node in failed_nodes:
            for skipped_node in _collect_descendants(failed_node, plan):
                if status_by_node[skipped_node] != "pending":
                    continue
                status_by_node[skipped_node] = "skipped"
                emitter.node_skipped(
                    skipped_node,
                    message=f"Skipped because dependency {failed_node} failed",
                )

        if failed_nodes:
            emitter.run_failed(
                " ; ".join(
                    f"{node}: {failure_messages[node]}"
                    for node in sorted(failure_messages.keys())
                )
            )
            return

    emitter.run_completed(
        {
            "recipe": recipe.name,
            "completed_nodes": sum(1 for status in status_by_node.values() if status == "completed"),
            "failed_nodes": sum(1 for status in status_by_node.values() if status == "failed"),
            "skipped_nodes": sum(1 for status in status_by_node.values() if status == "skipped"),
            "node_summaries": summary_by_node,
        }
    )


def main() -> None:
    args = parse_args()

    if args.describe_recipe:
        metadata = describe_recipe(args.describe_recipe)
        sys.stdout.write(json.dumps(metadata, separators=(",", ":")) + "\n")
        sys.stdout.flush()
        return

    try:
        command = _command_from_args_or_stdin(args)
        asyncio.run(
            run_recipe(
                recipe_name=str(command["recipe"]),
                run_id=str(command["run_id"]),
                config=dict(command.get("config", {})),
            )
        )
    except Exception as error:  # noqa: BLE001
        run_id = args.run_id or "unknown"
        EventEmitter(run_id=run_id).run_failed(str(error))
        raise


if __name__ == "__main__":
    main()
