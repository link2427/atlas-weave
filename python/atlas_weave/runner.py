from __future__ import annotations

import argparse
import asyncio
import importlib
import json
import sys
from dataclasses import dataclass
from time import perf_counter
from typing import Any

from atlas_weave.context import AgentContext, CancellationToken, RunCancelledError
from atlas_weave.dag import DagPlan, build_execution_plan
from atlas_weave.events import EventEmitter
from atlas_weave.recipe import Recipe
from atlas_weave.tool import ToolRegistry
from atlas_weave.tools import register_builtin_tools


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


@dataclass(slots=True)
class AgentOutcome:
    node_id: str
    status: str
    summary: dict[str, Any] | None = None
    error: str | None = None


@dataclass(slots=True)
class RunMetrics:
    tool_calls: int = 0
    llm_calls: int = 0
    llm_prompt_tokens: int = 0
    llm_completion_tokens: int = 0
    llm_cost_usd: float = 0.0

    def record(self, event: dict[str, Any]) -> None:
        if event["type"] == "tool_call":
            self.tool_calls += 1
        elif event["type"] == "llm_call":
            self.llm_calls += 1
        elif event["type"] == "llm_result":
            self.llm_prompt_tokens += int(event.get("prompt_tokens", 0) or 0)
            self.llm_completion_tokens += int(event.get("completion_tokens", 0) or 0)
            self.llm_cost_usd = round(
                self.llm_cost_usd + float(event.get("estimated_cost_usd", 0.0) or 0.0),
                6,
            )

    def summary(self) -> dict[str, Any]:
        return {
            "tool_calls": self.tool_calls,
            "llm_calls": self.llm_calls,
            "llm_prompt_tokens": self.llm_prompt_tokens,
            "llm_completion_tokens": self.llm_completion_tokens,
            "llm_cost_usd": self.llm_cost_usd,
        }


async def _listen_for_cancel(run_id: str, token: CancellationToken) -> None:
    while True:
        line = await asyncio.to_thread(sys.stdin.readline)
        if not line:
            return

        command = json.loads(line)
        if command.get("type") == "cancel_run" and command.get("run_id") == run_id:
            token.cancel("Run cancelled from Atlas Weave")
            return


async def _execute_agent(
    recipe: Recipe,
    agent_name: str,
    run_id: str,
    config: dict[str, Any],
    state: dict[str, Any],
    tools: ToolRegistry,
    emitter: EventEmitter,
    cancellation: CancellationToken,
) -> AgentOutcome:
    agent_type = recipe.agent_type_map()[agent_name]
    agent = agent_type()
    context = AgentContext(
        run_id=run_id,
        node_id=agent_name,
        config=config,
        db=None,
        tools=tools,
        emit=emitter,
        cancellation=cancellation,
        state=state,
    )
    context.raise_if_cancelled()
    started_at = perf_counter()
    emitter.node_started(agent_name)

    try:
        result = await agent.execute(context)
    except RunCancelledError as error:
        emitter.node_cancelled(agent_name, str(error))
        return AgentOutcome(node_id=agent_name, status="cancelled", error=str(error))
    except Exception as error:  # noqa: BLE001
        emitter.node_failed(agent_name, str(error))
        return AgentOutcome(node_id=agent_name, status="failed", error=str(error))

    duration_ms = int((perf_counter() - started_at) * 1000)
    summary = result.model_dump(mode="json")
    emitter.node_completed(agent_name, duration_ms=duration_ms, summary=summary)
    return AgentOutcome(node_id=agent_name, status="completed", summary=summary)


def _mark_skipped(
    roots: list[str],
    plan: DagPlan,
    status_by_node: dict[str, str],
    emitter: EventEmitter,
    message_factory: Any,
) -> None:
    for root in roots:
        for skipped_node in _collect_descendants(root, plan):
            if status_by_node[skipped_node] != "pending":
                continue
            status_by_node[skipped_node] = "skipped"
            emitter.node_skipped(skipped_node, message=str(message_factory(root)))


