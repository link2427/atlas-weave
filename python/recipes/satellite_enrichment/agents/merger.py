from __future__ import annotations

import json
from collections import Counter, defaultdict
from typing import Any

from atlas_weave import Agent, AgentContext, AgentResult
from recipes.satellite_enrichment import db
from recipes.satellite_enrichment.schema import (
    EnrichedSatellite,
    LLM_ALLOWED_FIELDS,
    compute_completeness,
    derive_constellation_name,
    derive_orbit_class,
    normalize_country,
    utc_now,
)

IDENTITY_FIELDS = ("international_designator", "object_name")
ORBIT_FIELDS = (
    "epoch_utc",
    "inclination_deg",
    "eccentricity",
    "period_min",
    "mean_motion_rev_per_day",
    "semi_major_axis_km",
    "perigee_km",
    "apogee_km",
    "altitude_km",
    "raan_deg",
    "arg_perigee_deg",
    "mean_anomaly_deg",
    "tle_line1",
    "tle_line2",
)
SPACE_TRACK_FIELDS = (
    "object_type",
    "object_status",
    "launch_date",
    "launch_year",
    "launch_site",
    "launch_vehicle",
    "launch_site_country_code",
    "decay_date",
    "radar_cross_section_m2",
)
UCS_OWNERSHIP_FIELDS = (
    "operator_name",
    "operator_country_code",
    "operator_country_name",
    "owner_name",
    "owner_country_code",
    "owner_country_name",
    "purpose_primary",
    "mission_class",
)
DISCOS_OWNERSHIP_FIELDS = (
    "operator_name",
    "operator_country_code",
    "operator_country_name",
    "owner_name",
    "owner_country_code",
    "owner_country_name",
    "purpose_primary",
    "program_name",
    "civilian_military",
    "operator_type",
)
DISCOS_PHYSICAL_FIELDS = (
    "manufacturer_name",
    "prime_contractor",
    "bus_platform",
    "dry_mass_kg",
    "launch_mass_kg",
    "dimensions_text",
    "shape",
    "design_life_years",
    "launch_provider",
    "launch_vehicle",
)
UCS_PHYSICAL_FIELDS = (
    "dry_mass_kg",
    "launch_mass_kg",
    "expected_life_years",
    "launch_provider",
    "launch_vehicle",
)
PROTECTED_FIELDS = {
    "norad_id",
    "international_designator",
    "epoch_utc",
    "inclination_deg",
    "eccentricity",
    "period_min",
    "mean_motion_rev_per_day",
    "semi_major_axis_km",
    "perigee_km",
    "apogee_km",
    "altitude_km",
    "raan_deg",
    "arg_perigee_deg",
    "mean_anomaly_deg",
    "tle_line1",
    "tle_line2",
}


