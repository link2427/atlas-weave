from __future__ import annotations

from typing import Any

from atlas_weave import Recipe
from recipes.satellite_enrichment.agents.auditor import QualityAuditor
from recipes.satellite_enrichment.agents.collector import StructuredDataCollector
from recipes.satellite_enrichment.agents.merger import RecordMerger
from recipes.satellite_enrichment.agents.researcher import ResearchSwarm


class SatelliteEnrichmentRecipe(Recipe):
    name = "satellite_enrichment"
    description = "Cosmotrak satellite enrichment pipeline with staged source collection, merge, a runtime research swarm, and audit."
    version = "0.2.0"
    agents = [StructuredDataCollector, RecordMerger, ResearchSwarm, QualityAuditor]
    edges = [
        ("structured_data_collector", "record_merger"),
        ("record_merger", "research_swarm"),
        ("research_swarm", "quality_auditor"),
    ]
    config_schema: dict[str, Any] = {
        "space_track_mode": {
            "type": "string",
            "default": "prefer_cache",
            "enum": ["disabled", "prefer_cache", "live"],
            "description": "Use cached Space-Track snapshots by default and only hit the live API when explicitly enabled.",
        },
        "space_track_identity": {
            "type": "string",
            "required": False,
            "secret": True,
            "description": "Optional Space-Track account identity. Only required when space_track_mode is live.",
        },
        "space_track_password": {
            "type": "string",
            "required": False,
            "secret": True,
            "description": "Optional Space-Track password. Only required when space_track_mode is live.",
        },
        "discos_api_token": {
            "type": "string",
            "required": False,
            "secret": True,
            "description": "Optional ESA DISCOS bearer token used for richer object metadata access.",
        },
        "ucs_catalog_csv_url": {
            "type": "string",
            "default": "",
            "description": "Optional UCS catalog CSV URL used when a local file path is not provided.",
        },
        "ucs_catalog_csv_path": {
            "type": "string",
            "default": "",
            "description": "Optional local UCS catalog CSV path. Takes precedence over the URL when set.",
        },
        "llm_provider": {
            "type": "string",
            "default": "openrouter",
            "enum": ["openrouter", "anthropic"],
            "description": "Provider used for selective low-completeness enrichment.",
        },
        "llm_model": {
            "type": "string",
            "default": "nvidia/nemotron-3-super-120b-a12b:free",
            "description": "Model slug for the selected LLM provider.",
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
        "enable_llm_research": {
            "type": "boolean",
            "default": True,
            "description": "Enable metadata-heavy LLM-backed enrichment for missing or conflicting fields.",
        },
        "refresh_sources": {
            "type": "boolean",
            "default": False,
            "description": "Bypass source cache TTLs and force live refresh for all available HTTP sources.",
        },
        "celestrak_cache_ttl_minutes": {
            "type": "number",
            "default": 60,
            "description": "How long recent CelesTrak snapshots should be reused before refreshing.",
        },
        "completeness_threshold": {
            "type": "number",
            "default": 0.5,
            "description": "Records below this completeness score are queued for research even if no direct conflicts are present.",
        },
        "llm_confidence_threshold": {
            "type": "number",
            "default": 0.7,
            "description": "Minimum model confidence required before LLM fields are accepted.",
        },
        "max_research_records": {
            "type": "number",
            "default": 500,
            "description": "Maximum number of metadata-heavy research candidates sent through LLM enrichment per run.",
        },
        "research_concurrency": {
            "type": "number",
            "default": 12,
            "description": "Maximum number of runtime research workers processed concurrently during the swarm phase.",
        },
        "llm_concurrency": {
            "type": "number",
            "default": 4,
            "description": "Maximum number of concurrent LLM extraction calls inside the research swarm.",
        },
        "record_limit": {
            "type": "number",
            "description": "Optional development-only cap on the number of merged records to process.",
        },
    }


RECIPE = SatelliteEnrichmentRecipe()
