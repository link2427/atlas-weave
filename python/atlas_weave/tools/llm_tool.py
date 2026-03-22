from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from typing import Any

from atlas_weave.context import AgentContext
from atlas_weave.tool import Tool, run_llm_operation
from atlas_weave.tools.http_tool import HttpTool

logger = logging.getLogger(__name__)

ANTHROPIC_PRICING = {
    "claude-3-5-haiku-20241022": (0.80, 4.00),
    "claude-3-5-haiku-latest": (0.80, 4.00),
    "claude-haiku-4-5-20251001": (0.80, 4.00),
    "claude-3-5-sonnet-20241022": (3.00, 15.00),
    "claude-3-5-sonnet-latest": (3.00, 15.00),
    "claude-3-7-sonnet-latest": (3.00, 15.00),
}

# Lazily populated from the OpenRouter /api/v1/models endpoint.
# Maps model ID → (prompt_rate_per_million, completion_rate_per_million).
_openrouter_pricing_cache: dict[str, tuple[float, float]] | None = None


@dataclass(slots=True)
class LLMProviderResponse:
    provider_request_id: str | None
    output: Any
    prompt_tokens: int
    completion_tokens: int
    estimated_cost_usd: float
    provider_model: str | None = None


class LLMTool(Tool):
    name = "llm"
    description = "Call a structured LLM provider through Anthropic or OpenRouter."

    def __init__(self, http_tool: HttpTool) -> None:
        self.http_tool = http_tool

    async def call(
        self,
        ctx: AgentContext,
        *,
        provider: str,
        model: str,
        messages: list[dict[str, Any]],
        system: str | None = None,
        max_tokens: int = 512,
        temperature: float = 0.2,
        json_schema: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        node_id = ctx.node_id
        input_payload = {
            "provider": provider,
            "model": model,
            "system": system,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "json_schema": json_schema,
        }

        async def operation() -> dict[str, Any]:
            provider_response = await self._provider(provider).complete(
                ctx=ctx,
                model=model,
                messages=messages,
                system=system,
                max_tokens=max_tokens,
                temperature=temperature,
                json_schema=json_schema,
            )
            return {
                "provider_request_id": provider_response.provider_request_id,
                "provider_model": provider_response.provider_model or model,
                "output": provider_response.output,
                "prompt_tokens": provider_response.prompt_tokens,
                "completion_tokens": provider_response.completion_tokens,
                "estimated_cost_usd": provider_response.estimated_cost_usd,
            }

        return await run_llm_operation(
            ctx=ctx,
            node_id=node_id,
            provider=provider,
            model=model,
            input_payload=input_payload,
            operation=operation,
        )

    def has_credentials(self, provider: str) -> bool:
        return bool(os.getenv(_credential_env_var(provider)))

    def _provider(self, provider: str) -> "_BaseProvider":
        if provider == "anthropic":
            return AnthropicProvider(self.http_tool)
        if provider == "openrouter":
            return OpenRouterProvider(self.http_tool)
        raise ValueError(f"unsupported LLM provider: {provider}")


class _BaseProvider:
    provider_name: str

    def __init__(self, http_tool: HttpTool) -> None:
        self.http_tool = http_tool

    def credential(self) -> str:
        env_var = _credential_env_var(self.provider_name)
        value = os.getenv(env_var)
        if not value:
            raise ValueError(
                f"missing credential for provider {self.provider_name}: {env_var}"
            )
        return value

    async def complete(
        self,
        *,
        ctx: AgentContext,
        model: str,
        messages: list[dict[str, Any]],
        system: str | None,
        max_tokens: int,
        temperature: float,
        json_schema: dict[str, Any] | None,
    ) -> LLMProviderResponse:
        raise NotImplementedError


class OpenRouterProvider(_BaseProvider):
    provider_name = "openrouter"

    async def complete(
        self,
        *,
        ctx: AgentContext,
        model: str,
        messages: list[dict[str, Any]],
        system: str | None,
        max_tokens: int,
        temperature: float,
        json_schema: dict[str, Any] | None,
    ) -> LLMProviderResponse:
        await _ensure_openrouter_pricing(self.http_tool, ctx)

        body: dict[str, Any] = {
            "model": model,
            "messages": _openai_messages(messages, system),
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if json_schema is not None:
            body["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": "atlas_weave_output",
                    "strict": True,
                    "schema": json_schema,
                },
            }

        response = await self.http_tool.call(
            ctx,
            method="POST",
            url="https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {self.credential()}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://atlas-weave.local",
                "X-Title": "Atlas Weave",
            },
            json_body=body,
        )
        payload = response.json_body or {}
        choices = payload.get("choices") or []
        if not choices:
            raise ValueError("OpenRouter response did not include choices")

        message = choices[0].get("message") or {}
        usage = payload.get("usage") or {}
        prompt_tokens = int(usage.get("prompt_tokens", 0))
        completion_tokens = int(usage.get("completion_tokens", 0))

        return LLMProviderResponse(
            provider_request_id=payload.get("id"),
            output=_extract_openai_output(message, json_schema),
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            estimated_cost_usd=_openrouter_cost(
                payload, model, prompt_tokens, completion_tokens
            ),
            provider_model=payload.get("model"),
        )


