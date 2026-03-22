from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from bs4 import BeautifulSoup

from atlas_weave.context import AgentContext
from atlas_weave.runtime import data_dir
from atlas_weave.tool import Tool, run_tool_operation
from atlas_weave.tools.http_tool import HttpTool

CACHE_TTL = timedelta(days=7)


@dataclass(slots=True)
class SearchResult:
    title: str
    url: str
    snippet: str


class WebSearchTool(Tool):
    name = "web_search"
    description = (
        "Run a cached provider-fallback web search that never hard-fails the caller."
    )

    def __init__(self, http_tool: HttpTool) -> None:
        self.http_tool = http_tool

    async def call(
        self,
        ctx: AgentContext,
        *,
        query: str,
        max_results: int = 5,
    ) -> dict[str, Any]:
        node_id = ctx.node_id
        input_payload = {"query": query, "max_results": max_results}
        cache_key = _cache_key(query, max_results)
        cached = _load_cache(cache_key)

        if cached is not None:
            return await run_tool_operation(
                ctx=ctx,
                node_id=node_id,
                tool_name=self.name,
                input_payload=input_payload,
                operation=lambda: _return_value(cached),
                serialize_result=_search_result_payload,
                cache_hit=True,
            )

        async def operation() -> dict[str, Any]:
            provider_attempts: list[dict[str, Any]] = []
            failures: list[dict[str, str]] = []
            results: list[dict[str, Any]] = []

            for provider in _provider_order(ctx):
                try:
                    provider_results = await _search_with_provider(
                        provider=provider,
                        http_tool=self.http_tool,
                        ctx=ctx,
                        query=query,
                        max_results=max_results,
                    )
                except Exception as error:  # noqa: BLE001
                    failures.append({"provider": provider, "error": str(error)})
                    provider_attempts.append(
                        {
                            "provider": provider,
                            "status": "error",
                            "result_count": 0,
                            "error": str(error),
                        }
                    )
                    continue

                provider_attempts.append(
                    {
                        "provider": provider,
                        "status": "ok" if provider_results else "empty",
                        "result_count": len(provider_results),
                    }
                )
                if provider_results:
                    results = provider_results[:max_results]
                    break

            payload = {
                "query": query,
                "results": results,
                "provider_attempts": provider_attempts,
                "failures": failures,
            }
            _write_cache(cache_key, payload)
            return payload

        return await run_tool_operation(
            ctx=ctx,
            node_id=node_id,
            tool_name=self.name,
            input_payload=input_payload,
            operation=operation,
            serialize_result=_search_result_payload,
            cache_hit=False,
        )


async def _return_value(value: dict[str, Any]) -> dict[str, Any]:
    return value


def _provider_order(ctx: AgentContext) -> list[str]:
    providers: list[str] = []
    if os.getenv("BRAVE_SEARCH_API_KEY"):
        providers.append("brave")
    searxng_base_url = str(ctx.config.get("searxng_base_url", "") or "").strip()
    if searxng_base_url:
        providers.append("searxng")
    providers.append("duckduckgo")
    return providers


async def _search_with_provider(
    *,
    provider: str,
    http_tool: HttpTool,
    ctx: AgentContext,
    query: str,
    max_results: int,
) -> list[dict[str, Any]]:
    if provider == "brave":
        response = await http_tool.call(
            ctx,
            method="GET",
            url="https://api.search.brave.com/res/v1/web/search",
            headers={
                "Accept": "application/json",
                "X-Subscription-Token": os.getenv("BRAVE_SEARCH_API_KEY", ""),
                "User-Agent": "AtlasWeave/0.1",
            },
            params={"q": query, "count": max_results},
        )
        payload = response.json_body or {}
        return _parse_brave_results(payload, max_results)

    if provider == "searxng":
        base_url = str(ctx.config.get("searxng_base_url", "") or "").rstrip("/")
        headers = {"Accept": "application/json", "User-Agent": "AtlasWeave/0.1"}
        api_key = os.getenv("SEARXNG_API_KEY")
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        response = await http_tool.call(
            ctx,
            method="GET",
            url=f"{base_url}/search",
            headers=headers,
            params={"q": query, "format": "json"},
        )
        payload = response.json_body or {}
        return _parse_searxng_results(payload, max_results)

    response = await http_tool.call(
        ctx,
        method="GET",
        url="https://html.duckduckgo.com/html/",
        params={"q": query},
        headers={"User-Agent": "AtlasWeave/0.1"},
    )
    return [
        {"title": result.title, "url": result.url, "snippet": result.snippet}
        for result in _parse_duckduckgo_results(response.text or "", max_results)
    ]


