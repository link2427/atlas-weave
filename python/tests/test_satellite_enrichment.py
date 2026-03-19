from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any

import pytest

from atlas_weave.runner import describe_recipe, run_recipe
from atlas_weave.tools.llm_tool import LLMTool
from atlas_weave.tools.web_scrape_tool import WebScrapeTool
from atlas_weave.tools.web_search_tool import WebSearchTool
from recipes.satellite_enrichment import db
from recipes.satellite_enrichment.schema import compute_completeness, derive_constellation_name, derive_orbit_class
from recipes.satellite_enrichment.sources import (
    SourceBundle,
    _load_snapshot,
    _parse_space_track_payload,
    _read_text_file_with_fallbacks,
    _write_snapshot,
)


def build_source_bundle() -> SourceBundle:
    return SourceBundle(
        space_track_satcat=[],
        space_track_gp=[],
        celestrak_satcat=[
            {
                "norad_id": 44713,
                "group_name": "starlink",
                "object_name": "STARLINK-1001",
                "international_designator": "2019-074A",
                "epoch_utc": "2026-03-16T00:00:00+00:00",
                "inclination_deg": 53.0,
                "eccentricity": 0.00012,
                "period_min": 95.4,
                "mean_motion_rev_per_day": 15.10,
                "semi_major_axis_km": 6923.2,
                "perigee_km": 540.0,
                "apogee_km": 552.0,
                "altitude_km": 546.0,
                "raan_deg": 255.6,
                "arg_perigee_deg": 84.2,
                "mean_anomaly_deg": 120.0,
                "tle_line1": "1 44713U 19074A   26076.00000000  .00000123  00000-0  56789-5 0  9998",
                "tle_line2": "2 44713  53.0000 255.6000 0001200  84.2000 120.0000 15.10000000000000",
            },
            {
                "norad_id": 25544,
                "group_name": "stations",
                "object_name": "ISS (ZARYA)",
                "international_designator": "1998-067A",
                "epoch_utc": "2026-03-16T00:00:00+00:00",
                "inclination_deg": 51.64,
                "eccentricity": 0.00041,
                "period_min": 92.7,
                "mean_motion_rev_per_day": 15.55,
                "semi_major_axis_km": 6797.1,
                "perigee_km": 417.0,
                "apogee_km": 423.0,
                "altitude_km": 420.0,
                "raan_deg": 130.4,
                "arg_perigee_deg": 72.3,
                "mean_anomaly_deg": 281.2,
                "tle_line1": "1 25544U 98067A   26076.00000000  .00001234  00000-0  23456-4 0  9993",
                "tle_line2": "2 25544  51.6400 130.4000 0004100  72.3000 281.2000 15.55000000000000",
            },
        ],
        discos=[
            {
                "norad_id": 25544,
                "international_designator": "1998-067A",
                "object_name": "ISS (ZARYA)",
                "operator_name": "NASA",
                "operator_country_code": "US",
                "operator_country_name": "United States",
                "owner_name": "NASA",
                "owner_country_code": "US",
                "owner_country_name": "United States",
                "purpose_primary": "Human Spaceflight",
                "program_name": "ISS",
                "manufacturer_name": "Energia",
                "prime_contractor": "Energia",
                "bus_platform": "ISS",
                "dry_mass_kg": 419725.0,
                "launch_mass_kg": 419725.0,
                "dimensions_text": "109m x 73m",
                "design_life_years": 15.0,
                "launch_provider": "Roscosmos",
                "launch_vehicle": "PROTON-K",
                "civilian_military": "civil",
            }
        ],
        ucs=[
            {
                "norad_id": 44713,
                "international_designator": "2019-074A",
                "object_name": "STARLINK-1001",
                "operator_name": "",
                "operator_country_code": "US",
                "operator_country_name": "United States",
                "owner_name": "",
                "purpose_primary": "",
                "mission_class": "Low Earth Orbit",
                "launch_date": "2019-11-11",
                "launch_vehicle": "FALCON 9",
                "launch_provider": "Cape Canaveral",
                "dry_mass_kg": None,
                "launch_mass_kg": None,
                "expected_life_years": 5.0,
            }
        ],
        source_status={"space_track": "disabled", "celestrak": "cached", "discos": "live", "ucs": "file"},
        cached_sources=["celestrak"],
        stale_sources=[],
        source_snapshots=[
            {
                "source_key": "celestrak",
                "status": "cached",
                "cache_state": "fresh",
                "record_count": 2,
                "source_url": "https://celestrak.org/NORAD/elements/gp.php",
                "cache_path": "/tmp/celestrak.json",
                "fetched_at": "2026-03-16T00:00:00+00:00",
                "expires_at": "2026-03-16T01:00:00+00:00",
            }
        ],
    )


