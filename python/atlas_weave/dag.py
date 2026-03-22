from __future__ import annotations

from dataclasses import dataclass

from atlas_weave.recipe import Recipe


@dataclass(frozen=True, slots=True)
class DagPlan:
    levels: list[list[str]]
    dependencies: dict[str, set[str]]
    downstream: dict[str, set[str]]


def build_execution_plan(recipe: Recipe) -> DagPlan:
    agent_map = recipe.agent_type_map()
    agent_names = list(agent_map.keys())

    if len(agent_names) != len(recipe.agent_types()):
        raise ValueError("recipe contains duplicate agent names")

    dependencies = {name: set() for name in agent_names}
    downstream = {name: set() for name in agent_names}
    indegree = {name: 0 for name in agent_names}

    for source, target in recipe.edges:
        if source not in agent_map or target not in agent_map:
            raise ValueError(f"edge references unknown agent: {source}->{target}")
        if source == target:
            raise ValueError(f"self-referential edge is not allowed: {source}")
        if target not in downstream[source]:
            downstream[source].add(target)
            dependencies[target].add(source)
            indegree[target] += 1

    remaining = set(agent_names)
    levels: list[list[str]] = []

    while remaining:
        ready = [
            name for name in agent_names if name in remaining and indegree[name] == 0
        ]
        if not ready:
            raise ValueError("recipe graph contains a cycle")

        levels.append(ready)
        for name in ready:
            remaining.remove(name)
            for child in downstream[name]:
                indegree[child] -= 1

    return DagPlan(levels=levels, dependencies=dependencies, downstream=downstream)
