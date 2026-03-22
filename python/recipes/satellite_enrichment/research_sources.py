from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass, field
from typing import Any

from atlas_weave.context import AgentContext


@dataclass(slots=True)
class EvidenceResult:
    source_name: str
    structured_fields: dict[str, Any] = field(default_factory=dict)
    scraped_text: str = ""
    evidence_urls: list[str] = field(default_factory=list)
    success: bool = False


# ── Wikipedia ──────────────────────────────────────────────────────────────────

_WIKI_API = "https://en.wikipedia.org/w/api.php"
_WIKI_HEADERS = {
    "User-Agent": "AtlasWeave/0.1 (satellite enrichment pipeline; https://github.com/atlas-weave)"
}

_CONSTELLATION_ARTICLES: dict[str, str] = {
    "STARLINK": "Starlink",
    "ONEWEB": "OneWeb satellite constellation",
    "IRIDIUM": "Iridium satellite constellation",
    "GLOBALSTAR": "Globalstar",
    "ORBCOMM": "Orbcomm",
    "GPS": "GPS satellite",
    "GALILEO": "Galileo (satellite navigation)",
    "BEIDOU": "BeiDou",
    "GLONASS": "GLONASS",
    "COSMOS": "Cosmos (satellite)",
    "INTELSAT": "Intelsat",
    "SES": "SES S.A.",
    "TELESAT": "Telesat",
}

_WELL_KNOWN: dict[str, str] = {
    "ISS (ZARYA)": "International Space Station",
    "ISS": "International Space Station",
    "HUBBLE": "Hubble Space Telescope",
    "HST": "Hubble Space Telescope",
    "TDRS": "Tracking and Data Relay Satellite",
    "GOES": "Geostationary Operational Environmental Satellite",
    "NOAA": "NOAA satellite",
    "LANDSAT": "Landsat program",
    "TERRA": "Terra (satellite)",
    "AQUA": "Aqua (satellite)",
    "JASON": "Jason (satellite)",
}


def _build_wikipedia_titles(record: dict[str, Any]) -> list[str]:
    """Build up to 3 candidate Wikipedia article titles from the satellite record."""
    object_name = str(record.get("object_name") or "").strip()
    if not object_name:
        return []

    upper = object_name.upper()
    titles: list[str] = []

    # Check well-known exact matches first
    if upper in _WELL_KNOWN:
        titles.append(_WELL_KNOWN[upper])
    for prefix, article in _WELL_KNOWN.items():
        if upper.startswith(prefix) and article not in titles:
            titles.append(article)
            break

    # Check constellation patterns — strip numeric suffix
    base = re.sub(r"[-\s]\d+$", "", upper).strip()
    for prefix, article in _CONSTELLATION_ARTICLES.items():
        if (
            base == prefix
            or upper.startswith(prefix + "-")
            or upper.startswith(prefix + " ")
        ):
            if article not in titles:
                titles.append(article)
            break

    # Try the object name itself with disambiguation
    name_title = object_name.replace("_", " ").strip()
    # Remove parenthetical like "(ZARYA)"
    clean = re.sub(r"\s*\(.*?\)\s*", " ", name_title).strip()
    if clean and clean not in titles:
        titles.append(clean)
    disambiguation = f"{clean} (satellite)"
    if disambiguation not in titles:
        titles.append(disambiguation)

    return titles[:3]


def _parse_wikipedia_infobox(wikitext: str) -> dict[str, Any]:
    """Extract satellite metadata from Wikipedia infobox wikitext."""
    fields: dict[str, Any] = {}
    if not wikitext:
        return fields

    field_map = {
        "manufacturer": "manufacturer_name",
        "manufacturer_name": "manufacturer_name",
        "operator": "operator_name",
        "operators": "operator_name",
        "mission_type": "purpose_primary",
        "mission type": "purpose_primary",
        "spacecraft_bus": "bus_platform",
        "spacecraft bus": "bus_platform",
        "bus": "bus_platform",
        "spacecraft_type": "bus_platform",
        "design_life": "design_life_years",
        "design life": "design_life_years",
    }

    for line in wikitext.split("\n"):
        line = line.strip()
        if not line.startswith("|"):
            continue
        match = re.match(r"\|\s*([^=]+?)\s*=\s*(.*)", line)
        if not match:
            continue

        wiki_key = match.group(1).strip().lower().replace(" ", "_")
        raw_value = match.group(2).strip()
        if not raw_value:
            continue

        our_field = field_map.get(wiki_key) or field_map.get(wiki_key.replace("_", " "))
        if not our_field:
            # Also check for launch_mass → dry_mass_kg
            if wiki_key in ("launch_mass", "mass", "spacecraft_mass"):
                mass = _parse_mass(raw_value)
                if mass is not None:
                    fields.setdefault("dry_mass_kg", mass)
            continue

        if our_field == "design_life_years":
            years = _parse_years(raw_value)
            if years is not None:
                fields.setdefault(our_field, years)
        elif our_field == "dry_mass_kg":
            mass = _parse_mass(raw_value)
            if mass is not None:
                fields.setdefault(our_field, mass)
        else:
            cleaned = _clean_wikitext(raw_value)
            if cleaned:
                fields.setdefault(our_field, cleaned)

    return fields