class AnthropicProvider(_BaseProvider):
    provider_name = "anthropic"

    async def complete(
        self,
        *,
        ctx: AgentContext,
        model: str,
        messages: list[dict[str, Any]],
        system: str | None,
        max_tokens: int,
        temperature: float,
        json_schema: dict[str, Any] | None,
    ) -> LLMProviderResponse:
        body: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if system:
            body["system"] = system
        if json_schema is not None:
            body["tools"] = [
                {
                    "name": "atlas_weave_output",
                    "description": "Return the structured Atlas Weave response payload",
                    "input_schema": json_schema,
                }
            ]
            body["tool_choice"] = {"type": "tool", "name": "atlas_weave_output"}

        response = await self.http_tool.call(
            ctx,
            method="POST",
            url="https://api.anthropic.com/v1/messages",
            headers={
                "content-type": "application/json",
                "x-api-key": self.credential(),
                "anthropic-version": "2023-06-01",
            },
            json_body=body,
        )
        payload = response.json_body or {}
        usage = payload.get("usage") or {}
        prompt_tokens = int(usage.get("input_tokens", 0))
        completion_tokens = int(usage.get("output_tokens", 0))

        return LLMProviderResponse(
            provider_request_id=payload.get("id"),
            output=_extract_anthropic_output(payload, json_schema),
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            estimated_cost_usd=_estimate_cost(
                model, prompt_tokens, completion_tokens, ANTHROPIC_PRICING
            ),
            provider_model=payload.get("model"),
        )


def _credential_env_var(provider: str) -> str:
    if provider == "anthropic":
        return "CLAUDE_API_KEY"
    if provider == "openrouter":
        return "OPENROUTER_API_KEY"
    raise ValueError(f"unsupported LLM provider: {provider}")


async def _ensure_openrouter_pricing(http_tool: HttpTool, ctx: AgentContext) -> None:
    """Fetch and cache model pricing from the OpenRouter API (once per process)."""
    global _openrouter_pricing_cache  # noqa: PLW0603
    if _openrouter_pricing_cache is not None:
        return
    try:
        response = await http_tool.call(
            ctx,
            method="GET",
            url="https://openrouter.ai/api/v1/models",
            headers={"Content-Type": "application/json"},
        )
        body = response.json_body or {}
        models = body.get("data") or (body if isinstance(body, list) else [])
        pricing_map: dict[str, tuple[float, float]] = {}
        for model_entry in models:
            model_id = model_entry.get("id")
            pricing = model_entry.get("pricing")
            if not model_id or not isinstance(pricing, dict):
                continue
            try:
                prompt_per_token = float(pricing.get("prompt") or 0)
                completion_per_token = float(pricing.get("completion") or 0)
            except (TypeError, ValueError):
                continue
            # Convert per-token to per-million-token rates
            pricing_map[model_id] = (
                round(prompt_per_token * 1_000_000, 4),
                round(completion_per_token * 1_000_000, 4),
            )
        _openrouter_pricing_cache = pricing_map
        logger.info("Fetched OpenRouter pricing for %d models", len(pricing_map))
    except Exception:  # noqa: BLE001
        logger.warning(
            "Failed to fetch OpenRouter model pricing; using hardcoded fallback"
        )
        _openrouter_pricing_cache = {}


