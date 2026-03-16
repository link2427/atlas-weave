from __future__ import annotations

from abc import ABC, abstractmethod
from typing import ClassVar

from pydantic import BaseModel, Field

from atlas_weave.context import AgentContext


class AgentResult(BaseModel):
    records_processed: int = 0
    records_created: int = 0
    records_updated: int = 0
    errors: int = 0
    summary: dict[str, object] = Field(default_factory=dict)


class Agent(ABC):
    name: ClassVar[str]
    description: ClassVar[str]
    inputs: ClassVar[list[str]] = []
    outputs: ClassVar[list[str]] = []

    @abstractmethod
    async def execute(self, ctx: AgentContext) -> AgentResult:
        """Execute the agent for a single run."""