class RecordMerger(Agent):
    name = "record_merger"
    description = "Merge staged source records into the canonical enriched satellite table."
    inputs = ["staged_sources"]
    outputs = ["merged_satellites", "research_queue"]

    async def execute(self, ctx: AgentContext) -> AgentResult:
        ctx.raise_if_cancelled()
        output_db_path = _db_path(ctx)
        satcat_rows = db.fetch_stage_payloads(output_db_path, "stage_space_track_satcat", ctx.run_id)
        gp_rows = db.fetch_stage_payloads(output_db_path, "stage_space_track_gp", ctx.run_id)
        celestrak_rows = db.fetch_stage_payloads(output_db_path, "stage_celestrak_satcat", ctx.run_id)
        discos_rows = db.fetch_stage_payloads(output_db_path, "stage_discos", ctx.run_id)
        ucs_rows = db.fetch_stage_payloads(output_db_path, "stage_ucs", ctx.run_id)

        intldes_to_norad = _build_intldes_index([satcat_rows, gp_rows, celestrak_rows, discos_rows, ucs_rows])
        unresolved_rows: list[dict[str, Any]] = []
        satcat_by_norad = _index_rows(satcat_rows, "space_track_satcat", intldes_to_norad, unresolved_rows, ctx.run_id)
        gp_by_norad = _index_rows(gp_rows, "space_track_gp", intldes_to_norad, unresolved_rows, ctx.run_id)
        celestrak_by_norad = _index_rows(celestrak_rows, "celestrak", intldes_to_norad, unresolved_rows, ctx.run_id)
        discos_by_norad = _index_rows(discos_rows, "discos", intldes_to_norad, unresolved_rows, ctx.run_id)
        ucs_by_norad = _index_rows(ucs_rows, "ucs", intldes_to_norad, unresolved_rows, ctx.run_id)

        candidate_norad_ids = sorted(
            set(satcat_by_norad) | set(gp_by_norad) | set(celestrak_by_norad) | set(discos_by_norad) | set(ucs_by_norad)
        )
        record_limit = _record_limit(ctx)
        if record_limit:
            candidate_norad_ids = candidate_norad_ids[:record_limit]

        merged_rows: list[dict[str, Any]] = []
        research_queue_rows: list[dict[str, Any]] = []
        lineage_rows: list[dict[str, Any]] = []
        completeness_buckets = Counter()
        threshold = float(ctx.config.get("completeness_threshold", 0.5))

        for index, norad_id in enumerate(candidate_norad_ids, start=1):
            ctx.raise_if_cancelled()
            merged, source_fields, candidate_values, conflict_fields, celestrak_groups = _merge_satellite_record(
                norad_id=norad_id,
                satcat_rows=satcat_by_norad.get(norad_id, []),
                gp_rows=gp_by_norad.get(norad_id, []),
                celestrak_rows=celestrak_by_norad.get(norad_id, []),
                discos_rows=discos_by_norad.get(norad_id, []),
                ucs_rows=ucs_by_norad.get(norad_id, []),
            )

            completeness = compute_completeness(merged)
            merged["data_completeness_pct"] = completeness
            completeness_buckets[_bucket_label(completeness)] += 1
            merged["source_space_track"] = json.dumps(sorted(source_fields["space_track"])) if source_fields["space_track"] else None
            merged["source_discos"] = json.dumps(sorted(source_fields["discos"])) if source_fields["discos"] else None
            merged["source_ucs"] = json.dumps(sorted(source_fields["ucs"])) if source_fields["ucs"] else None
            merged["source_celestrak"] = json.dumps(sorted(source_fields["celestrak"])) if source_fields["celestrak"] else None
            merged_rows.append(EnrichedSatellite.model_validate(merged).model_dump(mode="python"))
            lineage_rows.extend(_build_lineage_rows(ctx.run_id, norad_id, merged, candidate_values))

            missing_fields = sorted(_missing_llm_fields(merged))
            if _needs_research(merged, threshold, missing_fields, conflict_fields):
                research_queue_rows.append(
                    {
                        "run_id": ctx.run_id,
                        "norad_id": norad_id,
                        "source_key": "research_candidate",
                        "label": merged.get("object_name") or str(norad_id),
                        "status": "queued",
                        "payload_json": json.dumps(
                            {
                                "norad_id": norad_id,
                                "priority": _research_priority(merged, missing_fields, conflict_fields),
                                "missing_fields": missing_fields,
                                "conflict_fields": conflict_fields,
                                "record": merged,
                                "celestrak_groups": celestrak_groups,
                            },
                            separators=(",", ":"),
                        ),
                        "created_at_utc": utc_now(),
                    }
                )

            if index % 500 == 0:
                ctx.emit.progress(self.name, min(0.95, index / max(1, len(candidate_norad_ids))), f"Merged {index}/{len(candidate_norad_ids)} satellites")

        db.upsert_satellites(output_db_path, merged_rows)
        db.replace_stage_rows(output_db_path, "research_queue", ctx.run_id, research_queue_rows)
        db.replace_stage_rows(output_db_path, "unresolved_identities", ctx.run_id, unresolved_rows)
        db.replace_merge_lineage(output_db_path, ctx.run_id, lineage_rows)

        now = utc_now()
        db.upsert_manifest(
            output_db_path,
            {
                "run_id": ctx.run_id,
                "recipe_name": db.RECIPE_NAME,
                "output_db_path": str(output_db_path),
                "latest_db_path": ctx.state["satellite_enrichment"]["latest_db_path"],
                "total_records": len(merged_rows),
                "active_records": sum(1 for merged in merged_rows if merged.get("active_status") == "active"),
                "research_candidates": len(research_queue_rows),
                "source_breakdown_json": json.dumps(
                    {
                        "space_track_satcat": len(satcat_rows),
                        "space_track_gp": len(gp_rows),
                        "celestrak_satcat": len(celestrak_rows),
                        "discos": len(discos_rows),
                        "ucs": len(ucs_rows),
                    },
                    separators=(",", ":"),
                ),
                "source_status_json": json.dumps(ctx.state.get("_run_summary", {}).get("source_status", {}), separators=(",", ":")),
                "cached_sources_json": json.dumps(ctx.state.get("_run_summary", {}).get("cached_sources", []), separators=(",", ":")),
                "stale_sources_json": json.dumps(ctx.state.get("_run_summary", {}).get("stale_sources", []), separators=(",", ":")),
                "space_track_mode": str(ctx.config.get("space_track_mode", "prefer_cache")),
                "field_completion_rates_json": "{}",
                "created_at_utc": now,
                "updated_at_utc": now,
            },
        )
        ctx.state["_run_summary"] = {
            **ctx.state.get("_run_summary", {}),
            "merged_records": len(merged_rows),
            "research_candidates": len(research_queue_rows),
            "unresolved_records": len(unresolved_rows),
        }
        ctx.emit.log(self.name, "info", f"Merged {len(merged_rows)} satellites and queued {len(research_queue_rows)} for research.")
        ctx.emit.progress(self.name, 1.0, "Record merge complete")
        return AgentResult(
            records_processed=len(candidate_norad_ids),
            records_created=len(merged_rows),
            records_updated=len(research_queue_rows),
            summary={
                "merged_records": len(merged_rows),
                "research_candidates": len(research_queue_rows),
                "unresolved_records": len(unresolved_rows),
                "completeness_distribution": dict(completeness_buckets),
            },
        )


