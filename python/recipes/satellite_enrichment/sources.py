from __future__ import annotations

import asyncio
import csv
import json
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from io import StringIO
from pathlib import Path
from typing import Any

import httpx

from atlas_weave.context import AgentContext
from recipes.satellite_enrichment import db
from recipes.satellite_enrichment.schema import normalize_country, utc_now

SPACE_TRACK_GP_BATCH_SIZE = 50
SPACE_TRACK_GP_DELAY_S = 0.75
SPACE_TRACK_RETRY_ATTEMPTS = 6
SOURCE_CACHE_TTL_MINUTES = {
    "celestrak": 60,
    "discos": 240,
    "ucs_url": 1440,
    "space_track": 720,
}

CELESTRAK_GROUPS = [
    "active",
    "stations",
    "visual",
    "weather",
    "noaa",
    "goes",
    "resource",
    "sarsat",
    "dmc",
    "tdrss",
    "argos",
    "planet",
    "spire",
    "geo",
    "intelsat",
    "ses",
    "iridium",
    "starlink",
    "oneweb",
    "orbcomm",
    "globalstar",
    "amateur",
    "x-comm",
    "other-comm",
    "gps-ops",
    "glo-ops",
    "galileo",
    "beidou",
    "satnogs",
    "cubesat",
    "education",
    "engineering",
    "geodetic",
    "science",
    "radar",
    "military",
    "musson",
    "gnss",
    "tle-new",
    "last-30-days",
    "active-geo",
    "geo-protected",
    "intelsat-geo",
    "analyst",
    "other",
    "navigation",
    "communications",
    "earth-resources",
]


@dataclass(slots=True)
class SourceBundle:
    space_track_satcat: list[dict[str, Any]]
    space_track_gp: list[dict[str, Any]]
    celestrak_satcat: list[dict[str, Any]]
    discos: list[dict[str, Any]]
    ucs: list[dict[str, Any]]
    source_status: dict[str, str]
    cached_sources: list[str]
    stale_sources: list[str]
    source_snapshots: list[dict[str, Any]]

    def counts(self) -> dict[str, int]:
        return {
            "space_track_satcat": len(self.space_track_satcat),
            "space_track_gp": len(self.space_track_gp),
            "celestrak_satcat": len(self.celestrak_satcat),
            "discos": len(self.discos),
            "ucs": len(self.ucs),
        }


async def fetch_source_bundle(ctx: AgentContext) -> SourceBundle:
    cached_sources: list[str] = []
    stale_sources: list[str] = []
    source_snapshots: list[dict[str, Any]] = []

    ctx.emit.progress(ctx.node_id, 0.06, "Fetching CelesTrak categories")
    celestrak_rows, celestrak_status, snapshot = await _fetch_celestrak(ctx)
    _record_snapshot_state("celestrak", celestrak_status, snapshot, cached_sources, stale_sources, source_snapshots)

    ctx.emit.progress(ctx.node_id, 0.38, "Fetching ESA DISCOS objects")
    discos_rows, discos_status, snapshot = await _fetch_discos(ctx)
    _record_snapshot_state("discos", discos_status, snapshot, cached_sources, stale_sources, source_snapshots)

    ctx.emit.progress(ctx.node_id, 0.58, "Loading UCS catalog")
    ucs_rows, ucs_status, snapshot = await _fetch_ucs(ctx)
    _record_snapshot_state("ucs", ucs_status, snapshot, cached_sources, stale_sources, source_snapshots)

    ctx.emit.progress(ctx.node_id, 0.78, "Resolving optional Space-Track data")
    satcat_rows, gp_rows, space_track_status, snapshot = await _fetch_space_track(ctx)
    _record_snapshot_state("space_track", space_track_status, snapshot, cached_sources, stale_sources, source_snapshots)

    if not any((celestrak_rows, discos_rows, ucs_rows, satcat_rows)):
        raise ValueError("No structured source data was collected. Configure CelesTrak access, UCS input, or DISCOS credentials.")

    ctx.emit.progress(ctx.node_id, 0.94, "Structured source collection complete")
    return SourceBundle(
        space_track_satcat=satcat_rows,
        space_track_gp=gp_rows,
        celestrak_satcat=celestrak_rows,
        discos=discos_rows,
        ucs=ucs_rows,
        source_status={
            "space_track": space_track_status,
            "celestrak": celestrak_status,
            "discos": discos_status,
            "ucs": ucs_status,
        },
        cached_sources=cached_sources,
        stale_sources=stale_sources,
        source_snapshots=source_snapshots,
    )