async def run_recipe(
    recipe_name: str,
    run_id: str,
    config: dict[str, Any],
    protocol_mode: bool = False,
) -> None:
    recipe = _load_recipe(recipe_name)
    plan = build_execution_plan(recipe)
    metrics = RunMetrics()
    emitter = EventEmitter(run_id=run_id, hooks=[metrics.record])
    tools = register_builtin_tools(ToolRegistry())
    state: dict[str, Any] = {}
    cancellation = CancellationToken()
    cancel_task: asyncio.Task[None] | None = None
    status_by_node = {name: "pending" for name in recipe.agent_type_map()}
    summary_by_node: dict[str, dict[str, Any]] = {}
    failure_messages: dict[str, str] = {}

    if protocol_mode:
        cancel_task = asyncio.create_task(_listen_for_cancel(run_id, cancellation))

    try:
        for level in plan.levels:
            if cancellation.cancelled:
                pending_nodes = [name for name, status in status_by_node.items() if status == "pending"]
                for node_id in pending_nodes:
                    status_by_node[node_id] = "skipped"
                    emitter.node_skipped(node_id, message=cancellation.message)
                emitter.run_cancelled(cancellation.message)
                return

            runnable = [name for name in level if status_by_node[name] == "pending"]
            if not runnable:
                continue

            outcomes = await asyncio.gather(
                *[
                    _execute_agent(
                        recipe,
                        agent_name,
                        run_id,
                        config,
                        state,
                        tools,
                        emitter,
                        cancellation,
                    )
                    for agent_name in runnable
                ]
            )

            failed_nodes: list[str] = []
            cancelled_nodes: list[str] = []
            for outcome in outcomes:
                if outcome.status == "completed" and outcome.summary is not None:
                    status_by_node[outcome.node_id] = "completed"
                    summary_by_node[outcome.node_id] = outcome.summary
                elif outcome.status == "failed":
                    status_by_node[outcome.node_id] = "failed"
                    failure_messages[outcome.node_id] = outcome.error or "agent failed"
                    failed_nodes.append(outcome.node_id)
                elif outcome.status == "cancelled":
                    status_by_node[outcome.node_id] = "cancelled"
                    cancelled_nodes.append(outcome.node_id)

            if failed_nodes:
                _mark_skipped(
                    failed_nodes,
                    plan,
                    status_by_node,
                    emitter,
                    lambda root: f"Skipped because dependency {root} failed",
                )
                emitter.run_failed(
                    " ; ".join(
                        f"{node}: {failure_messages[node]}"
                        for node in sorted(failure_messages.keys())
                    )
                )
                return

            if cancelled_nodes or cancellation.cancelled:
                _mark_skipped(
                    cancelled_nodes or runnable,
                    plan,
                    status_by_node,
                    emitter,
                    lambda _root: cancellation.message,
                )
                emitter.run_cancelled(cancellation.message)
                return

        emitter.run_completed(
            {
                "recipe": recipe.name,
                "completed_nodes": sum(1 for status in status_by_node.values() if status == "completed"),
                "failed_nodes": sum(1 for status in status_by_node.values() if status == "failed"),
                "skipped_nodes": sum(1 for status in status_by_node.values() if status == "skipped"),
                "cancelled_nodes": sum(1 for status in status_by_node.values() if status == "cancelled"),
                "node_summaries": summary_by_node,
                **dict(state.get("_run_summary", {})),
                **metrics.summary(),
            }
        )
    finally:
        if cancel_task is not None:
            cancel_task.cancel()
            try:
                await cancel_task
            except asyncio.CancelledError:
                pass


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
                protocol_mode=not (args.recipe and args.run_id),
            )
        )
    except Exception as error:  # noqa: BLE001
        run_id = args.run_id or "unknown"
        EventEmitter(run_id=run_id).run_failed(str(error))
        raise


if __name__ == "__main__":
    main()