def _parse_brave_results(
    payload: dict[str, Any], max_results: int
) -> list[dict[str, Any]]:
    web = payload.get("web")
    rows = web.get("results") if isinstance(web, dict) else []
    results: list[dict[str, Any]] = []
    if not isinstance(rows, list):
        return results
    for row in rows[:max_results]:
        if not isinstance(row, dict):
            continue
        url = row.get("url")
        title = row.get("title")
        if not isinstance(url, str) or not isinstance(title, str):
            continue
        results.append(
            {
                "title": title.strip(),
                "url": url.strip(),
                "snippet": str(row.get("description") or "").strip(),
            }
        )
    return results


def _parse_searxng_results(
    payload: dict[str, Any], max_results: int
) -> list[dict[str, Any]]:
    rows = payload.get("results")
    results: list[dict[str, Any]] = []
    if not isinstance(rows, list):
        return results
    for row in rows[:max_results]:
        if not isinstance(row, dict):
            continue
        url = row.get("url")
        title = row.get("title")
        if not isinstance(url, str) or not isinstance(title, str):
            continue
        results.append(
            {
                "title": title.strip(),
                "url": url.strip(),
                "snippet": str(row.get("content") or row.get("snippet") or "").strip(),
            }
        )
    return results


def _parse_duckduckgo_results(html: str, max_results: int) -> list[SearchResult]:
    soup = BeautifulSoup(html, "html.parser")
    results: list[SearchResult] = []

    for container in soup.select(".result, .result--web, .web-result"):
        link = container.select_one(".result__a, .result__title a, a")
        if link is None:
            continue
        snippet = container.select_one(
            ".result__snippet, .result__body, .result-snippet"
        )
        results.append(
            SearchResult(
                title=" ".join(link.get_text(" ", strip=True).split()),
                url=link.get("href", ""),
                snippet=" ".join(
                    (snippet.get_text(" ", strip=True) if snippet else "").split()
                ),
            )
        )
        if len(results) >= max_results:
            break

    return results


def _search_result_payload(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "query": result["query"],
        "result_count": len(result["results"]),
        "results": result["results"],
        "provider_attempts": result.get("provider_attempts", []),
        "failures": result.get("failures", []),
    }


def _cache_db_path() -> str:
    return str(data_dir().joinpath("tool-cache.db"))


def _ensure_cache(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS web_search_cache (
            cache_key TEXT PRIMARY KEY,
            payload_json TEXT NOT NULL,
            fetched_at TEXT NOT NULL
        )
        """
    )


def _load_cache(cache_key: str) -> dict[str, Any] | None:
    with sqlite3.connect(_cache_db_path()) as conn:
        _ensure_cache(conn)
        row = conn.execute(
            "SELECT payload_json, fetched_at FROM web_search_cache WHERE cache_key = ?",
            (cache_key,),
        ).fetchone()

    if row is None:
        return None

    fetched_at = datetime.fromisoformat(row[1])
    if datetime.now(UTC) - fetched_at > CACHE_TTL:
        with sqlite3.connect(_cache_db_path()) as conn:
            _ensure_cache(conn)
            conn.execute(
                "DELETE FROM web_search_cache WHERE cache_key = ?", (cache_key,)
            )
            conn.commit()
        return None

    return json.loads(row[0])


def _write_cache(cache_key: str, payload: dict[str, Any]) -> None:
    with sqlite3.connect(_cache_db_path()) as conn:
        _ensure_cache(conn)
        conn.execute(
            """
            INSERT INTO web_search_cache (cache_key, payload_json, fetched_at)
            VALUES (?, ?, ?)
            ON CONFLICT(cache_key) DO UPDATE SET
                payload_json = excluded.payload_json,
                fetched_at = excluded.fetched_at
            """,
            (cache_key, json.dumps(payload), datetime.now(UTC).isoformat()),
        )
        conn.commit()


def _cache_key(query: str, max_results: int) -> str:
    return hashlib.sha256(f"{query}:{max_results}".encode("utf-8")).hexdigest()