async def _fetch_space_track(
    ctx: AgentContext,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], str, dict[str, Any] | None]:
    mode = str(ctx.config.get("space_track_mode", "prefer_cache") or "prefer_cache").strip().lower()
    if mode not in {"disabled", "prefer_cache", "live"}:
        mode = "prefer_cache"

    fresh_snapshot = _load_snapshot("space_track", SOURCE_CACHE_TTL_MINUTES["space_track"])
    stale_snapshot = fresh_snapshot or _load_snapshot("space_track", None)

    if mode == "disabled":
        return ([], [], "disabled", _snapshot_metadata(stale_snapshot, "disabled"))

    if mode == "prefer_cache":
        if stale_snapshot:
            return (
                list(stale_snapshot["payload"].get("satcat_rows", [])),
                list(stale_snapshot["payload"].get("gp_rows", [])),
                "cached" if fresh_snapshot else "stale_cache",
                _snapshot_metadata(stale_snapshot, "cached" if fresh_snapshot else "stale_cache"),
            )
        return ([], [], "skipped", None)

    identity = os.getenv("SPACE_TRACK_IDENTITY")
    password = os.getenv("SPACE_TRACK_PASSWORD")
    if not identity or not password:
        if stale_snapshot:
            ctx.emit.log(ctx.node_id, "warning", "Space-Track live mode requested without credentials; using cached snapshot instead.")
            return (
                list(stale_snapshot["payload"].get("satcat_rows", [])),
                list(stale_snapshot["payload"].get("gp_rows", [])),
                "stale_cache",
                _snapshot_metadata(stale_snapshot, "stale_cache"),
            )
        ctx.emit.log(ctx.node_id, "warning", "Space-Track live mode requested without credentials; skipping Space-Track.")
        return ([], [], "skipped", None)

    login_url = "https://www.space-track.org/ajaxauth/login"
    satcat_url = "https://www.space-track.org/basicspacedata/query/class/satcat/orderby/NORAD_CAT_ID asc/format/json"
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=45.0) as client:
            login_response = await client.post(
                login_url,
                data={"identity": identity, "password": password},
                headers={"User-Agent": "AtlasWeave/0.1"},
            )
            login_response.raise_for_status()

            satcat_response = await _retry_request(
                lambda: client.get(satcat_url, headers={"User-Agent": "AtlasWeave/0.1"}),
                attempts=SPACE_TRACK_RETRY_ATTEMPTS,
                on_retry=lambda attempt, delay_s, status_code: ctx.emit.log(
                    ctx.node_id,
                    "warning",
                    (
                        f"Space-Track SATCAT request retry {attempt}/{SPACE_TRACK_RETRY_ATTEMPTS} "
                        f"after HTTP {status_code}; waiting {delay_s:.1f}s."
                    ),
                ),
            )
            satcat_response.raise_for_status()
            satcat_payload = _parse_space_track_payload(satcat_response.json(), "SATCAT")
            satcat_rows = [normalize_space_track_satcat_row(item) for item in satcat_payload]
            satcat_rows = [row for row in satcat_rows if row.get("norad_id") is not None]
            if not satcat_rows:
                raise ValueError("Space-Track SATCAT response did not contain any valid satellite records")

            record_limit = _safe_int(ctx.config.get("record_limit"))
            if record_limit:
                satcat_rows = satcat_rows[:record_limit]

            norad_ids = [str(row["norad_id"]) for row in satcat_rows if row.get("norad_id")]
            gp_rows: list[dict[str, Any]] = []
            batches = _batched(norad_ids, SPACE_TRACK_GP_BATCH_SIZE)
            for index, batch in enumerate(batches, start=1):
                ctx.raise_if_cancelled()
                if index > 1:
                    await asyncio.sleep(SPACE_TRACK_GP_DELAY_S)
                gp_payload = await _fetch_space_track_gp_batch(ctx, client, batch)
                gp_rows.extend(normalize_space_track_gp_row(item) for item in gp_payload)
                ctx.emit.progress(
                    ctx.node_id,
                    min(0.92, 0.78 + (index / max(1, len(batches))) * 0.12),
                    f"Fetched Space-Track GP batch {index}/{max(1, len(batches))}",
                )
    except Exception as error:  # noqa: BLE001
        if stale_snapshot:
            ctx.emit.log(ctx.node_id, "warning", f"Space-Track live fetch failed; using cached snapshot instead: {error}")
            return (
                list(stale_snapshot["payload"].get("satcat_rows", [])),
                list(stale_snapshot["payload"].get("gp_rows", [])),
                "stale_cache",
                _snapshot_metadata(stale_snapshot, "stale_cache"),
            )
        ctx.emit.log(ctx.node_id, "warning", f"Space-Track fetch failed and no cache is available: {error}")
        return ([], [], "failed", None)

    snapshot = _write_snapshot(
        "space_track",
        {
            "satcat_rows": satcat_rows,
            "gp_rows": gp_rows,
        },
        ttl_minutes=SOURCE_CACHE_TTL_MINUTES["space_track"],
        source_url=satcat_url,
        record_count=len(satcat_rows),
    )
    return (satcat_rows, gp_rows, "live", _snapshot_metadata(snapshot, "live"))


