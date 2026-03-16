from __future__ import annotations

import json
from io import StringIO
from pathlib import Path
from typing import Any

import httpx
import pytest

from atlas_weave.context import AgentContext, CancellationToken
from atlas_weave.events import EventEmitter
from atlas_weave.runner import run_recipe
from atlas_weave.tool import ToolRegistry
from atlas_weave.tools.http_tool import HttpTool
from atlas_weave.tools.llm_tool import LLMTool
from atlas_weave.tools.sqlite_tool import SQLiteTool
from atlas_weave.tools.web_scrape_tool import WebScrapeTool
from atlas_weave.tools.web_search_tool import WebSearchTool


def make_context(stream: StringIO | None = None) -> tuple[AgentContext, StringIO]:
    output = stream or StringIO()
    ctx = AgentContext(
        run_id="test-run",
        node_id="tool_node",
        config={},
        db=None,
        tools=ToolRegistry(),
        emit=EventEmitter(run_id="test-run", stream=output),
        cancellation=CancellationToken(),
        state={},
    )
    return ctx, output


def read_events(stream: StringIO) -> list[dict[str, Any]]:
    stream.seek(0)
    return [json.loads(line) for line in stream.getvalue().splitlines() if line]


@pytest.mark.anyio
async def test_http_tool_emits_success_events() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"ok": True},
            headers={"content-type": "application/json", "x-request-id": "req-1"},
            request=request,
        )

    tool = HttpTool(
        client_factory=lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler))
    )
    ctx, stream = make_context()

    result = await tool.call(ctx, method="GET", url="https://example.com/api")
    events = read_events(stream)

    assert result.json_body == {"ok": True}
    assert events[0]["type"] == "tool_call"
    assert events[1]["type"] == "tool_result"
    assert events[1]["tool"] == "http"
    assert events[1]["output"]["status_code"] == 200


@pytest.mark.anyio
async def test_http_tool_emits_error_result() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    tool = HttpTool(
        client_factory=lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler))
    )
    ctx, stream = make_context()

    with pytest.raises(httpx.ReadTimeout):
        await tool.call(ctx, method="GET", url="https://example.com/api")

    events = read_events(stream)
    assert events[0]["type"] == "tool_call"
    assert events[1]["type"] == "tool_result"
    assert "timed out" in events[1]["error"]


@pytest.mark.anyio
async def test_web_search_tool_caches_results(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    html = """
    <div class="result">
      <a class="result__a" href="https://example.com/one">Example One</a>
      <div class="result__snippet">First snippet</div>
    </div>
    <div class="result">
      <a class="result__a" href="https://example.com/two">Example Two</a>
      <div class="result__snippet">Second snippet</div>
    </div>
    """
    request_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal request_count
        request_count += 1
        return httpx.Response(
            200,
            text=html,
            headers={"content-type": "text/html"},
            request=request,
        )

    monkeypatch.setenv("ATLAS_WEAVE_DATA_DIR", str(tmp_path))
    http_tool = HttpTool(
        client_factory=lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler))
    )
    search_tool = WebSearchTool(http_tool=http_tool)
    ctx, stream = make_context()

    first = await search_tool.call(ctx, query="example query", max_results=2)
    second = await search_tool.call(ctx, query="example query", max_results=2)
    events = read_events(stream)
    search_results = [event for event in events if event.get("tool") == "web_search" and event["type"] == "tool_result"]

    assert request_count == 1
    assert len(first["results"]) == 2
    assert second == first
    assert search_results[0]["cache_hit"] is False
    assert search_results[1]["cache_hit"] is True


