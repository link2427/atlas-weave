from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable

import httpx

from atlas_weave.context import AgentContext
from atlas_weave.tool import Tool, run_tool_operation

TEXT_PREVIEW_LIMIT = 1200
VISIBLE_REQUEST_HEADERS = {
    "accept",
    "content-type",
    "http-referer",
    "referer",
    "user-agent",
    "x-title",
}
VISIBLE_RESPONSE_HEADERS = {
    "cache-control",
    "content-type",
    "etag",
    "last-modified",
    "x-request-id",
}
REDACTED_HEADERS = {"api-key", "authorization", "x-api-key"}


@dataclass(slots=True)
class HttpToolResponse:
    method: str
    url: str
    final_url: str
    status_code: int
    headers: dict[str, str]
    content_type: str
    body_bytes: int
    text: str | None
    text_preview: str
    json_body: Any | None


class HttpTool(Tool):
    name = "http"
    description = (
        "Execute an HTTP request and emit structured request/response metadata."
    )

    def __init__(
        self,
        client_factory: Callable[[], httpx.AsyncClient] | None = None,
    ) -> None:
        self._client_factory = client_factory or (
            lambda: httpx.AsyncClient(follow_redirects=True)
        )

    async def call(
        self,
        ctx: AgentContext,
        *,
        method: str,
        url: str,
        headers: dict[str, str] | None = None,
        params: dict[str, Any] | None = None,
        json_body: Any | None = None,
        data: Any | None = None,
        timeout_s: float = 20.0,
        raise_for_status: bool = True,
    ) -> HttpToolResponse:
        node_id = ctx.node_id
        request_input = {
            "method": method.upper(),
            "url": url,
            "headers": _sanitize_headers(headers, VISIBLE_REQUEST_HEADERS),
            "params": params or {},
            "timeout_s": timeout_s,
        }

        async def operation() -> HttpToolResponse:
            async with self._client_factory() as client:
                response = await client.request(
                    method=method,
                    url=url,
                    headers=headers,
                    params=params,
                    json=json_body,
                    data=data,
                    timeout=timeout_s,
                )
                if raise_for_status:
                    response.raise_for_status()
                return _serialize_response(method, url, response)

        return await run_tool_operation(
            ctx=ctx,
            node_id=node_id,
            tool_name=self.name,
            input_payload=request_input,
            operation=operation,
            serialize_result=_tool_result_payload,
        )


def _serialize_response(
    method: str, url: str, response: httpx.Response
) -> HttpToolResponse:
    content_type = response.headers.get("content-type", "")
    text: str | None = response.text if _is_text_response(content_type) else None
    json_body: Any | None = None
    if "json" in content_type:
        try:
            json_body = response.json()
        except json.JSONDecodeError:
            json_body = None
    if json_body is None and text is not None:
        try:
            json_body = json.loads(text)
        except (json.JSONDecodeError, ValueError):
            pass

    return HttpToolResponse(
        method=method.upper(),
        url=url,
        final_url=str(response.url),
        status_code=response.status_code,
        headers=_sanitize_headers(dict(response.headers), VISIBLE_RESPONSE_HEADERS),
        content_type=content_type,
        body_bytes=len(response.content),
        text=text,
        text_preview=_truncate(text or "", TEXT_PREVIEW_LIMIT),
        json_body=json_body,
    )


def _tool_result_payload(result: HttpToolResponse) -> dict[str, Any]:
    return {
        "method": result.method,
        "url": result.url,
        "final_url": result.final_url,
        "status_code": result.status_code,
        "headers": result.headers,
        "content_type": result.content_type,
        "body_bytes": result.body_bytes,
        "text_preview": result.text_preview,
    }


def _truncate(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return value[: limit - 3] + "..."


def _sanitize_headers(
    headers: dict[str, str] | None,
    visible_keys: set[str],
) -> dict[str, str]:
    if not headers:
        return {}

    sanitized: dict[str, str] = {}
    for key, value in headers.items():
        lowered = key.lower()
        if lowered in REDACTED_HEADERS:
            sanitized[key] = "<redacted>"
        elif lowered in visible_keys:
            sanitized[key] = value
    return sanitized


def _is_text_response(content_type: str) -> bool:
    return (
        content_type.startswith("text/")
        or "html" in content_type
        or "json" in content_type
        or "xml" in content_type
    )