async def _fetch_space_track_gp_batch(
    ctx: AgentContext,
    client: httpx.AsyncClient,
    norad_ids: list[str],
) -> list[dict[str, Any]]:
    if not norad_ids:
        return []

    gp_url = (
        "https://www.space-track.org/basicspacedata/query/class/gp/"
        f"NORAD_CAT_ID/{','.join(norad_ids)}/orderby/NORAD_CAT_ID asc/format/json"
    )
    response = await _retry_request(
        lambda: client.get(gp_url, headers={"User-Agent": "AtlasWeave/0.1"}),
        attempts=SPACE_TRACK_RETRY_ATTEMPTS,
        on_retry=lambda attempt, delay_s, status_code: ctx.emit.log(
            ctx.node_id,
            "warning",
            (
                f"Space-Track GP request retry {attempt}/{SPACE_TRACK_RETRY_ATTEMPTS} "
                f"after HTTP {status_code}; waiting {delay_s:.1f}s."
            ),
        ),
    )

    if response.status_code == 400 and len(norad_ids) > 1:
        midpoint = max(1, len(norad_ids) // 2)
        ctx.emit.log(
            ctx.node_id,
            "warning",
            f"Space-Track rejected a GP batch of {len(norad_ids)} ids; retrying in smaller chunks.",
        )
        left = await _fetch_space_track_gp_batch(ctx, client, norad_ids[:midpoint])
        right = await _fetch_space_track_gp_batch(ctx, client, norad_ids[midpoint:])
        return [*left, *right]

    response.raise_for_status()
    payload = _parse_space_track_payload(response.json(), "GP")
    return payload if isinstance(payload, list) else []


async def _fetch_celestrak(
    ctx: AgentContext,
) -> tuple[list[dict[str, Any]], str, dict[str, Any] | None]:
    ttl_minutes = max(1, _safe_int(ctx.config.get("celestrak_cache_ttl_minutes")) or SOURCE_CACHE_TTL_MINUTES["celestrak"])
    refresh_sources = bool(ctx.config.get("refresh_sources", False))
    fresh_snapshot = None if refresh_sources else _load_snapshot("celestrak", ttl_minutes)
    if fresh_snapshot:
        rows = [dict(row) for row in fresh_snapshot["payload"].get("rows", [])]
        return (rows, "cached", _snapshot_metadata(fresh_snapshot, "cached"))

    stale_snapshot = _load_snapshot("celestrak", None)
    rows: list[dict[str, Any]] = []
    failures = 0
    for index, group in enumerate(CELESTRAK_GROUPS, start=1):
        ctx.raise_if_cancelled()
        url = f"https://celestrak.org/NORAD/elements/gp.php?GROUP={group}&FORMAT=json"
        try:
            response = await ctx.tools.http.call(ctx, method="GET", url=url, headers={"User-Agent": "AtlasWeave/0.1"})
            payload = response.json_body if isinstance(response.json_body, list) else []
            rows.extend(normalize_celestrak_row(item, group) for item in payload)
        except Exception as error:  # noqa: BLE001
            failures += 1
            ctx.emit.log(ctx.node_id, "warning", f"CelesTrak group {group} failed: {error}")
        ctx.emit.progress(
            ctx.node_id,
            0.06 + (index / len(CELESTRAK_GROUPS)) * 0.28,
            f"Fetching CelesTrak: {index}/{len(CELESTRAK_GROUPS)} groups",
        )
        await asyncio.sleep(0.2)

    rows = _dedupe_celestrak_rows(rows)
    if rows:
        snapshot = _write_snapshot(
            "celestrak",
            {"rows": rows},
            ttl_minutes=ttl_minutes,
            source_url="https://celestrak.org/NORAD/elements/gp.php",
            record_count=len(rows),
        )
        status = "live" if failures == 0 else "partial_live"
        return (rows, status, _snapshot_metadata(snapshot, status))

    if stale_snapshot:
        ctx.emit.log(ctx.node_id, "warning", "CelesTrak live fetch failed; using cached snapshot instead.")
        return (
            [dict(row) for row in stale_snapshot["payload"].get("rows", [])],
            "stale_cache",
            _snapshot_metadata(stale_snapshot, "stale_cache"),
        )
    return ([], "failed", None)


async def _fetch_discos(
    ctx: AgentContext,
) -> tuple[list[dict[str, Any]], str, dict[str, Any] | None]:
    refresh_sources = bool(ctx.config.get("refresh_sources", False))
    fresh_snapshot = None if refresh_sources else _load_snapshot("discos", SOURCE_CACHE_TTL_MINUTES["discos"])
    if fresh_snapshot:
        return (
            [dict(row) for row in fresh_snapshot["payload"].get("rows", [])],
            "cached",
            _snapshot_metadata(fresh_snapshot, "cached"),
        )

    token = os.getenv("DISCOS_API_TOKEN")
    stale_snapshot = _load_snapshot("discos", None)
    if not token:
        if stale_snapshot:
            ctx.emit.log(ctx.node_id, "warning", "DISCOS token is missing; using cached DISCOS snapshot.")
            return (
                [dict(row) for row in stale_snapshot["payload"].get("rows", [])],
                "stale_cache",
                _snapshot_metadata(stale_snapshot, "stale_cache"),
            )
        return ([], "skipped", None)

    rows: list[dict[str, Any]] = []
    try:
        page_number = 1
        while True:
            ctx.raise_if_cancelled()
            response = await ctx.tools.http.call(
                ctx,
                method="GET",
                url="https://discosweb.esoc.esa.int/api/objects",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/vnd.api+json",
                    "User-Agent": "AtlasWeave/0.1",
                },
                params={
                    "filter": "eq(objectClass,Payload)",
                    "page[number]": page_number,
                    "page[size]": 100,
                },
            )
            payload = response.json_body or {}
            data = payload.get("data") if isinstance(payload, dict) else None
            if not isinstance(data, list) or not data:
                break
            rows.extend(normalize_discos_row(item) for item in data)
            page_number += 1
            if page_number > 500:
                break
    except Exception as error:  # noqa: BLE001
        if stale_snapshot:
            ctx.emit.log(ctx.node_id, "warning", f"DISCOS live fetch failed; using cached snapshot instead: {error}")
            return (
                [dict(row) for row in stale_snapshot["payload"].get("rows", [])],
                "stale_cache",
                _snapshot_metadata(stale_snapshot, "stale_cache"),
            )
        ctx.emit.log(ctx.node_id, "warning", f"DISCOS fetch failed: {error}")
        return ([], "failed", None)

    snapshot = _write_snapshot(
        "discos",
        {"rows": rows},
        ttl_minutes=SOURCE_CACHE_TTL_MINUTES["discos"],
        source_url="https://discosweb.esoc.esa.int/api/objects",
        record_count=len(rows),
    )
    return (rows, "live", _snapshot_metadata(snapshot, "live"))


