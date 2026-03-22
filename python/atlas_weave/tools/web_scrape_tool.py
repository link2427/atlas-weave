from __future__ import annotations

from typing import Any

from bs4 import BeautifulSoup

from atlas_weave.context import AgentContext
from atlas_weave.tool import Tool, run_tool_operation
from atlas_weave.tools.http_tool import HttpTool


class WebScrapeTool(Tool):
    name = "web_scrape"
    description = "Fetch and normalize HTML content for downstream agents."

    def __init__(self, http_tool: HttpTool) -> None:
        self.http_tool = http_tool

    async def call(
        self,
        ctx: AgentContext,
        *,
        url: str,
        max_chars: int = 4000,
        max_links: int = 10,
    ) -> dict[str, Any]:
        node_id = ctx.node_id

        async def operation() -> dict[str, Any]:
            response = await self.http_tool.call(
                ctx,
                method="GET",
                url=url,
                headers={"User-Agent": "AtlasWeave/0.1"},
            )
            return _extract_page(url, response.text or "", max_chars, max_links)

        return await run_tool_operation(
            ctx=ctx,
            node_id=node_id,
            tool_name=self.name,
            input_payload={"url": url, "max_chars": max_chars, "max_links": max_links},
            operation=operation,
            serialize_result=lambda result: result,
        )


def _extract_page(
    url: str, html: str, max_chars: int, max_links: int
) -> dict[str, Any]:
    soup = BeautifulSoup(html, "html.parser")
    title = " ".join(
        (soup.title.get_text(" ", strip=True) if soup.title else "").split()
    )
    text = " ".join(soup.get_text(" ", strip=True).split())
    links = []

    for link in soup.select("a[href]"):
        href = link.get("href", "")
        if not href:
            continue
        links.append(
            {
                "href": href,
                "label": " ".join(link.get_text(" ", strip=True).split()),
            }
        )
        if len(links) >= max_links:
            break

    return {
        "url": url,
        "title": title,
        "text": text[:max_chars],
        "link_count": len(links),
        "links": links,
    }