def _openai_messages(
    messages: list[dict[str, Any]],
    system: str | None,
) -> list[dict[str, Any]]:
    normalized = []
    if system:
        normalized.append({"role": "system", "content": system})
    normalized.extend(messages)
    return normalized


def _extract_openai_output(
    message: dict[str, Any], json_schema: dict[str, Any] | None
) -> Any:
    content = message.get("content")
    if json_schema is None:
        return _openai_text_content(content)
    if isinstance(content, dict):
        return content
    if isinstance(content, str):
        return _parse_json_string(content)
    if isinstance(content, list):
        for part in content:
            if isinstance(part, dict):
                if isinstance(part.get("json"), dict):
                    return part["json"]
                if isinstance(part.get("input"), dict):
                    return part["input"]
                if isinstance(part.get("text"), str) and part.get("text", "").strip():
                    return _parse_json_string(part["text"])
    tool_calls = message.get("tool_calls")
    if isinstance(tool_calls, list):
        for tool_call in tool_calls:
            function = (
                tool_call.get("function") if isinstance(tool_call, dict) else None
            )
            arguments = (
                function.get("arguments") if isinstance(function, dict) else None
            )
            if isinstance(arguments, str) and arguments.strip():
                return _parse_json_string(arguments)
            if isinstance(arguments, dict):
                return arguments
    refusal = message.get("refusal")
    if refusal:
        raise ValueError(f"OpenRouter model refused structured output: {refusal}")
    raise ValueError("OpenRouter model did not return structured JSON output")


def _openai_text_content(content: Any) -> Any:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        text_parts: list[str] = []
        for part in content:
            if isinstance(part, dict) and isinstance(part.get("text"), str):
                text_parts.append(part["text"])
        return "\n".join(part for part in text_parts if part)
    return content


def _parse_json_string(value: str) -> Any:
    normalized = value.strip()
    if normalized.startswith("```"):
        normalized = _strip_code_fence(normalized)
    if not normalized:
        raise ValueError("OpenRouter returned empty structured output content")
    try:
        return json.loads(normalized)
    except json.JSONDecodeError as error:
        preview = normalized[:180]
        raise ValueError(
            f"OpenRouter structured output was not valid JSON: {preview}"
        ) from error


def _strip_code_fence(value: str) -> str:
    lines = value.splitlines()
    if len(lines) >= 2 and lines[0].startswith("```") and lines[-1].strip() == "```":
        return "\n".join(lines[1:-1]).strip()
    return value


def _extract_anthropic_output(
    payload: dict[str, Any], json_schema: dict[str, Any] | None
) -> Any:
    content = payload.get("content") or []
    if json_schema is None:
        text_blocks = [
            block.get("text", "") for block in content if block.get("type") == "text"
        ]
        return "\n".join(block for block in text_blocks if block)

    for block in content:
        if (
            block.get("type") == "tool_use"
            and block.get("name") == "atlas_weave_output"
        ):
            return block.get("input")
    raise ValueError(
        "Anthropic model did not return the requested structured output tool payload"
    )


def _openrouter_cost(
    payload: dict[str, Any],
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
) -> float:
    # Prefer cost reported directly by OpenRouter in the response
    usage = payload.get("usage") or {}
    for key in ("cost", "estimated_cost", "total_cost"):
        if key in usage:
            return float(usage[key])
        if key in payload:
            return float(payload[key])
    # Fall back to computing from cached API pricing
    resolved_model = str(payload.get("model") or model)
    pricing = _openrouter_pricing_cache or {}
    return _estimate_cost(resolved_model, prompt_tokens, completion_tokens, pricing)


def _estimate_cost(
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    pricing: dict[str, tuple[float, float]],
) -> float:
    prompt_rate, completion_rate = _find_pricing(model, pricing)
    if prompt_rate == 0.0 and completion_rate == 0.0:
        return 0.0
    prompt_cost = (prompt_tokens / 1_000_000) * prompt_rate
    completion_cost = (completion_tokens / 1_000_000) * completion_rate
    return round(prompt_cost + completion_cost, 6)


def _find_pricing(
    model: str,
    pricing: dict[str, tuple[float, float]],
) -> tuple[float, float]:
    if model in pricing:
        return pricing[model]

    lowered = model.lower()
    for key, value in pricing.items():
        candidate = key.lower()
        if candidate in lowered or lowered in candidate:
            return value
    return (0.0, 0.0)