def test_describe_recipe_reports_satellite_enrichment_metadata() -> None:
    metadata = describe_recipe("satellite_enrichment")

    assert metadata["name"] == "satellite_enrichment"
    assert metadata["config_schema"]["space_track_identity"]["secret"] is True
    assert metadata["config_schema"]["space_track_identity"]["required"] is False
    assert metadata["config_schema"]["space_track_mode"]["default"] == "prefer_cache"
    assert len(metadata["dag"]["nodes"]) == 4


def test_schema_derivations_cover_orbit_and_constellation() -> None:
    assert derive_orbit_class(550.0) == "LEO"
    assert derive_orbit_class(20000.0) == "MEO"
    assert derive_orbit_class(35786.0) == "GEO"
    assert derive_constellation_name("STARLINK-1001", []) == "Starlink"
    assert compute_completeness({"object_name": "Demo", "object_type": "PAYLOAD"}) > 0


def test_read_text_file_with_fallbacks_accepts_cp1252_bytes(tmp_path: Path) -> None:
    csv_path = tmp_path / "ucs.csv"
    csv_path.write_bytes("NORAD Number,Operator/Owner\n25544,ACME\xa0Space\n".encode("cp1252"))

    text = _read_text_file_with_fallbacks(str(csv_path))

    assert "ACME" in text
    assert "25544" in text


def test_parse_space_track_payload_rejects_error_objects() -> None:
    with pytest.raises(ValueError, match="query rate limit"):
        _parse_space_track_payload(
            [
                {
                    "error": "You've violated your query rate limit. Please refer to our Acceptable Use guidelines.",
                }
            ],
            "SATCAT",
        )


def test_source_snapshot_round_trip_uses_cache_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("ATLAS_WEAVE_DATA_DIR", str(tmp_path))

    snapshot = _write_snapshot(
        "celestrak",
        {"rows": [{"norad_id": 25544}]},
        ttl_minutes=60,
        source_url="https://celestrak.org/NORAD/elements/gp.php",
        record_count=1,
    )
    loaded = _load_snapshot("celestrak", 60)

    assert snapshot["cache_path"].startswith(str(db.cache_dir()))
    assert loaded is not None
    assert loaded["payload"]["rows"][0]["norad_id"] == 25544