def _db_path(ctx: AgentContext) -> str:
    return str(ctx.state["satellite_enrichment"]["db_path"])


def _record_limit(ctx: AgentContext) -> int | None:
    value = ctx.config.get("record_limit")
    if value in {None, ""}:
        return None
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return None


def _build_intldes_index(sources: list[list[dict[str, Any]]]) -> dict[str, int]:
    mapping: dict[str, int] = {}
    for rows in sources:
        for row in rows:
            payload = row["payload"]
            norad_id = payload.get("norad_id")
            intldes = payload.get("international_designator")
            if norad_id is None or intldes in {None, ""}:
                continue
            mapping[str(intldes).strip().upper()] = int(norad_id)
    return mapping


def _index_rows(
    rows: list[dict[str, Any]],
    source_name: str,
    intldes_to_norad: dict[str, int],
    unresolved_rows: list[dict[str, Any]],
    run_id: str,
) -> dict[int, list[dict[str, Any]]]:
    indexed: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        payload = dict(row["payload"])
        norad_id = payload.get("norad_id")
        if norad_id is None:
            intldes = str(payload.get("international_designator") or "").strip().upper()
            norad_id = intldes_to_norad.get(intldes) if intldes else None
        if norad_id is None:
            unresolved_rows.append(
                {
                    "run_id": run_id,
                    "norad_id": None,
                    "source_key": source_name,
                    "label": payload.get("object_name") or payload.get("international_designator") or source_name,
                    "status": "unresolved",
                    "payload_json": json.dumps(
                        {
                            "reason": "missing_norad_identity",
                            "payload": payload,
                        },
                        separators=(",", ":"),
                    ),
                    "created_at_utc": utc_now(),
                }
            )
            continue
        payload["norad_id"] = int(norad_id)
        indexed[int(norad_id)].append(payload)
    return indexed


