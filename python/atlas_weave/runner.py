from __future__ import annotations

import argparse
import asyncio
import importlib
import json
import sys
from typing import Any

from atlas_weave.events import EventEmitter


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Atlas Weave recipe runner")
    parser.add_argument("--recipe", type=str, default=None)
    parser.add_argument("--run-id", type=str, default=None)
    return parser.parse_args()


def _command_from_args_or_stdin(args: argparse.Namespace) -> dict[str, Any]:
    if args.recipe and args.run_id:
        return {
            "type": "start_run",
            "recipe": args.recipe,
            "run_id": args.run_id,
            "config": {},
        }

    line = sys.stdin.readline().strip()
    if not line:
        raise ValueError("expected start_run command on stdin")

    command = json.loads(line)
    if command.get("type") != "start_run":
        raise ValueError("unsupported command type")

    return command


async def run_recipe(recipe_name: str, run_id: str, config: dict[str, Any]) -> None:
    emitter = EventEmitter(run_id=run_id)
    module = importlib.import_module(f"recipes.{recipe_name}.recipe")

    recipe_runner = getattr(module, "run", None)
    if recipe_runner is None:
        raise AttributeError(f"recipe {recipe_name} does not export async run()")

    await recipe_runner(run_id=run_id, emitter=emitter, config=config)


def main() -> None:
    args = parse_args()

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