def _parse_mass(raw: str) -> float | None:
    """Parse mass from wikitext values like '260 kg', '{{convert|260|kg}}', etc."""
    # Handle {{convert|260|kg|...}}
    convert_match = re.search(r"\{\{convert\|([0-9,.]+)\|kg", raw, re.IGNORECASE)
    if convert_match:
        try:
            return float(convert_match.group(1).replace(",", ""))
        except ValueError:
            pass

    # Handle plain numbers with kg
    kg_match = re.search(r"([0-9,.]+)\s*kg", raw, re.IGNORECASE)
    if kg_match:
        try:
            return float(kg_match.group(1).replace(",", ""))
        except ValueError:
            pass

    # Handle plain numbers
    num_match = re.search(r"([0-9,.]+)", raw)
    if num_match:
        try:
            val = float(num_match.group(1).replace(",", ""))
            if 1 <= val <= 50000:
                return val
        except ValueError:
            pass

    return None


def _parse_years(raw: str) -> float | None:
    """Parse design life like '5 years', '15 yr', etc."""
    match = re.search(r"([0-9.]+)\s*(?:years?|yr)", raw, re.IGNORECASE)
    if match:
        try:
            val = float(match.group(1))
            if 0 < val <= 50:
                return val
        except ValueError:
            pass
    # Try plain number
    match = re.search(r"([0-9.]+)", raw)
    if match:
        try:
            val = float(match.group(1))
            if 0 < val <= 50:
                return val
        except ValueError:
            pass
    return None


def _clean_wikitext(raw: str) -> str:
    """Strip wiki markup from a value."""
    # Remove [[ ]] links, keeping display text
    cleaned = re.sub(r"\[\[(?:[^|\]]*\|)?([^\]]*)\]\]", r"\1", raw)
    # Remove {{ }} templates (simple case)
    cleaned = re.sub(r"\{\{[^}]*\}\}", "", cleaned)
    # Remove HTML tags
    cleaned = re.sub(r"<[^>]+>", "", cleaned)
    # Remove <ref>...</ref>
    cleaned = re.sub(r"<ref[^>]*>.*?</ref>", "", cleaned, flags=re.DOTALL)
    cleaned = re.sub(r"<ref[^>]*/?>", "", cleaned)
    # Collapse whitespace
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


