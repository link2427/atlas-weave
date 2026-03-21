from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any

import pytest

from atlas_weave.runner import describe_recipe, run_recipe
from atlas_weave.tools.http_tool import HttpTool, HttpToolResponse
from atlas_weave.tools.llm_tool import LLMTool
from atlas_weave.tools.web_scrape_tool import WebScrapeTool
from atlas_weave.tools.web_search_tool import WebSearchTool
from recipes.satellite_enrichment import db
from recipes.satellite_enrichment.research_sources import (
    _build_wikipedia_titles,
    _parse_wikipedia_infobox,
)
from recipes.satellite_enrichment.constellation_templates import CONSTELLATION_TEMPLATES
from recipes.satellite_enrichment.schema import compute_completeness, derive_constellation_name, derive_orbit_class
from recipes.satellite_enrichment.sources import (
    SourceBundle,
    _load_snapshot,
    _parse_space_track_payload,
    _read_text_file_with_fallbacks,
    _write_snapshot,
    normalize_space_track_satcat_row,
    normalize_ucs_row,
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

    async def fake_http(self: HttpTool, ctx: Any, *, method: str, url: str, **kwargs: Any) -> HttpToolResponse:
        """Mock HTTP tool that handles Wikipedia API calls."""
        params = kwargs.get("params") or {}
        if "wikipedia.org" in url and params.get("list") == "search":
            return HttpToolResponse(
                method="GET", url=url, final_url=url, status_code=200,
                headers={}, content_type="application/json", body_bytes=200,
                text=None, text_preview="",
                json_body={
                    "query": {
                        "search": [{"title": "Starlink", "snippet": "SpaceX satellite constellation"}]
                    }
                },
            )
        if "wikipedia.org" in url and params.get("prop") == "revisions":
            wikitext = (
                "{{Infobox spacecraft\n"
                "| operator = [[SpaceX]]\n"
                "| manufacturer = [[SpaceX]]\n"
                "| mission_type = Communications\n"
                "| spacecraft_bus = Bus-1\n"
                "| launch_mass = {{convert|260|kg}}\n"
                "| design_life = 5 years\n"
                "}}\n"
                "'''Starlink''' is a satellite internet constellation operated by SpaceX."
            )
            return HttpToolResponse(
                method="GET", url=url, final_url=url, status_code=200,
                headers={}, content_type="application/json", body_bytes=500,
                text=None, text_preview="",
                json_body={
                    "query": {
                        "pages": {
                            "12345": {
                                "title": "Starlink",
                                "revisions": [{"slots": {"main": {"*": wikitext}}}],
                            }
                        }
                    }
                },
            )
        return HttpToolResponse(
            method="GET", url=url, final_url=url, status_code=404,
            headers={}, content_type="text/html", body_bytes=0,
            text="Not found", text_preview="Not found", json_body=None,
        )

    async def fake_scrape(self: WebScrapeTool, ctx: Any, *, url: str, max_chars: int = 2000, max_links: int = 6) -> dict[str, Any]:
        if "n2yo.com" in url:
            return {
                "url": url, "title": "N2YO Satellite", "links": [], "link_count": 0,
                "text": "Satellite details: operated by SpaceX for communications.",
            }
        if "skyrocket.de" in url:
            return {
                "url": url, "title": "Gunter's Space Page", "links": [], "link_count": 0,
                "text": "Starlink satellite specs: mass 260 kg, operator SpaceX, manufacturer SpaceX.",
            }
        return {
            "url": url, "title": "Example Starlink", "links": [], "link_count": 0,
            "text": "SpaceX operates the Starlink communications constellation. Each satellite has a dry mass near 260 kg.",
        }

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
    monkeypatch.setattr(HttpTool, "call", fake_http)
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
                "skip_research_constellations": [],
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
    assert run_completed["summary"]["accepted_llm_records"] >= 1
    assert run_completed["summary"]["cached_sources"] == ["celestrak"]
    assert run_completed["summary"]["space_track_mode"] == "prefer_cache"
    assert run_completed["summary"]["coverage_operator_purpose_pct"] == pytest.approx(100.0)
    assert swarm_completed["summary"]["summary"]["started_workers"] == 2
    assert swarm_completed["summary"]["summary"]["accepted_llm_records"] >= 1
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
    starlink = next((sat for sat in satellites if sat["norad_id"] == 44713), None)
    assert starlink is not None
    # Constellation template now fills operator_name for Starlink even without LLM
    assert starlink["operator_name"] == "SpaceX"


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

    async def fake_http_no_wiki(self: HttpTool, ctx: Any, *, method: str, url: str, **kwargs: Any) -> HttpToolResponse:
        """Return empty Wikipedia search results so no structured fields are found."""
        return HttpToolResponse(
            method="GET", url=url, final_url=url, status_code=200,
            headers={}, content_type="application/json", body_bytes=50,
            text=None, text_preview="",
            json_body={"query": {"search": []}},
        )

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
    monkeypatch.setattr(HttpTool, "call", fake_http_no_wiki)
    monkeypatch.setattr(WebSearchTool, "call", fake_search)
    monkeypatch.setattr(WebScrapeTool, "call", fake_scrape)
    monkeypatch.setattr(LLMTool, "has_credentials", lambda self, provider: True)
    monkeypatch.setattr(LLMTool, "call", fail_llm)

    asyncio.run(run_recipe("satellite_enrichment", "sat-run-parse-error", {
        "enable_llm_research": True,
        "skip_research_constellations": [],
    }))
    events = [json.loads(line) for line in capsys.readouterr().out.splitlines() if line]

    swarm_completed = next(
        event for event in events if event["type"] == "node_completed" and event["node_id"] == "research_swarm"
    )
    run_completed = next(event for event in events if event["type"] == "run_completed")
    assert swarm_completed["summary"]["errors"] > 0
    assert swarm_completed["summary"]["summary"]["failed_workers"] > 0
    assert run_completed["summary"]["llm_research_status"] == "completed_with_errors"


# ── Unit tests for research_sources ────────────────────────────────────────────


def test_parse_wikipedia_infobox_extracts_starlink_fields() -> None:
    wikitext = (
        "{{Infobox spacecraft\n"
        "| operator = [[SpaceX]]\n"
        "| manufacturer = [[SpaceX]]\n"
        "| mission_type = Communications\n"
        "| spacecraft_bus = Bus-1\n"
        "| launch_mass = {{convert|260|kg}}\n"
        "| design_life = 5 years\n"
        "}}\n"
    )
    fields = _parse_wikipedia_infobox(wikitext)
    assert fields["operator_name"] == "SpaceX"
    assert fields["manufacturer_name"] == "SpaceX"
    assert fields["purpose_primary"] == "Communications"
    assert fields["bus_platform"] == "Bus-1"
    assert fields["dry_mass_kg"] == 260.0
    assert fields["design_life_years"] == 5.0


def test_parse_wikipedia_infobox_handles_iss() -> None:
    wikitext = (
        "{{Infobox space station\n"
        "| operator = [[NASA]], [[Roscosmos]]\n"
        "| manufacturer = [[Boeing]]\n"
        "| mission_type = Human spaceflight\n"
        "| mass = 419,725 kg\n"
        "| design_life = 15 years\n"
        "}}\n"
    )
    fields = _parse_wikipedia_infobox(wikitext)
    assert "NASA" in fields.get("operator_name", "")
    assert fields.get("purpose_primary") == "Human spaceflight"
    assert fields.get("dry_mass_kg") == 419725.0
    assert fields.get("design_life_years") == 15.0


def test_parse_wikipedia_infobox_handles_gps_satellite() -> None:
    wikitext = (
        "{{Infobox spacecraft\n"
        "| operator = [[United States Space Force]]\n"
        "| manufacturer = [[Lockheed Martin]]\n"
        "| mission_type = Navigation\n"
        "| spacecraft_bus = A2100\n"
        "| launch_mass = 2,032 kg\n"
        "| design_life = 12 years\n"
        "}}\n"
    )
    fields = _parse_wikipedia_infobox(wikitext)
    assert fields["operator_name"] == "United States Space Force"
    assert fields["manufacturer_name"] == "Lockheed Martin"
    assert fields["purpose_primary"] == "Navigation"
    assert fields["bus_platform"] == "A2100"
    assert fields["dry_mass_kg"] == 2032.0
    assert fields["design_life_years"] == 12.0


def test_parse_wikipedia_infobox_returns_empty_for_no_infobox() -> None:
    wikitext = "This article has no infobox at all."
    fields = _parse_wikipedia_infobox(wikitext)
    assert fields == {}


def test_build_wikipedia_titles_starlink() -> None:
    titles = _build_wikipedia_titles({"object_name": "STARLINK-1007"})
    assert "Starlink" in titles
    assert len(titles) <= 3


def test_build_wikipedia_titles_iss() -> None:
    titles = _build_wikipedia_titles({"object_name": "ISS (ZARYA)"})
    assert "International Space Station" in titles


def test_build_wikipedia_titles_goes() -> None:
    titles = _build_wikipedia_titles({"object_name": "GOES-16"})
    assert any("Geostationary Operational Environmental Satellite" in t for t in titles)


def test_build_wikipedia_titles_generic() -> None:
    titles = _build_wikipedia_titles({"object_name": "MYSAT-1"})
    assert any("MYSAT" in t for t in titles)
    assert len(titles) >= 1


def test_build_wikipedia_titles_empty() -> None:
    titles = _build_wikipedia_titles({"object_name": ""})
    assert titles == []


def test_researcher_uses_wikipedia_evidence(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """When Wikipedia returns infobox data, structured fields are accepted without LLM."""
    async def fake_fetch_source_bundle(_: Any) -> SourceBundle:
        bundle = build_source_bundle()
        # Only keep the Starlink satellite — it has missing fields
        bundle.celestrak_satcat = [bundle.celestrak_satcat[0]]
        bundle.discos = []
        bundle.ucs = []
        return bundle

    async def fake_http_with_wiki(self: HttpTool, ctx: Any, *, method: str, url: str, **kwargs: Any) -> HttpToolResponse:
        params = kwargs.get("params") or {}
        if "wikipedia.org" in url and params.get("list") == "search":
            return HttpToolResponse(
                method="GET", url=url, final_url=url, status_code=200,
                headers={}, content_type="application/json", body_bytes=200,
                text=None, text_preview="",
                json_body={
                    "query": {
                        "search": [{"title": "Starlink", "snippet": "SpaceX constellation"}]
                    }
                },
            )
        if "wikipedia.org" in url and params.get("prop") == "revisions":
            wikitext = (
                "{{Infobox spacecraft\n"
                "| operator = [[SpaceX]]\n"
                "| manufacturer = [[SpaceX]]\n"
                "| mission_type = Communications\n"
                "| spacecraft_bus = Bus-1\n"
                "| launch_mass = {{convert|260|kg}}\n"
                "| design_life = 5 years\n"
                "}}\n"
            )
            return HttpToolResponse(
                method="GET", url=url, final_url=url, status_code=200,
                headers={}, content_type="application/json", body_bytes=500,
                text=None, text_preview="",
                json_body={
                    "query": {
                        "pages": {
                            "12345": {
                                "title": "Starlink",
                                "revisions": [{"slots": {"main": {"*": wikitext}}}],
                            }
                        }
                    }
                },
            )
        return HttpToolResponse(
            method="GET", url=url, final_url=url, status_code=404,
            headers={}, content_type="text/html", body_bytes=0,
            text="Not found", text_preview="Not found", json_body=None,
        )

    async def fake_scrape(self: WebScrapeTool, ctx: Any, *, url: str, max_chars: int = 2000, max_links: int = 6) -> dict[str, Any]:
        return {"url": url, "title": "Page", "text": "Satellite info", "links": [], "link_count": 0}

    llm_called = {"count": 0}

    async def spy_llm(self: LLMTool, ctx: Any, **_: Any) -> dict[str, Any]:
        llm_called["count"] += 1
        return {
            "provider_request_id": "req-1",
            "provider_model": "test",
            "output": {"confidence": 0.9, "fields": {}, "evidence_urls": []},
            "prompt_tokens": 100, "completion_tokens": 50, "estimated_cost_usd": 0.0,
        }

    monkeypatch.setenv("ATLAS_WEAVE_DATA_DIR", str(tmp_path))
    monkeypatch.setattr("recipes.satellite_enrichment.agents.collector.fetch_source_bundle", fake_fetch_source_bundle)
    monkeypatch.setattr(HttpTool, "call", fake_http_with_wiki)
    monkeypatch.setattr(WebSearchTool, "call", lambda *a, **kw: {"results": []})
    monkeypatch.setattr(WebScrapeTool, "call", fake_scrape)
    monkeypatch.setattr(LLMTool, "has_credentials", lambda self, provider: True)
    monkeypatch.setattr(LLMTool, "call", spy_llm)

    asyncio.run(run_recipe("satellite_enrichment", "sat-wiki-test", {
        "enable_llm_research": True,
        "skip_research_constellations": [],
    }))

    satellites = db.fetch_satellites(db.run_db_path("sat-wiki-test"))
    starlink = next((s for s in satellites if s["norad_id"] == 44713), None)
    assert starlink is not None
    assert starlink["operator_name"] == "SpaceX"
    assert starlink["manufacturer_name"] == "SpaceX"
    assert starlink["purpose_primary"] == "Communications"


def test_researcher_falls_back_to_web_search(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """When targeted sources all fail, researcher falls back to web search."""
    async def fake_fetch_source_bundle(_: Any) -> SourceBundle:
        bundle = build_source_bundle()
        bundle.celestrak_satcat = [bundle.celestrak_satcat[0]]
        bundle.discos = []
        bundle.ucs = []
        return bundle

    async def fake_http_404(self: HttpTool, ctx: Any, *, method: str, url: str, **kwargs: Any) -> HttpToolResponse:
        """All HTTP calls return empty/404."""
        return HttpToolResponse(
            method="GET", url=url, final_url=url, status_code=200,
            headers={}, content_type="application/json", body_bytes=50,
            text=None, text_preview="",
            json_body={"query": {"search": []}},
        )

    async def fake_scrape_404(self: WebScrapeTool, ctx: Any, *, url: str, max_chars: int = 2000, max_links: int = 6) -> dict[str, Any]:
        if "skyrocket.de" in url or "n2yo.com" in url:
            raise Exception("404 Not Found")
        return {
            "url": url, "title": "Fallback Page", "links": [], "link_count": 0,
            "text": "SpaceX operates Starlink for broadband internet communications.",
        }

    async def fake_search(self: WebSearchTool, ctx: Any, *, query: str, max_results: int = 4) -> dict[str, Any]:
        return {
            "query": query,
            "results": [
                {"title": "Starlink Info", "url": "https://example.com/fallback", "snippet": "Starlink info"}
            ],
        }

    async def fake_llm(self: LLMTool, ctx: Any, **_: Any) -> dict[str, Any]:
        return {
            "provider_request_id": "req-1",
            "provider_model": "test",
            "output": {
                "confidence": 0.85,
                "fields": {"operator_name": "SpaceX", "purpose_primary": "Communications"},
                "evidence_urls": ["https://example.com/fallback"],
            },
            "prompt_tokens": 200, "completion_tokens": 80, "estimated_cost_usd": 0.0,
        }

    monkeypatch.setenv("ATLAS_WEAVE_DATA_DIR", str(tmp_path))
    monkeypatch.setattr("recipes.satellite_enrichment.agents.collector.fetch_source_bundle", fake_fetch_source_bundle)
    monkeypatch.setattr(HttpTool, "call", fake_http_404)
    monkeypatch.setattr(WebSearchTool, "call", fake_search)
    monkeypatch.setattr(WebScrapeTool, "call", fake_scrape_404)
    monkeypatch.setattr(LLMTool, "has_credentials", lambda self, provider: True)
    monkeypatch.setattr(LLMTool, "call", fake_llm)

    asyncio.run(run_recipe("satellite_enrichment", "sat-fallback-test", {
        "enable_llm_research": True,
        "skip_research_constellations": [],
    }))

    satellites = db.fetch_satellites(db.run_db_path("sat-fallback-test"))
    starlink = next((s for s in satellites if s["norad_id"] == 44713), None)
    assert starlink is not None
    assert starlink["operator_name"] == "SpaceX"


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


# ── Unit tests for bug fixes and new logic ─────────────────────────────────────


def test_ucs_country_extraction_ignores_operator_name() -> None:
    """Verify 'SpaceX' is NOT used as country input — only 'Country of Operator/Owner' and 'Country' columns."""
    row = normalize_ucs_row({
        "NORAD Number": "44713",
        "Operator/Owner": "SpaceX",
        "Country of Operator/Owner": "USA",
        "Country": "USA",
    })
    assert row["operator_country_code"] == "US"
    assert row["operator_country_name"] == "United States"
    assert row["owner_country_code"] == "US"
    assert row["owner_country_name"] == "United States"


def test_ucs_country_extraction_does_not_pick_operator_name_as_country() -> None:
    """When only Operator/Owner is present (no country columns), country should be None."""
    row = normalize_ucs_row({
        "NORAD Number": "44713",
        "Operator/Owner": "SpaceX",
    })
    # "SpaceX" should NOT be used as a country — normalize_country("SpaceX") returns (None, "Spacex")
    assert row["operator_country_code"] is None


def test_space_track_satcat_normalizer_does_not_use_launch_piece() -> None:
    """LAUNCH_PIECE is the fragment designator, not the vehicle name."""
    row = normalize_space_track_satcat_row({
        "NORAD_CAT_ID": "25544",
        "OBJECT_NAME": "ISS (ZARYA)",
        "LAUNCH_PIECE": "A",
        "COUNTRY": "US",
    })
    # Should NOT pick "A" as the launch vehicle
    assert row["launch_vehicle"] is None


def test_space_track_satcat_normalizer_outputs_launch_site_country_code() -> None:
    """Merger expects launch_site_country_code, not country_code."""
    row = normalize_space_track_satcat_row({
        "NORAD_CAT_ID": "25544",
        "OBJECT_NAME": "ISS (ZARYA)",
        "COUNTRY": "US",
    })
    assert "launch_site_country_code" in row
    assert row["launch_site_country_code"] == "US"
    assert "country_code" not in row


def test_constellation_template_fills_empty_fields() -> None:
    """Constellation templates should fill empty record fields."""
    template = CONSTELLATION_TEMPLATES.get("starlink")
    assert template is not None
    assert template["manufacturer_name"] == "SpaceX"
    assert template["operator_name"] == "SpaceX"
    assert template["purpose_primary"] == "Communications"
    assert template["design_life_years"] == 5.0


def test_object_type_derivation_from_name() -> None:
    """object_type should be derived from object_name patterns when missing."""
    from recipes.satellite_enrichment.agents.merger import _finalize_derived_fields

    debris_record: dict[str, Any] = {"object_name": "STARLINK-1001 DEB", "object_type": None}
    _finalize_derived_fields(debris_record)
    assert debris_record["object_type"] == "DEBRIS"
    assert debris_record["is_debris"] is True

    rb_record: dict[str, Any] = {"object_name": "CZ-2C R/B", "object_type": None}
    _finalize_derived_fields(rb_record)
    assert rb_record["object_type"] == "ROCKET BODY"

    payload_record: dict[str, Any] = {"object_name": "STARLINK-1001", "object_type": None}
    _finalize_derived_fields(payload_record)
    assert payload_record["object_type"] == "PAYLOAD"


def test_launch_date_derivation_from_international_designator() -> None:
    """launch_date should be derived from international_designator when missing."""
    from recipes.satellite_enrichment.agents.merger import _finalize_derived_fields

    record: dict[str, Any] = {
        "international_designator": "2019-074A",
        "launch_date": None,
        "launch_year": None,
        "object_type": "PAYLOAD",
    }
    _finalize_derived_fields(record)
    assert record["launch_date"] == "2019-01-01"
    assert record["launch_year"] == 2019


def test_launch_date_not_derived_when_already_present() -> None:
    """Existing launch_date should not be overwritten."""
    from recipes.satellite_enrichment.agents.merger import _finalize_derived_fields

    record: dict[str, Any] = {
        "international_designator": "2019-074A",
        "launch_date": "2019-11-11",
        "launch_year": 2019,
        "object_type": "PAYLOAD",
    }
    _finalize_derived_fields(record)
    assert record["launch_date"] == "2019-11-11"