async def _fetch_ucs(
    ctx: AgentContext,
) -> tuple[list[dict[str, Any]], str, dict[str, Any] | None]:
    csv_path = str(ctx.config.get("ucs_catalog_csv_path", "") or "").strip()
    csv_url = str(ctx.config.get("ucs_catalog_csv_url", "") or "").strip()
    if csv_path:
        text = await asyncio.to_thread(_read_text_file_with_fallbacks, csv_path)
        rows = _parse_ucs_csv(text)
        return (
            rows,
            "file",
            {
                "source_key": "ucs",
                "status": "file",
                "cache_state": "file",
                "record_count": len(rows),
                "source_url": csv_path,
                "cache_path": csv_path,
                "fetched_at": utc_now(),
                "expires_at": None,
            },
        )

    if csv_url:
        refresh_sources = bool(ctx.config.get("refresh_sources", False))
        fresh_snapshot = None if refresh_sources else _load_snapshot("ucs_url", SOURCE_CACHE_TTL_MINUTES["ucs_url"])
        if fresh_snapshot:
            return (
                [dict(row) for row in fresh_snapshot["payload"].get("rows", [])],
                "cached",
                _snapshot_metadata(fresh_snapshot, "cached", source_key="ucs"),
            )
        stale_snapshot = _load_snapshot("ucs_url", None)
        try:
            response = await ctx.tools.http.call(ctx, method="GET", url=csv_url, headers={"User-Agent": "AtlasWeave/0.1"})
            rows = _parse_ucs_csv(_decode_csv_http_response(response))
            snapshot = _write_snapshot(
                "ucs_url",
                {"rows": rows},
                ttl_minutes=SOURCE_CACHE_TTL_MINUTES["ucs_url"],
                source_url=csv_url,
                record_count=len(rows),
            )
            return (rows, "live", _snapshot_metadata(snapshot, "live", source_key="ucs"))
        except Exception as error:  # noqa: BLE001
            if stale_snapshot:
                ctx.emit.log(ctx.node_id, "warning", f"UCS URL fetch failed; using cached snapshot instead: {error}")
                return (
                    [dict(row) for row in stale_snapshot["payload"].get("rows", [])],
                    "stale_cache",
                    _snapshot_metadata(stale_snapshot, "stale_cache", source_key="ucs"),
                )
            ctx.emit.log(ctx.node_id, "warning", f"UCS URL fetch failed: {error}")
            return ([], "failed", None)

    ctx.emit.log(ctx.node_id, "warning", "No UCS CSV path or URL configured; skipping UCS source.")
    return ([], "skipped", None)


