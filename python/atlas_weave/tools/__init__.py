from __future__ import annotations

from atlas_weave.tool import ToolRegistry

from atlas_weave.tools.http_tool import HttpTool
from atlas_weave.tools.llm_tool import LLMTool
from atlas_weave.tools.sqlite_tool import SQLiteTool
from atlas_weave.tools.web_scrape_tool import WebScrapeTool
from atlas_weave.tools.web_search_tool import WebSearchTool


def register_builtin_tools(registry: ToolRegistry | None = None) -> ToolRegistry:
    tool_registry = registry or ToolRegistry()
    http_tool = HttpTool()
    tool_registry.register(http_tool)
    tool_registry.register(WebSearchTool(http_tool=http_tool))
    tool_registry.register(WebScrapeTool(http_tool=http_tool))
    tool_registry.register(SQLiteTool())
    tool_registry.register(LLMTool(http_tool=http_tool))
    return tool_registry


__all__ = [
    "HttpTool",
    "LLMTool",
    "SQLiteTool",
    "WebScrapeTool",
    "WebSearchTool",
    "register_builtin_tools",
]
