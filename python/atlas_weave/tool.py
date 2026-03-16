from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from atlas_weave.context import AgentContext


class Tool(ABC):
    name: str
    description: str

    @abstractmethod
    async def call(self, ctx: AgentContext, **kwargs: Any) -> Any:
        """Execute the tool."""


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool:
        return self._tools[name]

    def __getattr__(self, name: str) -> Tool:
        try:
            return self._tools[name]
        except KeyError as error:
            raise AttributeError(name) from error