def test_recipe_run_creates_output_db_and_latest_manifest(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    async def fake_fetch_source_bundle(_: Any) -> SourceBundle:
        return build_source_bundle()

    async def fake_search(self: WebSearchTool, ctx: Any, *, query: str, max_results: int = 4) -> dict[str, Any]:
        return {
            "query": query,
            "results": [
                {
                    "title": "Starlink Specs",
                    "url": "https://example.com/starlink",
                    "snippet": "Starlink by SpaceX communications constellation.",
                }
            ][:max_results],
        }

    async def fake_scrape(self: WebScrapeTool, ctx: Any, *, url: str, max_chars: int = 2000, max_links: int = 6) -> dict[str, Any]:
        return {
            "url": url,
            "title": "Example Starlink",
            "text": "SpaceX operates the Starlink communications constellation. Each satellite has a dry mass near 260 kg.",
            "links": [],
            "link_count": 0,
        }

    async def fake_llm(self: LLMTool, ctx: Any, **_: Any) -> dict[str, Any]:
        return {
            "provider_request_id": "req-1",
            "provider_model": "nvidia/nemotron-3-super-120b-a12b:free",
            "output": {
                "confidence": 0.93,
                "fields": {
                    "operator_name": "SpaceX",
                    "owner_name": "SpaceX",
                    "purpose_primary": "Communications",
                    "manufacturer_name": "SpaceX",
                    "dry_mass_kg": 260.0,
                    "constellation_name": "Starlink",
                },
                "evidence_urls": ["https://example.com/starlink"],
            },
            "prompt_tokens": 500,
            "completion_tokens": 150,
            "estimated_cost_usd": 0.0,
        }

    monkeypatch.setenv("ATLAS_WEAVE_DATA_DIR", str(tmp_path))
    monkeypatch.setattr("recipes.satellite_enrichment.agents.collector.fetch_source_bundle", fake_fetch_source_bundle)
    monkeypatch.setattr(WebSearchTool, "call", fake_search)
    monkeypatch.setattr(WebScrapeTool, "call", fake_scrape)
    monkeypatch.setattr(LLMTool, "has_credentials", lambda self, provider: True)
    monkeypatch.setattr(LLMTool, "call", fake_llm)

    asyncio.run(
        run_recipe(
            "satellite_enrichment",
            "sat-run-1",
            {
                "enable_llm_research": True,
                "llm_provider": "openrouter",
                "llm_model": "nvidia/nemotron-3-super-120b-a12b:free",
            },
        )
    )
    events = [json.loads(line) for line in capsys.readouterr().out.splitlines() if line]
    run_completed = next(event for event in events if event["type"] == "run_completed")
    swarm_completed = next(
        event for event in events if event["type"] == "node_completed" and event["node_id"] == "research_swarm"
    )
    graph_patch = next(event for event in events if event["type"] == "graph_patch")

    output_db = db.run_db_path("sat-run-1")
    latest_db = db.latest_db_path()
    satellites = db.fetch_satellites(output_db)

    assert output_db.exists()
    assert latest_db.exists()
    assert len(satellites) == 2
    assert any(sat["operator_name"] == "SpaceX" for sat in satellites)
    assert run_completed["summary"]["output_db_path"] == str(output_db)
    assert run_completed["summary"]["latest_db_path"] == str(latest_db)
    assert run_completed["summary"]["accepted_llm_records"] == 2
    assert run_completed["summary"]["cached_sources"] == ["celestrak"]
    assert run_completed["summary"]["space_track_mode"] == "prefer_cache"
    assert run_completed["summary"]["coverage_operator_purpose_pct"] == pytest.approx(100.0)
    assert swarm_completed["summary"]["summary"]["started_workers"] == 2
    assert swarm_completed["summary"]["summary"]["accepted_llm_records"] == 2
    assert any(node["id"].startswith("research_category_") for node in graph_patch["nodes"])
    assert any(edge[0] == "research_swarm" for edge in graph_patch["edges"])


def test_recipe_run_skips_research_when_disabled(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    async def fake_fetch_source_bundle(_: Any) -> SourceBundle:
        return build_source_bundle()

    monkeypatch.setenv("ATLAS_WEAVE_DATA_DIR", str(tmp_path))
    monkeypatch.setattr("recipes.satellite_enrichment.agents.collector.fetch_source_bundle", fake_fetch_source_bundle)

    asyncio.run(run_recipe("satellite_enrichment", "sat-run-no-llm", {"enable_llm_research": False}))
    events = [json.loads(line) for line in capsys.readouterr().out.splitlines() if line]

    swarm_node_completed = next(
        event for event in events if event["type"] == "node_completed" and event["node_id"] == "research_swarm"
    )
    assert swarm_node_completed["summary"]["summary"]["skipped"] is True

    satellites = db.fetch_satellites(db.run_db_path("sat-run-no-llm"))
    assert any(sat["operator_name"] in {None, ""} for sat in satellites if sat["norad_id"] == 44713)


def test_recipe_run_skips_research_when_credentials_are_missing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    async def fake_fetch_source_bundle(_: Any) -> SourceBundle:
        return build_source_bundle()

    monkeypatch.setenv("ATLAS_WEAVE_DATA_DIR", str(tmp_path))
    monkeypatch.setattr("recipes.satellite_enrichment.agents.collector.fetch_source_bundle", fake_fetch_source_bundle)
    monkeypatch.setattr(LLMTool, "has_credentials", lambda self, provider: False)

    asyncio.run(run_recipe("satellite_enrichment", "sat-run-missing-creds", {"enable_llm_research": True}))
    events = [json.loads(line) for line in capsys.readouterr().out.splitlines() if line]

    swarm_node_completed = next(
        event for event in events if event["type"] == "node_completed" and event["node_id"] == "research_swarm"
    )
    run_completed = next(event for event in events if event["type"] == "run_completed")
    assert swarm_node_completed["summary"]["summary"]["skipped"] is True
    assert run_completed["summary"]["llm_research_status"] == "skipped_missing_credentials"


def test_recipe_run_tolerates_llm_parse_errors(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    async def fake_fetch_source_bundle(_: Any) -> SourceBundle:
        return build_source_bundle()

    async def fake_search(self: WebSearchTool, ctx: Any, *, query: str, max_results: int = 4) -> dict[str, Any]:
        return {
            "query": query,
            "results": [
                {
                    "title": "Starlink Specs",
                    "url": "https://example.com/starlink",
                    "snippet": "Starlink by SpaceX communications constellation.",
                }
            ][:max_results],
        }

    async def fake_scrape(self: WebScrapeTool, ctx: Any, *, url: str, max_chars: int = 2000, max_links: int = 6) -> dict[str, Any]:
        return {
            "url": url,
            "title": "Example Starlink",
            "text": "SpaceX operates the Starlink communications constellation.",
            "links": [],
            "link_count": 0,
        }

    async def fail_llm(self: LLMTool, ctx: Any, **_: Any) -> dict[str, Any]:
        raise ValueError('OpenRouter structured output was not valid JSON: { "confidence":0')

    monkeypatch.setenv("ATLAS_WEAVE_DATA_DIR", str(tmp_path))
    monkeypatch.setattr("recipes.satellite_enrichment.agents.collector.fetch_source_bundle", fake_fetch_source_bundle)
    monkeypatch.setattr(WebSearchTool, "call", fake_search)
    monkeypatch.setattr(WebScrapeTool, "call", fake_scrape)
    monkeypatch.setattr(LLMTool, "has_credentials", lambda self, provider: True)
    monkeypatch.setattr(LLMTool, "call", fail_llm)

    asyncio.run(run_recipe("satellite_enrichment", "sat-run-parse-error", {"enable_llm_research": True}))
    events = [json.loads(line) for line in capsys.readouterr().out.splitlines() if line]

    swarm_completed = next(
        event for event in events if event["type"] == "node_completed" and event["node_id"] == "research_swarm"
    )
    run_completed = next(event for event in events if event["type"] == "run_completed")
    assert swarm_completed["summary"]["errors"] > 0
    assert swarm_completed["summary"]["summary"]["failed_workers"] > 0
    assert run_completed["summary"]["llm_research_status"] == "completed_with_errors"


@pytest.mark.external
def test_celestrak_smoke_fetch_stations_group() -> None:
    """Fetch a single CelesTrak group and verify the response is usable."""
    import httpx

    from recipes.satellite_enrichment.sources import normalize_celestrak_row

    url = "https://celestrak.org/NORAD/elements/gp.php?GROUP=stations&FORMAT=json"
    response = httpx.get(url, headers={"User-Agent": "AtlasWeave/0.1"}, timeout=45.0, follow_redirects=True)
    response.raise_for_status()

    body = response.json()
    assert isinstance(body, list), f"Expected list, got {type(body).__name__}"
    assert len(body) > 0, "Expected non-empty list from CelesTrak stations group"

    first = body[0]
    assert "NORAD_CAT_ID" in first, f"Missing NORAD_CAT_ID in record keys: {list(first.keys())[:10]}"

    normalized = normalize_celestrak_row(first, "stations")
    assert normalized["norad_id"] is not None
    assert normalized.get("group_name") == "stations"


@pytest.mark.external
def test_satellite_enrichment_external_live_run(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    required = [
        "DISCOS_API_TOKEN",
    ]
    missing = [name for name in required if not os.getenv(name)]
    if missing:
        pytest.skip(f"missing live satellite enrichment credentials: {', '.join(missing)}")

    monkeypatch.setenv("ATLAS_WEAVE_DATA_DIR", str(tmp_path))
    asyncio.run(
        run_recipe(
            "satellite_enrichment",
            "sat-live",
            {
                "enable_llm_research": False,
                "record_limit": 100,
                "ucs_catalog_csv_url": os.getenv("UCS_CATALOG_CSV_URL", ""),
                "space_track_mode": "disabled",
            },
        )
    )

    satellites = db.fetch_satellites(db.run_db_path("sat-live"))
    assert len(satellites) >= 100
