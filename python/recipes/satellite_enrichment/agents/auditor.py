from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone

from atlas_weave import Agent, AgentContext, AgentResult
from recipes.satellite_enrichment import db
from recipes.satellite_enrichment.schema import COMPLETENESS_FIELDS, compute_completeness, utc_now


class QualityAuditor(Agent):
    name = "quality_auditor"
    description = "Validate enriched rows, compute coverage metrics, and publish the final output DB manifest."
    inputs = ["merged_satellites", "research_results"]
    outputs = ["audit_summary"]

    async def execute(self, ctx: AgentContext) -> AgentResult:
        ctx.raise_if_cancelled()
        output_db_path = str(ctx.state["satellite_enrichment"]["db_path"])
        satellites = db.fetch_satellites(output_db_path)
        findings: list[dict[str, object]] = []
        updated_rows: list[dict[str, object]] = []
        seen_norad_ids: set[int] = set()

        for index, satellite in enumerate(satellites, start=1):
            ctx.raise_if_cancelled()
            norad_id = int(satellite["norad_id"])
            if norad_id in seen_norad_ids:
                findings.append(_finding(ctx.run_id, norad_id, "error", "duplicate_norad_id", f"Duplicate NORAD id {norad_id}"))
            seen_norad_ids.add(norad_id)

            findings.extend(_validate_satellite(ctx.run_id, satellite))
            completeness = compute_completeness(satellite)
            satellite["data_completeness_pct"] = completeness
            satellite["enrichment_confidence"] = _enrichment_confidence(satellite, completeness)
            satellite["updated_at_utc"] = utc_now()
            satellite["last_verified_at_utc"] = utc_now()
            updated_rows.append(satellite)

            if index % 1000 == 0:
                ctx.emit.progress(self.name, min(0.95, index / max(1, len(satellites))), f"Audited {index}/{len(satellites)} satellites")

        db.upsert_satellites(output_db_path, updated_rows)
        coverage_rows, coverage_json = _field_coverage(ctx.run_id, updated_rows)
        db.replace_field_coverage(output_db_path, ctx.run_id, coverage_rows)
        db.replace_quality_findings(output_db_path, ctx.run_id, findings)
        latest_path = db.promote_latest(output_db_path)

        operator_and_purpose = sum(
            1
            for row in updated_rows
            if row.get("operator_name") not in {None, ""} and row.get("purpose_primary") not in {None, ""}
        )
        mass_coverage = sum(1 for row in updated_rows if row.get("dry_mass_kg") not in {None, ""})
        source_breakdown = Counter()
        for row in updated_rows:
            for source_name in ("source_space_track", "source_discos", "source_ucs", "source_celestrak", "source_llm"):
                if row.get(source_name):
                    source_breakdown[source_name] += 1

        manifest = {
            "run_id": ctx.run_id,
            "recipe_name": db.RECIPE_NAME,
            "output_db_path": str(output_db_path),
            "latest_db_path": str(latest_path),
            "total_records": len(updated_rows),
            "active_records": sum(1 for row in updated_rows if row.get("active_status") == "active"),
            "research_candidates": int(ctx.state.get("_run_summary", {}).get("research_candidates", 0)),
            "researched_records": int(ctx.state.get("_run_summary", {}).get("researched_records", 0)),
            "accepted_llm_records": int(ctx.state.get("_run_summary", {}).get("accepted_llm_records", 0)),
            "anomaly_count": len(findings),
            "source_breakdown_json": json.dumps(dict(source_breakdown), separators=(",", ":")),
            "source_status_json": json.dumps(ctx.state.get("_run_summary", {}).get("source_status", {}), separators=(",", ":")),
            "cached_sources_json": json.dumps(ctx.state.get("_run_summary", {}).get("cached_sources", []), separators=(",", ":")),
            "stale_sources_json": json.dumps(ctx.state.get("_run_summary", {}).get("stale_sources", []), separators=(",", ":")),
            "space_track_mode": str(ctx.state.get("_run_summary", {}).get("space_track_mode", "prefer_cache")),
            "field_completion_rates_json": json.dumps(coverage_json, separators=(",", ":")),
            "created_at_utc": utc_now(),
            "updated_at_utc": utc_now(),
        }
        db.upsert_manifest(output_db_path, manifest)
        for finding in findings[:20]:
            ctx.emit.log(self.name, "warning", str(finding["message"]))

        summary = {
            "output_db_path": str(output_db_path),
            "latest_db_path": str(latest_path),
            "total_records": len(updated_rows),
            "active_records": manifest["active_records"],
            "research_candidates": manifest["research_candidates"],
            "researched_records": manifest["researched_records"],
            "accepted_llm_records": manifest["accepted_llm_records"],
            "source_status": ctx.state.get("_run_summary", {}).get("source_status", {}),
            "cached_sources": ctx.state.get("_run_summary", {}).get("cached_sources", []),
            "stale_sources": ctx.state.get("_run_summary", {}).get("stale_sources", []),
            "space_track_mode": manifest["space_track_mode"],
            "llm_research_status": ctx.state.get("_run_summary", {}).get("llm_research_status"),
            "coverage_operator_purpose_pct": round((operator_and_purpose / max(1, len(updated_rows))) * 100, 2),
            "coverage_mass_pct": round((mass_coverage / max(1, len(updated_rows))) * 100, 2),
            "field_completion_rates": coverage_json,
            "source_breakdown": dict(source_breakdown),
            "anomaly_count": len(findings),
        }
        ctx.state["_run_summary"] = {**ctx.state.get("_run_summary", {}), **summary}
        ctx.emit.progress(self.name, 1.0, "Quality audit complete")
        return AgentResult(records_processed=len(updated_rows), records_updated=len(updated_rows), errors=len(findings), summary=summary)