def _merge_satellite_record(
    *,
    norad_id: int,
    satcat_rows: list[dict[str, Any]],
    gp_rows: list[dict[str, Any]],
    celestrak_rows: list[dict[str, Any]],
    discos_rows: list[dict[str, Any]],
    ucs_rows: list[dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, set[str]], dict[str, list[dict[str, Any]]], list[str]]:
    record = _blank_record(norad_id)
    source_fields = {name: set() for name in ("space_track", "discos", "ucs", "celestrak")}
    candidate_values: dict[str, list[dict[str, Any]]] = defaultdict(list)

    best_celestrak = _best_row(celestrak_rows)
    if best_celestrak:
        _merge_fields(record, source_fields, candidate_values, "celestrak", best_celestrak, IDENTITY_FIELDS + ORBIT_FIELDS)

    best_satcat = _best_row(satcat_rows)
    if best_satcat:
        _merge_fields(record, source_fields, candidate_values, "space_track", best_satcat, IDENTITY_FIELDS + SPACE_TRACK_FIELDS)

    best_gp = _best_row(gp_rows)
    if best_gp:
        _merge_fields(record, source_fields, candidate_values, "space_track", best_gp, ORBIT_FIELDS)

    best_ucs = _best_row(ucs_rows)
    if best_ucs:
        _merge_fields(record, source_fields, candidate_values, "ucs", best_ucs, UCS_OWNERSHIP_FIELDS)

    best_discos = _best_row(discos_rows)
    if best_discos:
        _merge_fields(record, source_fields, candidate_values, "discos", best_discos, DISCOS_OWNERSHIP_FIELDS)
        _merge_fields(record, source_fields, candidate_values, "discos", best_discos, DISCOS_PHYSICAL_FIELDS)

    if best_ucs:
        _merge_fields(record, source_fields, candidate_values, "ucs", best_ucs, UCS_PHYSICAL_FIELDS)

    groups = sorted({row.get("group_name") for row in celestrak_rows if row.get("group_name")})
    if groups:
        source_fields["celestrak"].add("group_name")
    constellation_name = derive_constellation_name(record.get("object_name"), groups)
    if constellation_name:
        _merge_fields(record, source_fields, candidate_values, "celestrak", {"constellation_name": constellation_name}, ("constellation_name",))

    if constellation_name:
        from recipes.satellite_enrichment.constellation_templates import CONSTELLATION_TEMPLATES
        template = CONSTELLATION_TEMPLATES.get(constellation_name.lower())
        if template:
            for field_name, value in template.items():
                if record.get(field_name) in {None, ""}:
                    record[field_name] = value
                    source_fields["celestrak"].add(field_name)

    _finalize_derived_fields(record)
    conflict_fields = _conflict_fields(candidate_values)
    return (record, source_fields, candidate_values, conflict_fields, groups)


def _blank_record(norad_id: int) -> dict[str, Any]:
    created_at = utc_now()
    return {
        "norad_id": norad_id,
        "alternate_names_json": json.dumps([], separators=(",", ":")),
        "created_at_utc": created_at,
        "updated_at_utc": created_at,
        "last_verified_at_utc": None,
        "llm_research_status": "not_started",
    }