async def fetch_wikipedia_evidence(
    ctx: AgentContext, record: dict[str, Any]
) -> EvidenceResult:
    """Fetch satellite data from Wikipedia using the MediaWiki API."""
    titles = _build_wikipedia_titles(record)
    if not titles:
        return EvidenceResult(source_name="wikipedia")

    node_id = ctx.node_id
    for title in titles:
        try:
            # Search for the article
            search_resp = await ctx.tools.http.call(
                ctx,
                method="GET",
                url=_WIKI_API,
                headers=_WIKI_HEADERS,
                params={
                    "action": "query",
                    "list": "search",
                    "srsearch": title,
                    "format": "json",
                    "srlimit": "3",
                },
                timeout_s=15.0,
                raise_for_status=True,
            )
            search_data = search_resp.json_body
            if not search_data or "query" not in search_data:
                continue
            search_results = search_data["query"].get("search", [])
            if not search_results:
                continue

            page_title = search_results[0]["title"]

            # Fetch the page content
            content_resp = await ctx.tools.http.call(
                ctx,
                method="GET",
                url=_WIKI_API,
                headers=_WIKI_HEADERS,
                params={
                    "action": "query",
                    "titles": page_title,
                    "prop": "revisions",
                    "rvprop": "content",
                    "rvslots": "main",
                    "format": "json",
                },
                timeout_s=15.0,
                raise_for_status=True,
            )
            content_data = content_resp.json_body
            if not content_data or "query" not in content_data:
                continue

            pages = content_data["query"].get("pages", {})
            page = next(iter(pages.values()), None)
            if not page or "revisions" not in page:
                continue

            revision = page["revisions"][0]
            wikitext = ""
            if "slots" in revision and "main" in revision["slots"]:
                wikitext = revision["slots"]["main"].get("*", "")
            elif "*" in revision:
                wikitext = revision["*"]

            if not wikitext:
                continue

            structured = _parse_wikipedia_infobox(wikitext)
            # Truncate text for LLM consumption
            scraped_text = wikitext[:3000]
            wiki_url = f"https://en.wikipedia.org/wiki/{page_title.replace(' ', '_')}"

            return EvidenceResult(
                source_name="wikipedia",
                structured_fields=structured,
                scraped_text=scraped_text,
                evidence_urls=[wiki_url],
                success=True,
            )
        except Exception as exc:  # noqa: BLE001
            ctx.emit.log(
                node_id, "warning", f"Wikipedia fetch failed for '{title}': {exc}"
            )
            continue

    return EvidenceResult(source_name="wikipedia")


# ── Gunter's Space Page ────────────────────────────────────────────────────────


def _gunter_url_candidates(record: dict[str, Any]) -> list[str]:
    """Build candidate Gunter's Space Page URLs for a satellite."""
    object_name = str(record.get("object_name") or "").strip()
    if not object_name:
        return []

    urls: list[str] = []
    base = "https://space.skyrocket.de/doc_sdat"

    # Try exact name (lowercased, spaces→hyphens)
    slug = object_name.lower().replace(" ", "-").replace("(", "").replace(")", "")
    urls.append(f"{base}/{slug}.htm")

    # Try without numeric suffix (constellation base)
    base_name = re.sub(r"[-\s]\d+$", "", object_name).strip()
    if base_name != object_name:
        slug2 = base_name.lower().replace(" ", "-").replace("(", "").replace(")", "")
        urls.append(f"{base}/{slug2}.htm")

    return urls[:2]


async def fetch_gunter_evidence(
    ctx: AgentContext, record: dict[str, Any]
) -> EvidenceResult:
    """Scrape satellite data from Gunter's Space Page."""
    urls = _gunter_url_candidates(record)
    for url in urls:
        try:
            scraped = await ctx.tools.web_scrape.call(
                ctx, url=url, max_chars=4000, max_links=6
            )
            text = str(scraped.get("text") or "")
            if len(text) > 100:
                return EvidenceResult(
                    source_name="gunter",
                    scraped_text=text,
                    evidence_urls=[url],
                    success=True,
                )
        except Exception:  # noqa: BLE001
            continue

    return EvidenceResult(source_name="gunter")


# ── N2YO ───────────────────────────────────────────────────────────────────────


async def fetch_n2yo_evidence(
    ctx: AgentContext, record: dict[str, Any]
) -> EvidenceResult:
    """Scrape satellite info from N2YO by NORAD ID."""
    norad_id = record.get("norad_id")
    if not norad_id:
        return EvidenceResult(source_name="n2yo")

    url = f"https://www.n2yo.com/satellite/?s={norad_id}"
    try:
        scraped = await ctx.tools.web_scrape.call(
            ctx, url=url, max_chars=3000, max_links=6
        )
        text = str(scraped.get("text") or "")
        if len(text) > 100:
            return EvidenceResult(
                source_name="n2yo",
                scraped_text=text,
                evidence_urls=[url],
                success=True,
            )
    except Exception:  # noqa: BLE001
        pass

    return EvidenceResult(source_name="n2yo")


# ── Evidence orchestrator ──────────────────────────────────────────────────────


