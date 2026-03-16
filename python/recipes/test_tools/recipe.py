from __future__ import annotations

from typing import Any

from atlas_weave import Agent, AgentContext, AgentResult, Recipe
from atlas_weave.tools.llm_tool import LLMTool


class HttpAgent(Agent):
    name = "http_agent"
    description = "Fetch a stable JSON payload over HTTP."
    outputs = ["http_payload"]

    async def execute(self, ctx: AgentContext) -> AgentResult:
        ctx.raise_if_cancelled()
        url = str(ctx.config.get("http_url", "https://jsonplaceholder.typicode.com/todos/1"))
        response = await ctx.tools.http.call(ctx, method="GET", url=url)
        payload = response.json_body or {"text_preview": response.text_preview}
        ctx.state[self.name] = {"payload": payload}
        ctx.emit.log(self.name, "info", f"Fetched demo HTTP payload from {url}")
        ctx.emit.progress(self.name, 1.0, "HTTP demo complete")
        return AgentResult(
            records_processed=1,
            summary={"url": url, "payload": payload},
        )


class SearchAgent(Agent):
    name = "search_agent"
    description = "Run a DuckDuckGo HTML search and capture the top results."
    outputs = ["search_results"]

    async def execute(self, ctx: AgentContext) -> AgentResult:
        ctx.raise_if_cancelled()
        query = str(ctx.config.get("search_query", "example domain"))
        result = await ctx.tools.web_search.call(ctx, query=query, max_results=3)
        ctx.state[self.name] = {"query": query, "results": result["results"]}
        ctx.emit.log(self.name, "info", f"Collected {len(result['results'])} search results")
        ctx.emit.progress(self.name, 1.0, "Search demo complete")
        return AgentResult(
            records_processed=len(result["results"]),
            summary={"query": query, "results": result["results"]},
        )


class ScrapeAgent(Agent):
    name = "scrape_agent"
    description = "Scrape a public page and normalize its visible text."
    outputs = ["scrape_result"]

    async def execute(self, ctx: AgentContext) -> AgentResult:
        ctx.raise_if_cancelled()
        url = str(ctx.config.get("scrape_url", "https://example.com"))
        result = await ctx.tools.web_scrape.call(ctx, url=url, max_chars=1500, max_links=6)
        ctx.state[self.name] = result
        ctx.emit.log(self.name, "info", f"Scraped {result['title'] or url}")
        ctx.emit.progress(self.name, 1.0, "Scrape demo complete")
        return AgentResult(
            records_processed=1,
            summary=result,
        )


class LlmAgent(Agent):
    name = "llm_agent"
    description = "Summarize upstream tool outputs through the configured LLM provider."
    inputs = ["http_payload", "search_results", "scrape_result"]

    async def execute(self, ctx: AgentContext) -> AgentResult:
        ctx.raise_if_cancelled()
        provider = str(ctx.config.get("llm_provider", "openrouter"))
        model = str(ctx.config.get("llm_model", "nvidia/nemotron-3-super-120b-a12b:free"))
        if provider == "openrouter" and model == "openrouter/auto":
            model = "nvidia/nemotron-3-super-120b-a12b:free"
        if provider == "anthropic" and model in {
            "openrouter/auto",
            "nvidia/nemotron-3-super-120b-a12b:free",
        }:
            model = "claude-3-5-haiku-latest"

        llm_tool = ctx.tools.llm
        if isinstance(llm_tool, LLMTool) and not llm_tool.has_credentials(provider):
            message = f"Skipped live LLM demo because {provider} credentials are not configured."
            ctx.emit.log(self.name, "warning", message)
            ctx.emit.progress(self.name, 1.0, "LLM demo skipped")
            return AgentResult(
                summary={
                    "provider": provider,
                    "model": model,
                    "skipped": True,
                    "reason": message,
                }
            )

        http_payload = ctx.state["http_agent"]["payload"]
        search_results = ctx.state["search_agent"]["results"]
        scrape_result = ctx.state["scrape_agent"]
        try:
            llm_result = await llm_tool.call(
                ctx,
                provider=provider,
                model=model,
                system="You are Atlas Weave's tool-observability demo model.",
                messages=[
                    {
                        "role": "user",
                        "content": (
                            "Summarize these tool outputs for an operator.\n"
                            "Return concise factual JSON only.\n"
                            f"HTTP payload: {http_payload}\n"
                            f"Search results: {search_results}\n"
                            f"Scraped page: {scrape_result}"
                        ),
                    }
                ],
                json_schema={
                    "type": "object",
                    "properties": {
                        "headline": {"type": "string"},
                        "summary": {"type": "string"},
                        "source_urls": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                    },
                    "required": ["headline", "summary", "source_urls"],
                    "additionalProperties": False,
                },
                max_tokens=500,
                temperature=0.1,
            )
        except Exception as error:  # noqa: BLE001
            message = f"LLM demo completed with a provider error: {error}"
            ctx.emit.log(self.name, "warning", message)
            ctx.emit.progress(self.name, 1.0, "LLM demo recorded an error")
            return AgentResult(
                summary={
                    "provider": provider,
                    "model": model,
                    "llm_error": str(error),
                    "skipped": True,
                    "reason": "Structured LLM output was not usable for the demo run.",
                }
            )

        ctx.state[self.name] = {"llm": llm_result}
        ctx.emit.log(self.name, "info", f"LLM summary complete via {provider}")
        ctx.emit.progress(self.name, 1.0, "LLM demo complete")
        return AgentResult(
            records_processed=1,
            summary={
                "provider": provider,
                "model": model,
                "output": llm_result["output"],
                "prompt_tokens": llm_result["prompt_tokens"],
                "completion_tokens": llm_result["completion_tokens"],
                "estimated_cost_usd": llm_result["estimated_cost_usd"],
            },
        )


class TestToolsRecipe(Recipe):
    name = "test_tools"
    description = "Built-in tool and multi-provider LLM demo recipe."
    version = "0.1.0"
    agents = [HttpAgent, SearchAgent, ScrapeAgent, LlmAgent]
    edges = [
        ("http_agent", "llm_agent"),
        ("search_agent", "llm_agent"),
        ("scrape_agent", "llm_agent"),
    ]
    config_schema: dict[str, Any] = {
        "http_url": {
            "type": "string",
            "default": "https://jsonplaceholder.typicode.com/todos/1",
            "description": "Public JSON endpoint used by the HTTP tool demo.",
        },
        "search_query": {
            "type": "string",
            "default": "example domain",
            "description": "DuckDuckGo HTML query used by the search tool demo.",
        },
        "scrape_url": {
            "type": "string",
            "default": "https://example.com",
            "description": "Public page used by the scrape tool demo.",
        },
        "llm_provider": {
            "type": "string",
            "default": "openrouter",
            "enum": ["openrouter", "anthropic"],
            "description": "Provider used for the live LLM demo call.",
        },
        "llm_model": {
            "type": "string",
            "default": "nvidia/nemotron-3-super-120b-a12b:free",
            "description": "Model slug for the selected provider.",
        },
        "openrouter_api_key": {
            "type": "string",
            "required": False,
            "secret": True,
            "description": "OpenRouter API key used when llm_provider is openrouter.",
        },
        "claude_api_key": {
            "type": "string",
            "required": False,
            "secret": True,
            "description": "Anthropic API key used when llm_provider is anthropic.",
        },
    }


RECIPE = TestToolsRecipe()