def _best_row(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not rows:
        return None
    return max(rows, key=_row_score)


def _row_score(row: dict[str, Any]) -> int:
    score = 0
    for value in row.values():
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        if isinstance(value, (list, dict)) and not value:
            continue
        score += 1
    return score


def _merge_fields(
    record: dict[str, Any],
    source_fields: dict[str, set[str]],
    candidate_values: dict[str, list[dict[str, Any]]],
    source_name: str,
    payload: dict[str, Any],
    fields: tuple[str, ...],
) -> None:
    for field_name in fields:
        value = payload.get(field_name)
        if value in {None, ""}:
            continue
        candidate_values[field_name].append({"source": source_name, "value": value})
        if record.get(field_name) in {None, ""}:
            record[field_name] = value
            source_fields[source_name].add(field_name)


def _finalize_derived_fields(record: dict[str, Any]) -> None:
    if record.get("object_type") in {None, ""}:
        name_upper = str(record.get("object_name") or "").upper()
        if "DEB" in name_upper:
            record["object_type"] = "DEBRIS"
        elif "R/B" in name_upper:
            record["object_type"] = "ROCKET BODY"
        elif name_upper:
            record["object_type"] = "PAYLOAD"

    if record.get("launch_date") in {None, ""} and record.get("international_designator"):
        intldes = str(record["international_designator"]).strip()
        if len(intldes) >= 4:
            try:
                year = int(intldes[:4])
                if 1957 <= year <= 2030:
                    record["launch_date"] = f"{year}-01-01"
                    if record.get("launch_year") in {None, ""}:
                        record["launch_year"] = year
            except ValueError:
                pass

    object_type = str(record.get("object_type") or "").upper()
    record["is_debris"] = "DEB" in object_type or "DEBRIS" in object_type
    object_name = str(record.get("object_name") or "").upper()
    record["is_crewed"] = any(keyword in object_name for keyword in ("CREW", "DRAGON", "SOYUZ", "STARLINER"))
    if record.get("active_status") in {None, ""}:
        if record.get("decay_date"):
            record["active_status"] = "decayed"
        elif record.get("tle_line1"):
            record["active_status"] = "active"
        elif record["is_debris"]:
            record["active_status"] = "inactive"
        else:
            record["active_status"] = "unknown"
    record["orbit_class"] = derive_orbit_class(record.get("altitude_km"))

    for prefix in ("operator", "owner"):
        code_key = f"{prefix}_country_code"
        name_key = f"{prefix}_country_name"
        code, name = normalize_country(record.get(code_key) or record.get(name_key))
        if code and not record.get(code_key):
            record[code_key] = code
        if name and not record.get(name_key):
            record[name_key] = name


def _build_lineage_rows(
    run_id: str,
    norad_id: int,
    record: dict[str, Any],
    candidate_values: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for field_name, candidates in candidate_values.items():
        chosen_value = record.get(field_name)
        chosen_source = None
        for candidate in candidates:
            if candidate.get("value") == chosen_value:
                chosen_source = candidate.get("source")
                break
        unique_values = {json.dumps(candidate.get("value"), sort_keys=True, default=str) for candidate in candidates}
        rows.append(
            {
                "run_id": run_id,
                "norad_id": norad_id,
                "field_name": field_name,
                "chosen_source": chosen_source,
                "chosen_value_json": json.dumps(chosen_value, separators=(",", ":"), default=str),
                "candidate_values_json": json.dumps(candidates, separators=(",", ":"), default=str),
                "conflict_count": max(0, len(unique_values) - 1),
                "created_at_utc": utc_now(),
            }
        )
    return rows


def _missing_llm_fields(record: dict[str, Any]) -> set[str]:
    return {
        field_name
        for field_name in LLM_ALLOWED_FIELDS
        if field_name not in PROTECTED_FIELDS and record.get(field_name) in {None, ""}
    }


def _conflict_fields(candidate_values: dict[str, list[dict[str, Any]]]) -> list[str]:
    conflicts: list[str] = []
    for field_name, candidates in candidate_values.items():
        unique_values = {json.dumps(candidate.get("value"), sort_keys=True, default=str) for candidate in candidates}
        if len(unique_values) > 1:
            conflicts.append(field_name)
    return sorted(conflicts)


def _needs_research(
    record: dict[str, Any],
    threshold: float,
    missing_fields: list[str],
    conflict_fields: list[str],
) -> bool:
    return (
        float(record.get("data_completeness_pct", 0.0)) < threshold
        or bool(missing_fields)
        or bool(conflict_fields)
    )


def _research_priority(record: dict[str, Any], missing_fields: list[str], conflict_fields: list[str]) -> list[float]:
    active_score = -1 if record.get("active_status") == "active" else 0
    completeness = float(record.get("data_completeness_pct", 0.0))
    return [active_score, -len(missing_fields), -len(conflict_fields), completeness, int(record["norad_id"])]


def _bucket_label(completeness: float) -> str:
    if completeness < 0.25:
        return "0-25%"
    if completeness < 0.5:
        return "25-50%"
    if completeness < 0.75:
        return "50-75%"
    return "75-100%"