@pytest.mark.anyio
async def test_web_scrape_tool_extracts_title_and_text() -> None:
    html = """
    <html>
      <head><title>Example Page</title></head>
      <body>
        <main>Hello <strong>world</strong>.</main>
        <a href="https://example.com/more">More</a>
      </body>
    </html>
    """

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            text=html,
            headers={"content-type": "text/html"},
            request=request,
        )

    scrape_tool = WebScrapeTool(
        http_tool=HttpTool(
            client_factory=lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler))
        )
    )
    ctx, _stream = make_context()

    result = await scrape_tool.call(ctx, url="https://example.com")

    assert result["title"] == "Example Page"
    assert "Hello world" in result["text"]
    assert result["link_count"] == 1


@pytest.mark.anyio
async def test_sqlite_tool_execute_fetch_and_upsert(tmp_path: Path) -> None:
    db_path = tmp_path / "recipe.db"
    tool = SQLiteTool()
    ctx, _stream = make_context()

    await tool.execute(
        ctx,
        db_path=str(db_path),
        sql="CREATE TABLE items (id INTEGER PRIMARY KEY, value TEXT NOT NULL)",
    )
    await tool.upsert(
        ctx,
        db_path=str(db_path),
        table="items",
        values={"id": 1, "value": "first"},
        key_columns=["id"],
    )
    await tool.upsert(
        ctx,
        db_path=str(db_path),
        table="items",
        values={"id": 1, "value": "updated"},
        key_columns=["id"],
    )
    rows = await tool.fetch_all(
        ctx,
        db_path=str(db_path),
        sql="SELECT id, value FROM items ORDER BY id",
    )

    assert rows == [{"id": 1, "value": "updated"}]


@pytest.mark.anyio
async def test_llm_tool_openrouter_emits_usage(monkeypatch: pytest.MonkeyPatch) -> None:
    response_payload = {
        "id": "openrouter-req",
        "model": "openai/gpt-4o-mini",
        "choices": [
            {
                "message": {
                    "content": json.dumps(
                        {
                            "headline": "Demo",
                            "summary": "Summarized",
                            "source_urls": ["https://example.com"],
                        }
                    )
                }
            }
        ],
        "usage": {
            "prompt_tokens": 120,
            "completion_tokens": 45,
            "cost": 0.0012,
        },
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=response_payload,
            headers={"content-type": "application/json"},
            request=request,
        )

    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    llm_tool = LLMTool(
        http_tool=HttpTool(
            client_factory=lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler))
        )
    )
    ctx, stream = make_context()

    result = await llm_tool.call(
        ctx,
        provider="openrouter",
        model="openrouter/auto",
        messages=[{"role": "user", "content": "Hello"}],
        json_schema={
            "type": "object",
            "properties": {"headline": {"type": "string"}},
            "required": ["headline"],
        },
    )
    events = read_events(stream)

    assert result["output"]["headline"] == "Demo"
    assert result["estimated_cost_usd"] == pytest.approx(0.0012)
    assert any(event["type"] == "llm_call" for event in events)
    assert any(event["type"] == "llm_result" and event["estimated_cost_usd"] == pytest.approx(0.0012) for event in events)


@pytest.mark.anyio
async def test_llm_tool_openrouter_accepts_content_parts(monkeypatch: pytest.MonkeyPatch) -> None:
    response_payload = {
        "id": "openrouter-req-2",
        "model": "openai/gpt-4o-mini",
        "choices": [
            {
                "message": {
                    "content": [
                        {
                            "type": "output_text",
                            "text": "```json\n{\"headline\":\"Demo\",\"summary\":\"From parts\",\"source_urls\":[\"https://example.com\"]}\n```",
                        }
                    ]
                }
            }
        ],
        "usage": {
            "prompt_tokens": 80,
            "completion_tokens": 30,
        },
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=response_payload,
            headers={"content-type": "application/json"},
            request=request,
        )

    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    llm_tool = LLMTool(
        http_tool=HttpTool(
            client_factory=lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler))
        )
    )
    ctx, _stream = make_context()

    result = await llm_tool.call(
        ctx,
        provider="openrouter",
        model="openrouter/auto",
        messages=[{"role": "user", "content": "Hello"}],
        json_schema={
            "type": "object",
            "properties": {"headline": {"type": "string"}},
            "required": ["headline"],
        },
    )

    assert result["output"]["headline"] == "Demo"
    assert result["output"]["summary"] == "From parts"