def _validate_satellite(run_id: str, satellite: dict[str, object]) -> list[dict[str, object]]:
    findings: list[dict[str, object]] = []
    if satellite.get("inclination_deg") is not None and not (0 <= float(satellite["inclination_deg"]) <= 180):
        findings.append(_finding(run_id, satellite["norad_id"], "warning", "invalid_inclination", "Inclination is outside the valid 0-180 range"))
    if satellite.get("eccentricity") is not None and not (0 <= float(satellite["eccentricity"]) < 1):
        findings.append(_finding(run_id, satellite["norad_id"], "warning", "invalid_eccentricity", "Eccentricity is outside the valid 0-1 range"))
    if satellite.get("perigee_km") is not None and satellite.get("apogee_km") is not None:
        if float(satellite["perigee_km"]) > float(satellite["apogee_km"]):
            findings.append(_finding(run_id, satellite["norad_id"], "warning", "invalid_orbit_bounds", "Perigee exceeds apogee"))
    for date_field in ("launch_date", "decay_date", "last_contact_date"):
        value = satellite.get(date_field)
        if value and not _is_reasonable_date(str(value)):
            findings.append(_finding(run_id, satellite["norad_id"], "warning", f"invalid_{date_field}", f"{date_field} is not a plausible ISO date"))
    for code_field in ("operator_country_code", "owner_country_code", "launch_site_country_code"):
        value = satellite.get(code_field)
        if value and not str(value).isalpha():
            findings.append(_finding(run_id, satellite["norad_id"], "warning", f"invalid_{code_field}", f"{code_field} should be alphabetic"))
    return findings


def _field_coverage(run_id: str, rows: list[dict[str, object]]) -> tuple[list[dict[str, object]], dict[str, float]]:
    coverage_rows = []
    coverage_json: dict[str, float] = {}
    total = max(1, len(rows))
    for field_name in COMPLETENESS_FIELDS:
        populated = sum(
            1
            for row in rows
            if row.get(field_name) not in {None, ""} and not (isinstance(row.get(field_name), str) and not str(row.get(field_name)).strip())
        )
        coverage_pct = round((populated / total) * 100, 2)
        coverage_rows.append(
            {
                "run_id": run_id,
                "field_name": field_name,
                "populated_records": populated,
                "coverage_pct": coverage_pct,
            }
        )
        coverage_json[field_name] = coverage_pct
    return (coverage_rows, coverage_json)


def _enrichment_confidence(satellite: dict[str, object], completeness: float) -> float:
    source_llm = satellite.get("source_llm")
    if source_llm:
        try:
            llm_payload = json.loads(str(source_llm))
            llm_confidence = float(llm_payload.get("confidence", 0.0))
            return round((completeness + llm_confidence) / 2, 4)
        except (json.JSONDecodeError, TypeError, ValueError):
            pass
    return round(min(1.0, 0.25 + completeness * 0.75), 4)


def _finding(run_id: str, norad_id: object | None, severity: str, code: str, message: str) -> dict[str, object]:
    return {
        "run_id": run_id,
        "norad_id": norad_id,
        "severity": severity,
        "code": code,
        "message": message,
        "created_at_utc": utc_now(),
    }


def _is_reasonable_date(value: str) -> bool:
    candidate = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError:
        return False
    return 1957 <= parsed.year <= datetime.now(timezone.utc).year + 1