def normalize_space_track_satcat_row(item: dict[str, Any]) -> dict[str, Any]:
    country_code, country_name = normalize_country(_pick(item, "COUNTRY", "COUNTRY_CODE", "COUNTRY_NAME"))
    launch_date = _pick(item, "LAUNCH", "LAUNCH_DATE")
    return {
        "norad_id": _safe_int(_pick(item, "NORAD_CAT_ID", "NORAD")),
        "international_designator": _pick(item, "INTLDES", "INTL_DES"),
        "object_name": _pick(item, "OBJECT_NAME", "SATNAME"),
        "object_type": _pick(item, "OBJECT_TYPE", "TYPE"),
        "object_status": _pick(item, "OPS_STATUS_CODE", "STATUS"),
        "launch_date": launch_date,
        "launch_year": _launch_year(launch_date),
        "launch_site": _pick(item, "SITE", "LAUNCH_SITE"),
        "launch_vehicle": _pick(item, "LAUNCH_PIECE", "LAUNCH_VEHICLE"),
        "decay_date": _pick(item, "DECAY", "DECAY_DATE"),
        "country_code": country_code,
        "country_name": country_name,
        "radar_cross_section_m2": _safe_float(_pick(item, "RCS", "RCS_SIZE")),
        "raw": item,
    }


def normalize_space_track_gp_row(item: dict[str, Any]) -> dict[str, Any]:
    return _normalize_orbit_payload(item, {})


def normalize_celestrak_row(item: dict[str, Any], group: str) -> dict[str, Any]:
    row = _normalize_orbit_payload(item, {"group_name": group})
    row["object_name"] = _pick(item, "OBJECT_NAME", "OBJECT") or row.get("object_name")
    row["international_designator"] = _pick(item, "OBJECT_ID", "INTLDES", "INTL_DES") or row.get("international_designator")
    row["raw"] = item
    return row


