from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from time import perf_counter
from typing import TYPE_CHECKING, Any, TypeVar
from uuid import uuid4

if TYPE_CHECKING:
    from atlas_weave.context import AgentContext

ResultT = TypeVar("ResultT")


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


def new_request_id() -> str:
    return uuid4().hex


async def run_tool_operation(
    *,
    ctx: AgentContext,
    node_id: str,
    tool_name: str,
    input_payload: dict[str, Any],
    operation: Callable[[], Awaitable[ResultT]],
    request_id: str | None = None,
    serialize_result: Callable[[ResultT], Any] | None = None,
    cache_hit: bool | None = None,
) -> ResultT:
    request_id = request_id or new_request_id()
    ctx.emit.tool_call(node_id=node_id, tool=tool_name, request_id=request_id, input=input_payload)
    started_at = perf_counter()

    try:
        result = await operation()
    except Exception as error:  # noqa: BLE001
        duration_ms = int((perf_counter() - started_at) * 1000)
        ctx.emit.tool_result(
            node_id=node_id,
            tool=tool_name,
            request_id=request_id,
            output={},
            duration_ms=duration_ms,
            cache_hit=cache_hit,
            error=str(error),
        )
        raise

    duration_ms = int((perf_counter() - started_at) * 1000)
    ctx.emit.tool_result(
        node_id=node_id,
        tool=tool_name,
        request_id=request_id,
        output=serialize_result(result) if serialize_result else result,
        duration_ms=duration_ms,
        cache_hit=cache_hit,
    )
    return result


async def run_llm_operation(
    *,
    ctx: AgentContext,
    node_id: str,
    provider: str,
    model: str,
    input_payload: dict[str, Any],
    operation: Callable[[], Awaitable[dict[str, Any]]],
    request_id: str | None = None,
) -> dict[str, Any]:
    request_id = request_id or new_request_id()
    ctx.emit.llm_call(
        node_id=node_id,
        provider=provider,
        model=model,
        request_id=request_id,
        input=input_payload,
    )
    started_at = perf_counter()

    try:
        result = await operation()
    except Exception as error:  # noqa: BLE001
        duration_ms = int((perf_counter() - started_at) * 1000)
        ctx.emit.llm_result(
            node_id=node_id,
            provider=provider,
            model=model,
            request_id=request_id,
            output={},
            duration_ms=duration_ms,
            prompt_tokens=0,
            completion_tokens=0,
            estimated_cost_usd=0.0,
            error=str(error),
        )
        raise

    duration_ms = int((perf_counter() - started_at) * 1000)
    ctx.emit.llm_result(
        node_id=node_id,
        provider=provider,
        model=model,
        request_id=request_id,
        output=result.get("output", {}),
        duration_ms=duration_ms,
        prompt_tokens=int(result.get("prompt_tokens", 0)),
        completion_tokens=int(result.get("completion_tokens", 0)),
        estimated_cost_usd=float(result.get("estimated_cost_usd", 0.0)),
    )
    return result
