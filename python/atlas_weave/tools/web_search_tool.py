from __future__ import annotations

import hashlib
import json
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
    description = "Run a DuckDuckGo HTML search with a local 7-day cache."

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
            response = await self.http_tool.call(
                ctx,
                method="GET",
                url="https://html.duckduckgo.com/html/",
                params={"q": query},
                headers={"User-Agent": "AtlasWeave/0.1"},
            )
            results = _parse_results(response.text or "", max_results)
            payload = {
                "query": query,
                "results": [
                    {
                        "title": result.title,
                        "url": result.url,
                        "snippet": result.snippet,
                    }
                    for result in results
                ],
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


def _parse_results(html: str, max_results: int) -> list[SearchResult]:
    soup = BeautifulSoup(html, "html.parser")
    results: list[SearchResult] = []

    for container in soup.select(".result, .result--web, .web-result"):
        link = container.select_one(".result__a, .result__title a, a")
        if link is None:
            continue
        snippet = container.select_one(".result__snippet, .result__body, .result-snippet")
        results.append(
            SearchResult(
                title=" ".join(link.get_text(" ", strip=True).split()),
                url=link.get("href", ""),
                snippet=" ".join((snippet.get_text(" ", strip=True) if snippet else "").split()),
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
            conn.execute("DELETE FROM web_search_cache WHERE cache_key = ?", (cache_key,))
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