def normalize_discos_row(item: dict[str, Any]) -> dict[str, Any]:
    attributes = item.get("attributes") if isinstance(item, dict) else {}
    relationships = item.get("relationships") if isinstance(item, dict) else {}
    mission = attributes.get("mission", {}) if isinstance(attributes, dict) else {}

    operator_country_code, operator_country_name = normalize_country(
        _pick(attributes, "operatorCountry", "operatorCountryCode", "operatorCountryName")
    )
    owner_country_code, owner_country_name = normalize_country(
        _pick(attributes, "ownerCountry", "ownerCountryCode", "ownerCountryName")
    )

    return {
        "norad_id": _safe_int(
            _pick(attributes, "satno", "noradId", "noradNumber")
            or _pick(item, "satno", "noradId")
        ),
        "international_designator": _pick(attributes, "cosparId", "cosparID", "intlDes"),
        "object_name": _pick(attributes, "name", "objectName"),
        "object_type": _pick(attributes, "objectClass"),
        "operator_name": _pick(attributes, "operatorName", "operator"),
        "operator_country_code": operator_country_code,
        "operator_country_name": operator_country_name,
        "owner_name": _pick(attributes, "ownerName", "owner"),
        "owner_country_code": owner_country_code,
        "owner_country_name": owner_country_name,
        "purpose_primary": _pick(attributes, "mission", "purpose", "missionClass"),
        "program_name": _pick(attributes, "programName", "program"),
        "manufacturer_name": _pick(attributes, "manufacturer", "manufacturerName"),
        "prime_contractor": _pick(attributes, "primeContractor", "contractor"),
        "bus_platform": _pick(attributes, "platform", "bus"),
        "dry_mass_kg": _safe_float(_pick(attributes, "dryMass", "mass")),
        "launch_mass_kg": _safe_float(_pick(attributes, "launchMass")),
        "dimensions_text": _pick(attributes, "shape", "dimensions"),
        "shape": _pick(attributes, "shape"),
        "design_life_years": _safe_float(_pick(attributes, "lifetime", "designLife")),
        "launch_provider": _pick(attributes, "launchProvider"),
        "launch_vehicle": _pick(attributes, "launchVehicle"),
        "civilian_military": _pick(attributes, "sector", "operatorType"),
        "relationships": relationships,
        "mission": mission,
        "raw": item,
    }


def normalize_ucs_row(item: dict[str, Any]) -> dict[str, Any]:
    operator_country_code, operator_country_name = normalize_country(
        _pick(item, "Operator/Owner", "Country of Operator/Owner", "Country")
    )
    return {
        "norad_id": _safe_int(_pick(item, "NORAD Number", "NORAD_CAT_ID")),
        "international_designator": _pick(item, "COSPAR Number", "International Designator", "COSPAR", "Intl. Des."),
        "object_name": _pick(item, "Current Official Name of Satellite", "Name of Satellite, Alternate Names"),
        "operator_name": _pick(item, "Operator/Owner"),
        "operator_country_code": operator_country_code,
        "operator_country_name": operator_country_name,
        "owner_name": _pick(item, "Operator/Owner"),
        "purpose_primary": _pick(item, "Purpose", "Users"),
        "mission_class": _pick(item, "Class of Orbit"),
        "launch_date": _pick(item, "Date of Launch"),
        "launch_vehicle": _pick(item, "Launch Vehicle"),
        "launch_provider": _pick(item, "Launch Site"),
        "dry_mass_kg": _safe_float(_pick(item, "Dry Mass (kg.)")),
        "launch_mass_kg": _safe_float(_pick(item, "Launch Mass (kg.)")),
        "expected_life_years": _safe_float(_pick(item, "Expected Lifetime (yrs.)")),
        "raw": item,
    }


async def _retry_request(
    operation: Any,
    attempts: int = 3,
    base_delay_s: float = 1.0,
    on_retry: Any | None = None,
) -> httpx.Response:
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            response = await operation()
            if response.status_code in {429, 500, 502, 503, 504} and attempt < attempts:
                delay_s = _retry_delay_s(response, attempt, base_delay_s)
                if on_retry is not None:
                    on_retry(attempt, delay_s, response.status_code)
                await asyncio.sleep(delay_s)
                continue
            return response
        except (httpx.HTTPError, httpx.TimeoutException) as error:
            last_error = error
            if attempt >= attempts:
                break
            delay_s = base_delay_s * attempt
            if on_retry is not None:
                on_retry(attempt, delay_s, None)
            await asyncio.sleep(delay_s)
    if last_error is not None:
        raise last_error
    raise RuntimeError("request retry loop failed without an error")


def _retry_delay_s(response: httpx.Response, attempt: int, base_delay_s: float) -> float:
    retry_after = response.headers.get("Retry-After")
    if retry_after:
        try:
            return max(float(retry_after), base_delay_s)
        except ValueError:
            pass
    return base_delay_s * (2 ** (attempt - 1))