def test_test_tools_recipe_tolerates_llm_provider_parse_error(monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    async def fail_call(self: LLMTool, ctx: AgentContext, **_: Any) -> dict[str, Any]:
        raise ValueError("OpenRouter structured output was not valid JSON")

    from atlas_weave.agent import AgentResult
    monkeypatch.setattr(LLMTool, "has_credentials", lambda self, provider: True)
    monkeypatch.setattr(LLMTool, "call", fail_call)

    import recipes.test_tools.recipe as test_tools_recipe

    async def fake_http_execute(self: Any, ctx: AgentContext) -> AgentResult:
        payload = {"id": 1, "title": "demo"}
        ctx.state[self.name] = {"payload": payload}
        return AgentResult(records_processed=1, summary={"url": "https://example.com", "payload": payload})

    async def fake_search_execute(self: Any, ctx: AgentContext) -> AgentResult:
        results = [{"url": "https://example.com", "title": "Example"}]
        ctx.state[self.name] = {"query": "example domain", "results": results}
        return AgentResult(records_processed=1, summary={"query": "example domain", "results": results})

    async def fake_scrape_execute(self: Any, ctx: AgentContext) -> AgentResult:
        result = {"url": "https://example.com", "title": "Example", "text": "Example text"}
        ctx.state[self.name] = result
        return AgentResult(records_processed=1, summary=result)

    monkeypatch.setattr(
        test_tools_recipe.HttpAgent,
        "execute",
        fake_http_execute,
    )
    monkeypatch.setattr(
        test_tools_recipe.SearchAgent,
        "execute",
        fake_search_execute,
    )
    monkeypatch.setattr(
        test_tools_recipe.ScrapeAgent,
        "execute",
        fake_scrape_execute,
    )

    import asyncio

    asyncio.run(run_recipe("test_tools", "run-tools", {}))
    events = [json.loads(line) for line in capsys.readouterr().out.splitlines() if line]

    llm_completed = next(
        event for event in events if event["type"] == "node_completed" and event["node_id"] == "llm_agent"
    )
    assert llm_completed["summary"]["summary"]["skipped"] is True
    assert "llm_error" in llm_completed["summary"]["summary"]
    assert any(event["type"] == "run_completed" for event in events)


@pytest.mark.anyio
async def test_llm_tool_anthropic_uses_structured_output(monkeypatch: pytest.MonkeyPatch) -> None:
    response_payload = {
        "id": "anthropic-req",
        "model": "claude-3-5-haiku-latest",
        "content": [
            {
                "type": "tool_use",
                "name": "atlas_weave_output",
                "input": {
                    "headline": "Anthropic Demo",
                    "summary": "Structured",
                    "source_urls": ["https://example.com"],
                },
            }
        ],
        "usage": {
            "input_tokens": 100,
            "output_tokens": 50,
        },
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=response_payload,
            headers={"content-type": "application/json"},
            request=request,
        )

    monkeypatch.setenv("CLAUDE_API_KEY", "test-key")
    llm_tool = LLMTool(
        http_tool=HttpTool(
            client_factory=lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler))
        )
    )
    ctx, stream = make_context()

    result = await llm_tool.call(
        ctx,
        provider="anthropic",
        model="claude-3-5-haiku-latest",
        messages=[{"role": "user", "content": "Hello"}],
        json_schema={
            "type": "object",
            "properties": {"headline": {"type": "string"}},
            "required": ["headline"],
        },
    )
    events = read_events(stream)

    assert result["output"]["headline"] == "Anthropic Demo"
    assert result["estimated_cost_usd"] > 0
    assert any(event["type"] == "llm_result" and event["completion_tokens"] == 50 for event in events)
