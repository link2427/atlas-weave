from __future__ import annotations

from typing import Any

from atlas_weave.agent import Agent


class Recipe:
    name: str = ""
    description: str = ""
    version: str = "0.1.0"
    agents: list[type[Agent]] = []
    edges: list[tuple[str, str]] = []
    config_schema: dict[str, Any] = {}

    def agent_types(self) -> list[type[Agent]]:
        return list(self.agents)

    def agent_type_map(self) -> dict[str, type[Agent]]:
        return {agent_type.name: agent_type for agent_type in self.agent_types()}

    def dag_metadata(self) -> dict[str, object]:
        nodes = [
            {
                "id": agent_type.name,
                "label": agent_type.name.replace("_", " ").title(),
                "description": agent_type.description,
            }
            for agent_type in self.agent_types()
        ]
        edges = [[source, target] for source, target in self.edges]
        return {"nodes": nodes, "edges": edges}

    def metadata(self) -> dict[str, object]:
        return {
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "config_schema": self.config_schema,
            "dag": self.dag_metadata(),
        }