def _parse_space_track_payload(payload: Any, label: str) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        error_message = _space_track_error_message(payload)
        if error_message:
            raise ValueError(f"Space-Track {label} request returned an API error: {error_message}")
        raise ValueError(f"Space-Track {label} request returned an unexpected object payload")

    if not isinstance(payload, list):
        raise ValueError(f"Space-Track {label} request returned an unexpected payload type")

    rows: list[dict[str, Any]] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        error_message = _space_track_error_message(item)
        if error_message:
            raise ValueError(f"Space-Track {label} request returned an API error: {error_message}")
        rows.append(item)
    return rows


def _space_track_error_message(payload: dict[str, Any]) -> str | None:
    for key in ("error", "Error", "message", "Message"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            lowered = value.lower()
            if "space-track" in lowered or "query rate limit" in lowered or "acceptable use" in lowered:
                return value.strip()
    return None


def _parse_ucs_csv(text: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    reader = csv.DictReader(StringIO(text))
    for row in reader:
        normalized = normalize_ucs_row(dict(row))
        if normalized.get("norad_id") is None and not normalized.get("international_designator"):
            continue
        rows.append(normalized)
    return rows


def _read_text_file_with_fallbacks(path: str) -> str:
    raw = open(path, "rb").read()
    for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _decode_csv_http_response(response: httpx.Response) -> str:
    if response.text is not None:
        return response.text

    raw = response.text_preview.encode("utf-8", errors="ignore")
    for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _normalize_orbit_payload(item: dict[str, Any], extra: dict[str, Any]) -> dict[str, Any]:
    mean_motion = _safe_float(_pick(item, "MEAN_MOTION"))
    period_min = round(1440.0 / mean_motion, 4) if mean_motion else None
    semi_major_axis = _semi_major_axis_km(mean_motion)
    eccentricity = _safe_float(_pick(item, "ECCENTRICITY"))
    perigee = _safe_float(_pick(item, "PERIGEE"))
    apogee = _safe_float(_pick(item, "APOGEE"))
    if perigee is None and semi_major_axis is not None and eccentricity is not None:
        perigee = round((semi_major_axis * (1 - eccentricity)) - 6378.137, 3)
    if apogee is None and semi_major_axis is not None and eccentricity is not None:
        apogee = round((semi_major_axis * (1 + eccentricity)) - 6378.137, 3)
    altitude = None
    if perigee is not None and apogee is not None:
        altitude = round((perigee + apogee) / 2, 3)

    return {
        "norad_id": _safe_int(_pick(item, "NORAD_CAT_ID", "NORAD")),
        "object_name": _pick(item, "OBJECT_NAME", "OBJECT"),
        "international_designator": _pick(item, "OBJECT_ID", "INTLDES", "INTL_DES"),
        "epoch_utc": _pick(item, "EPOCH"),
        "inclination_deg": _safe_float(_pick(item, "INCLINATION")),
        "eccentricity": eccentricity,
        "period_min": period_min,
        "mean_motion_rev_per_day": mean_motion,
        "semi_major_axis_km": semi_major_axis,
        "perigee_km": perigee,
        "apogee_km": apogee,
        "altitude_km": altitude,
        "raan_deg": _safe_float(_pick(item, "RA_OF_ASC_NODE", "RAAN")),
        "arg_perigee_deg": _safe_float(_pick(item, "ARG_OF_PERICENTER", "ARG_OF_PERIGEE")),
        "mean_anomaly_deg": _safe_float(_pick(item, "MEAN_ANOMALY")),
        "tle_line1": _pick(item, "TLE_LINE1", "LINE1"),
        "tle_line2": _pick(item, "TLE_LINE2", "LINE2"),
        **extra,
    }


def _pick(payload: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in payload and payload[key] not in {None, ""}:
            return payload[key]
    return None


def _safe_int(value: Any) -> int | None:
    if value in {None, ""}:
        return None
    try:
        return int(float(str(value).strip()))
    except ValueError:
        return None


def _safe_float(value: Any) -> float | None:
    if value in {None, ""}:
        return None
    try:
        return float(str(value).replace(",", "").strip())
    except ValueError:
        return None


def _batched(values: list[str], size: int) -> list[list[str]]:
    return [values[index : index + size] for index in range(0, len(values), size)]


def _launch_year(launch_date: str | None) -> int | None:
    if not launch_date:
        return None
    try:
        return int(str(launch_date)[:4])
    except ValueError:
        return None


def _semi_major_axis_km(mean_motion_rev_per_day: float | None) -> float | None:
    if not mean_motion_rev_per_day:
        return None
    mu = 398600.4418
    mean_motion_rad_s = mean_motion_rev_per_day * (2 * 3.141592653589793) / 86400
    return round((mu / (mean_motion_rad_s ** 2)) ** (1 / 3), 3)


def stage_rows(
    run_id: str,
    source_key: str,
    items: list[dict[str, Any]],
    *,
    status: str = "ok",
) -> list[dict[str, Any]]:
    created_at = utc_now()
    rows = []
    for item in items:
        rows.append(
            {
                "run_id": run_id,
                "norad_id": item.get("norad_id"),
                "source_key": source_key,
                "label": item.get("object_name") or item.get("group_name") or source_key,
                "status": status,
                "payload_json": json.dumps(item, separators=(",", ":"), default=str),
                "created_at_utc": created_at,
            }
        )
    return rows


def snapshot_stage_rows(run_id: str, snapshots: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for snapshot in snapshots:
        rows.append(
            {
                "run_id": run_id,
                "norad_id": None,
                "source_key": snapshot.get("source_key"),
                "label": snapshot.get("source_key"),
                "status": snapshot.get("status", "unknown"),
                "payload_json": json.dumps(snapshot, separators=(",", ":"), default=str),
                "created_at_utc": utc_now(),
            }
        )
    return rows


def _record_snapshot_state(
    source_key: str,
    status: str,
    snapshot: dict[str, Any] | None,
    cached_sources: list[str],
    stale_sources: list[str],
    source_snapshots: list[dict[str, Any]],
) -> None:
    if status in {"cached", "stale_cache"}:
        cached_sources.append(source_key)
    if status == "stale_cache":
        stale_sources.append(source_key)
    if snapshot:
        source_snapshots.append(snapshot)


def _load_snapshot(source_key: str, ttl_minutes: int | None) -> dict[str, Any] | None:
    path = db.cache_dir() / f"{source_key}.json"
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    expires_at = payload.get("expires_at")
    if ttl_minutes is None:
        return payload
    if expires_at and _parse_iso8601(expires_at) >= datetime.now(timezone.utc):
        return payload
    return None


def _write_snapshot(
    source_key: str,
    payload: dict[str, Any],
    *,
    ttl_minutes: int,
    source_url: str,
    record_count: int,
) -> dict[str, Any]:
    fetched_at = datetime.now(timezone.utc)
    snapshot = {
        "source_key": source_key,
        "source_url": source_url,
        "cache_path": str(db.cache_dir() / f"{source_key}.json"),
        "fetched_at": fetched_at.isoformat(),
        "expires_at": (fetched_at + timedelta(minutes=ttl_minutes)).isoformat(),
        "record_count": record_count,
        "payload": payload,
    }
    path = Path(snapshot["cache_path"])
    path.write_text(json.dumps(snapshot, separators=(",", ":"), default=str), encoding="utf-8")
    return snapshot


def _snapshot_metadata(
    snapshot: dict[str, Any] | None,
    status: str,
    *,
    source_key: str | None = None,
) -> dict[str, Any] | None:
    if not snapshot:
        return None
    expires_at = snapshot.get("expires_at")
    stale = bool(expires_at and _parse_iso8601(expires_at) < datetime.now(timezone.utc))
    return {
        "source_key": source_key or str(snapshot.get("source_key") or ""),
        "status": status,
        "cache_state": "stale" if stale else "fresh",
        "record_count": int(snapshot.get("record_count", 0)),
        "source_url": snapshot.get("source_url"),
        "cache_path": snapshot.get("cache_path"),
        "fetched_at": snapshot.get("fetched_at"),
        "expires_at": expires_at,
    }


def _parse_iso8601(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _dedupe_celestrak_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: dict[tuple[int | None, str | None], dict[str, Any]] = {}
    for row in rows:
        key = (row.get("norad_id"), row.get("group_name"))
        current = deduped.get(key)
        if current is None or _row_score(row) > _row_score(current):
            deduped[key] = row
    return list(deduped.values())


def _row_score(row: dict[str, Any]) -> int:
    return sum(
        1
        for field_name in (
            "object_name",
            "international_designator",
            "epoch_utc",
            "inclination_deg",
            "eccentricity",
            "period_min",
            "apogee_km",
            "perigee_km",
            "tle_line1",
            "tle_line2",
        )
        if row.get(field_name) not in {None, ""}
    )