async def gather_evidence(
    ctx: AgentContext,
    record: dict[str, Any],
    missing_fields: list[str],
    conflict_fields: list[str],
    shared_evidence: dict[str, list[EvidenceResult]] | None = None,
) -> list[EvidenceResult]:
    """Gather evidence from targeted sources, falling back to web search if needed."""
    constellation_key = _constellation_key(record)

    # Check shared evidence cache for constellation satellites
    if (
        shared_evidence is not None
        and constellation_key
        and constellation_key in shared_evidence
    ):
        return shared_evidence[constellation_key]

    # Run targeted sources concurrently
    wiki_task = asyncio.create_task(fetch_wikipedia_evidence(ctx, record))
    gunter_task = asyncio.create_task(fetch_gunter_evidence(ctx, record))
    n2yo_task = asyncio.create_task(fetch_n2yo_evidence(ctx, record))

    results_raw = await asyncio.gather(
        wiki_task, gunter_task, n2yo_task, return_exceptions=True
    )
    evidence: list[EvidenceResult] = []
    for result in results_raw:
        if isinstance(result, EvidenceResult) and result.success:
            evidence.append(result)

    # If no targeted source found data, fall back to web search
    if not evidence:
        fallback = await _fallback_web_search(
            ctx, record, missing_fields, conflict_fields
        )
        if fallback.success:
            evidence.append(fallback)

    # Cache results for constellation members
    if (
        shared_evidence is not None
        and constellation_key
        and constellation_key not in shared_evidence
    ):
        shared_evidence[constellation_key] = evidence

    return evidence


async def _fallback_web_search(
    ctx: AgentContext,
    record: dict[str, Any],
    missing_fields: list[str],
    conflict_fields: list[str],
) -> EvidenceResult:
    """Fall back to web search when targeted sources fail."""
    object_name = str(record.get("object_name") or "")

    # Try site-scoped Wikipedia search first
    site_query = f'site:en.wikipedia.org "{object_name}" satellite'
    try:
        search = await ctx.tools.web_search.call(ctx, query=site_query, max_results=2)
        results = list(search.get("results") or [])
        if results:
            url = str(results[0]["url"])
            scraped = await ctx.tools.web_scrape.call(
                ctx, url=url, max_chars=3000, max_links=6
            )
            text = str(scraped.get("text") or "")
            if len(text) > 100:
                return EvidenceResult(
                    source_name="web_search",
                    scraped_text=text,
                    evidence_urls=[url],
                    success=True,
                )
    except Exception:  # noqa: BLE001
        pass

    # Last resort: generic search
    query = _build_search_query(record, missing_fields, conflict_fields)
    try:
        search = await ctx.tools.web_search.call(ctx, query=query, max_results=4)
        results = list(search.get("results") or [])
        scraped_texts: list[str] = []
        urls: list[str] = []
        for result in results[:2]:
            try:
                scraped = await ctx.tools.web_scrape.call(
                    ctx, url=str(result["url"]), max_chars=2000, max_links=6
                )
                text = str(scraped.get("text") or "")
                if text:
                    scraped_texts.append(text)
                    urls.append(str(result["url"]))
            except Exception:  # noqa: BLE001
                continue
        if scraped_texts:
            return EvidenceResult(
                source_name="web_search",
                scraped_text="\n\n---\n\n".join(scraped_texts),
                evidence_urls=urls,
                success=True,
            )
    except Exception:  # noqa: BLE001
        pass

    return EvidenceResult(source_name="web_search")


def _build_search_query(
    record: dict[str, Any], missing_fields: list[str], conflict_fields: list[str]
) -> str:
    """Build a web search query from the record and field needs."""
    metadata_terms: list[str] = []
    if any(f.startswith("operator") or f.startswith("owner") for f in missing_fields):
        metadata_terms.append("operator owner")
    if any(f.startswith("purpose") or f == "mission_class" for f in missing_fields):
        metadata_terms.append("mission purpose")
    if any(
        f
        in {
            "manufacturer_name",
            "bus_platform",
            "dry_mass_kg",
            "design_life_years",
            "program_name",
        }
        for f in missing_fields
    ):
        metadata_terms.append("manufacturer specifications")
    if conflict_fields:
        metadata_terms.append("satellite facts")
    parts = [
        record.get("object_name"),
        "satellite",
        " ".join(metadata_terms) if metadata_terms else "operator mission manufacturer",
    ]
    return " ".join(str(p).strip() for p in parts if p)


def _constellation_key(record: dict[str, Any]) -> str | None:
    """Extract a constellation cache key from a record, if it's a constellation member."""
    object_name = str(record.get("object_name") or "").upper()
    # Check for pattern: NAME-NUMBER (e.g., STARLINK-1007, ONEWEB-0123)
    match = re.match(r"^([A-Z]+)[-\s]\d+", object_name)
    if match:
        base = match.group(1)
        if base in _CONSTELLATION_ARTICLES:
            return base
    return None
