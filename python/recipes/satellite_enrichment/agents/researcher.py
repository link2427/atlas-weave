from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass
from typing import Any

from atlas_weave import Agent, AgentContext, AgentResult
from atlas_weave.tools.llm_tool import LLMTool
from recipes.satellite_enrichment import db
from recipes.satellite_enrichment.research_sources import EvidenceResult, gather_evidence
from recipes.satellite_enrichment.schema import LLM_ALLOWED_FIELDS, compute_completeness, utc_now


# Large constellations where all members share the same operator/manufacturer/purpose.
# Researching each satellite individually is wasteful — skip by default.
_DEFAULT_SKIP_CONSTELLATIONS = {"starlink", "oneweb"}


@dataclass(slots=True)
class WorkerOutcome:
    category_node_id: str
    category_label: str
    record: dict[str, Any]
    result_row: dict[str, Any]
    accepted: bool
    errored: bool
    status: str


class ResearchSwarm(Agent):
    name = "research_swarm"
    description = "Supervise a visible swarm of satellite research workers and aggregate their evidence."
    inputs = ["research_queue"]
    outputs = ["research_results"]

    async def execute(self, ctx: AgentContext) -> AgentResult:
        ctx.raise_if_cancelled()
        output_db_path = str(ctx.state["satellite_enrichment"]["db_path"])
        if not bool(ctx.config.get("enable_llm_research", True)):
            ctx.emit.progress(self.name, 1.0, "LLM research disabled")
            return AgentResult(summary={"skipped": True, "reason": "LLM research disabled by config"})

        max_research_records = int(ctx.config.get("max_research_records", 500))
        if max_research_records <= 0:
            ctx.emit.progress(self.name, 1.0, "LLM research disabled")
            return AgentResult(summary={"skipped": True, "reason": "max_research_records is 0"})

        provider = str(ctx.config.get("llm_provider", "openrouter"))
        model = str(ctx.config.get("llm_model", "anthropic/claude-haiku-4-5-20251001"))
        llm_tool = ctx.tools.llm
        if not isinstance(llm_tool, LLMTool) or not llm_tool.has_credentials(provider):
            ctx.state["_run_summary"] = {
                **ctx.state.get("_run_summary", {}),
                "research_candidates": 0,
                "researched_records": 0,
                "accepted_llm_records": 0,
                "llm_research_status": "skipped_missing_credentials",
            }
            ctx.emit.progress(self.name, 1.0, "LLM research skipped: missing credentials")
            return AgentResult(
                summary={
                    "skipped": True,
                    "reason": f"{provider} credentials are not configured",
                    "provider": provider,
                    "model": model,
                }
            )

        # Constellations to skip research for — these have thousands of identical satellites
        skip_constellations = set(ctx.config.get("skip_research_constellations", _DEFAULT_SKIP_CONSTELLATIONS))

        queue_rows = db.fetch_stage_payloads(output_db_path, "research_queue", ctx.run_id)
        all_payloads = [row["payload"] for row in queue_rows]
        skipped_count = 0
        if skip_constellations:
            filtered = []
            for payload in all_payloads:
                constellation = str(payload.get("record", {}).get("constellation_name") or "").lower()
                if constellation in skip_constellations:
                    skipped_count += 1
                else:
                    filtered.append(payload)
            all_payloads = filtered
        candidates = sorted(
            all_payloads,
            key=lambda item: tuple(item.get("priority", [0, 0.0, 0])),
        )[:max_research_records]
        if skipped_count:
            ctx.emit.log(
                self.name,
                "info",
                f"Skipped {skipped_count} satellites from constellations: {', '.join(sorted(skip_constellations))}",
            )
        if not candidates:
            ctx.state["_run_summary"] = {
                **ctx.state.get("_run_summary", {}),
                "research_candidates": len(queue_rows),
                "researched_records": 0,
                "accepted_llm_records": 0,
                "llm_research_status": "completed",
            }
            ctx.emit.log(self.name, "info", "Research swarm had no candidates to process.")
            ctx.emit.progress(self.name, 1.0, "Research swarm complete")
            return AgentResult(
                summary={
                    "provider": provider,
                    "model": model,
                    "research_candidates": len(queue_rows),
                    "started_workers": 0,
                    "completed_workers": 0,
                    "failed_workers": 0,
                    "accepted_llm_records": 0,
                    "search_provider_breakdown": {},
                    "llm_research_status": "completed",
                }
            )

        worker_limit = _bounded_concurrency(ctx.config.get("research_concurrency"), len(candidates), 12)
        llm_limit = _bounded_concurrency(ctx.config.get("llm_concurrency"), len(candidates), 4)
        worker_semaphore = asyncio.Semaphore(worker_limit)
        llm_semaphore = asyncio.Semaphore(llm_limit)
        confidence_threshold = float(ctx.config.get("llm_confidence_threshold", 0.7))
        shared_evidence: dict[str, list[EvidenceResult]] = {}
        category_plans = _plan_categories(candidates)

        ctx.emit.graph_patch(
            nodes=[
                {
                    "id": plan["node_id"],
                    "label": plan["label"],
                    "description": plan["description"],
                    "kind": "runtime",
                    "parent_id": "research_swarm",
                    "group_key": "research_swarm",
                    "collapsed_by_default": False,
                }
                for plan in category_plans.values()
            ],
            edges=[("research_swarm", plan["node_id"]) for plan in category_plans.values()],
        )
        for plan in category_plans.values():
            ctx.emit.node_started(str(plan["node_id"]))
            ctx.emit.progress(
                str(plan["node_id"]),
                0.0,
                f"Queued {plan['planned']} satellites for {plan['label']}",
            )

        ctx.emit.log(
            self.name,
            "info",
            (
                f"Starting research swarm with {len(candidates)} candidates across "
                f"{len(category_plans)} categories, worker concurrency {worker_limit}, "
                f"llm concurrency {llm_limit}."
            ),
        )

        tasks = [
            asyncio.create_task(
                _run_worker(
                    parent_ctx=ctx,
                    candidate=candidate,
                    provider=provider,
                    model=model,
                    llm_tool=llm_tool,
                    confidence_threshold=confidence_threshold,
                    worker_semaphore=worker_semaphore,
                    llm_semaphore=llm_semaphore,
                    category_plan=category_plans[_category_key(candidate)],
                    shared_evidence=shared_evidence,
                    ordinal=index,
                    total=len(candidates),
                )
            )
            for index, candidate in enumerate(candidates, start=1)
        ]

        completed = 0
        accepted_count = 0
        error_count = 0
        completed_workers = 0
        failed_workers = 0
        provider_breakdown: dict[str, int] = {}
        updated_satellites: list[dict[str, Any]] = []
        research_results: list[dict[str, Any]] = []
        category_state = {
            str(plan["node_id"]): {
                "node_id": str(plan["node_id"]),
                "label": str(plan["label"]),
                "planned": int(plan["planned"]),
                "completed": 0,
                "accepted": 0,
                "failed": 0,
                "no_evidence": 0,
            }
            for plan in category_plans.values()
        }

        for task in asyncio.as_completed(tasks):
            ctx.raise_if_cancelled()
            outcome = await task
            completed += 1
            updated_satellites.append(outcome.record)
            research_results.append(outcome.result_row)
            if outcome.accepted:
                accepted_count += 1
            if outcome.errored:
                error_count += 1
                failed_workers += 1
            else:
                completed_workers += 1
            provider_attempts = json.loads(outcome.result_row["payload_json"]).get("provider_attempts", [])
            for attempt in provider_attempts:
                provider_name = attempt.get("provider")
                if isinstance(provider_name, str):
                    provider_breakdown[provider_name] = provider_breakdown.get(provider_name, 0) + 1
            bucket = category_state[outcome.category_node_id]
            bucket["completed"] += 1
            if outcome.accepted:
                bucket["accepted"] += 1
            if outcome.errored:
                bucket["failed"] += 1
            if outcome.status == "no_evidence":
                bucket["no_evidence"] += 1
            ctx.emit.progress(
                bucket["node_id"],
                bucket["completed"] / max(1, bucket["planned"]),
                (
                    f"{bucket['label']}: {bucket['completed']}/{bucket['planned']} processed, "
                    f"{bucket['accepted']} accepted, {bucket['failed']} failed"
                ),
            )
            if bucket["completed"] == bucket["planned"]:
                ctx.emit.node_completed(
                    bucket["node_id"],
                    duration_ms=0,
                    summary={
                        "category": bucket["label"],
                        "planned_satellites": bucket["planned"],
                        "completed_satellites": bucket["completed"],
                        "accepted_llm_records": bucket["accepted"],
                        "failed_satellites": bucket["failed"],
                        "no_evidence_satellites": bucket["no_evidence"],
                    },
                )
            ctx.emit.progress(
                self.name,
                completed / max(1, len(candidates)),
                f"Research swarm processed {completed}/{len(candidates)} satellites",
            )

        if updated_satellites:
            db.upsert_satellites(output_db_path, updated_satellites)
        db.replace_stage_rows(output_db_path, "research_results", ctx.run_id, research_results)

        llm_status = "completed_with_errors" if error_count else "completed"
        ctx.state["_run_summary"] = {
            **ctx.state.get("_run_summary", {}),
            "research_candidates": len(queue_rows),
            "researched_records": len(candidates),
            "accepted_llm_records": accepted_count,
            "llm_research_status": llm_status,
            "search_provider_breakdown": provider_breakdown,
        }
        ctx.emit.log(
            self.name,
            "info",
            f"Research swarm finished {len(candidates)} workers; accepted {accepted_count}; worker failures {failed_workers}.",
        )
        ctx.emit.progress(self.name, 1.0, "Research swarm complete")
        return AgentResult(
            records_processed=len(candidates),
            records_updated=accepted_count,
            errors=error_count,
            summary={
                "provider": provider,
                "model": model,
                "research_candidates": len(queue_rows),
                "started_workers": len(candidates),
                "completed_workers": completed_workers,
                "failed_workers": failed_workers,
                "accepted_llm_records": accepted_count,
                "category_count": len(category_plans),
                "search_provider_breakdown": provider_breakdown,
                "llm_research_status": llm_status,
            },
        )


async def _run_worker(
    *,
    parent_ctx: AgentContext,
    candidate: dict[str, Any],
    provider: str,
    model: str,
    llm_tool: LLMTool,
    confidence_threshold: float,
    worker_semaphore: asyncio.Semaphore,
    llm_semaphore: asyncio.Semaphore,
    category_plan: dict[str, Any],
    shared_evidence: dict[str, list[EvidenceResult]],
    ordinal: int,
    total: int,
) -> WorkerOutcome:
    async with worker_semaphore:
        parent_ctx.raise_if_cancelled()
        record = dict(candidate["record"])
        norad_id = int(candidate["norad_id"])
        missing_fields = list(candidate.get("missing_fields") or [])
        conflict_fields = list(candidate.get("conflict_fields") or [])
        label = record.get("object_name") or str(norad_id)
        category_node_id = str(category_plan["node_id"])
        category_label = str(category_plan["label"])
        worker_ctx = AgentContext(
            run_id=parent_ctx.run_id,
            node_id=category_node_id,
            config=parent_ctx.config,
            db=parent_ctx.db,
            tools=parent_ctx.tools,
            emit=parent_ctx.emit,
            cancellation=parent_ctx.cancellation,
            state=parent_ctx.state,
        )
        worker_ctx.emit.log(
            category_node_id,
            "info",
            f"[{ordinal}/{total}] Researching {label} in {category_label}",
        )

        # Phase 1: Gather evidence from targeted sources
        evidence_results = await gather_evidence(
            worker_ctx, record, missing_fields, conflict_fields, shared_evidence
        )

        if not evidence_results:
            worker_ctx.emit.log(category_node_id, "warning", f"No evidence found for {label}")
            record["llm_research_status"] = "no_evidence"
            record["updated_at_utc"] = utc_now()
            return WorkerOutcome(
                category_node_id=category_node_id,
                category_label=category_label,
                record=record,
                accepted=False,
                errored=False,
                status="no_evidence",
                result_row={
                    "run_id": parent_ctx.run_id,
                    "norad_id": norad_id,
                    "source_key": provider,
                    "label": label,
                    "status": "no_evidence",
                    "payload_json": json.dumps(
                        {
                            "evidence_sources": [ev.source_name for ev in evidence_results],
                            "accepted": False,
                            "missing_fields": missing_fields,
                            "conflict_fields": conflict_fields,
                        },
                        separators=(",", ":"),
                    ),
                    "created_at_utc": utc_now(),
                },
            )

        # Phase 2: Pre-fill structured fields (e.g., from Wikipedia infobox)
        structured_fields: dict[str, Any] = {}
        for ev in evidence_results:
            for k, v in ev.structured_fields.items():
                if k not in structured_fields:
                    structured_fields[k] = v

        prefilled_fields: list[str] = []
        for field_name, value in _validated_fields(structured_fields).items():
            if record.get(field_name) in {None, ""}:
                record[field_name] = value
                prefilled_fields.append(field_name)

        remaining_missing = [f for f in missing_fields if f not in prefilled_fields]
        all_evidence_urls = [url for ev in evidence_results for url in ev.evidence_urls]

        # Phase 3: Skip LLM if all gaps filled by structured data
        if not remaining_missing and not conflict_fields:
            record["source_llm"] = json.dumps(
                {
                    "fields": sorted(prefilled_fields),
                    "source": "structured_evidence",
                    "confidence": 0.95,
                    "evidence_urls": all_evidence_urls,
                },
                separators=(",", ":"),
            )
            record["llm_research_status"] = "accepted"
            record["data_completeness_pct"] = compute_completeness(record)
            record["updated_at_utc"] = utc_now()
            worker_ctx.emit.log(
                category_node_id,
                "info",
                f"{label}: accepted with {len(prefilled_fields)} structured fields (no LLM needed)",
            )
            return WorkerOutcome(
                category_node_id=category_node_id,
                category_label=category_label,
                record=record,
                accepted=True,
                errored=False,
                status="accepted",
                result_row={
                    "run_id": parent_ctx.run_id,
                    "norad_id": norad_id,
                    "source_key": "structured_evidence",
                    "label": label,
                    "status": "accepted",
                    "payload_json": json.dumps(
                        {
                            "evidence_sources": [ev.source_name for ev in evidence_results],
                            "structured_fields": structured_fields,
                            "prefilled_fields": prefilled_fields,
                            "accepted": True,
                            "missing_fields": missing_fields,
                            "conflict_fields": conflict_fields,
                        },
                        separators=(",", ":"),
                    ),
                    "created_at_utc": utc_now(),
                },
            )

        # Phase 4: Call LLM for remaining gaps
        try:
            async with llm_semaphore:
                llm_output = await _call_llm_with_heartbeat(
                    ctx=worker_ctx,
                    provider=provider,
                    model=model,
                    llm_tool=llm_tool,
                    record=record,
                    missing_fields=remaining_missing,
                    conflict_fields=conflict_fields,
                    evidence_results=evidence_results,
                    label=label,
                    ordinal=ordinal,
                    total=total,
                )
        except Exception as error:  # noqa: BLE001
            # Even on LLM error, keep any structured pre-fills
            if prefilled_fields:
                record["source_llm"] = json.dumps(
                    {
                        "fields": sorted(prefilled_fields),
                        "source": "structured_evidence",
                        "confidence": 0.95,
                        "evidence_urls": all_evidence_urls,
                    },
                    separators=(",", ":"),
                )
                record["llm_research_status"] = "accepted"
                record["data_completeness_pct"] = compute_completeness(record)
                record["updated_at_utc"] = utc_now()
                worker_ctx.emit.log(
                    category_node_id,
                    "warning",
                    f"{label}: LLM failed but kept {len(prefilled_fields)} structured fields: {error}",
                )
                return WorkerOutcome(
                    category_node_id=category_node_id,
                    category_label=category_label,
                    record=record,
                    accepted=True,
                    errored=False,
                    status="accepted",
                    result_row={
                        "run_id": parent_ctx.run_id,
                        "norad_id": norad_id,
                        "source_key": "structured_evidence",
                        "label": label,
                        "status": "accepted",
                        "payload_json": json.dumps(
                            {
                                "evidence_sources": [ev.source_name for ev in evidence_results],
                                "prefilled_fields": prefilled_fields,
                                "llm_error": str(error),
                                "accepted": True,
                                "missing_fields": missing_fields,
                                "conflict_fields": conflict_fields,
                            },
                            separators=(",", ":"),
                        ),
                        "created_at_utc": utc_now(),
                    },
                )

            record["llm_research_status"] = "error"
            record["updated_at_utc"] = utc_now()
            worker_ctx.emit.log(category_node_id, "error", f"{label} failed: {error}")
            return WorkerOutcome(
                category_node_id=category_node_id,
                category_label=category_label,
                record=record,
                accepted=False,
                errored=True,
                status="error",
                result_row={
                    "run_id": parent_ctx.run_id,
                    "norad_id": norad_id,
                    "source_key": provider,
                    "label": label,
                    "status": "error",
                    "payload_json": json.dumps(
                        {
                            "evidence_sources": [ev.source_name for ev in evidence_results],
                            "error": str(error),
                            "missing_fields": missing_fields,
                            "conflict_fields": conflict_fields,
                        },
                        separators=(",", ":"),
                    ),
                    "created_at_utc": utc_now(),
                },
            )

        llm_payload = llm_output["output"]
        fields = dict(llm_payload.get("fields") or {})
        validated_fields = _validated_fields(fields)
        confidence = float(llm_payload.get("confidence", 0.0))
        accepted = confidence >= confidence_threshold and bool(validated_fields)

        # Merge LLM fields with pre-filled structured fields
        all_accepted_fields = dict(zip(prefilled_fields, [record[f] for f in prefilled_fields]))
        if accepted:
            for field_name, value in validated_fields.items():
                if record.get(field_name) in {None, ""}:
                    record[field_name] = value
                    all_accepted_fields[field_name] = value

        total_accepted = bool(all_accepted_fields)
        if total_accepted:
            evidence_urls = list(llm_payload.get("evidence_urls") or []) + all_evidence_urls
            record["source_llm"] = json.dumps(
                {
                    "fields": sorted(all_accepted_fields.keys()),
                    "confidence": max(confidence, 0.95) if prefilled_fields else confidence,
                    "evidence_urls": evidence_urls,
                },
                separators=(",", ":"),
            )
            record["llm_research_status"] = "accepted"
            record["data_completeness_pct"] = compute_completeness(record)
            status = "accepted"
        else:
            record["llm_research_status"] = "rejected"
            status = "rejected"

        record["updated_at_utc"] = utc_now()
        worker_ctx.emit.log(
            category_node_id,
            "info",
            f"{label}: {status} with {len(all_accepted_fields)} fields ({len(prefilled_fields)} structured, {len(validated_fields) if accepted else 0} LLM)",
        )

        return WorkerOutcome(
            category_node_id=category_node_id,
            category_label=category_label,
            record=record,
            accepted=total_accepted,
            errored=False,
            status=status,
            result_row={
                "run_id": parent_ctx.run_id,
                "norad_id": norad_id,
                "source_key": provider,
                "label": label,
                "status": status,
                "payload_json": json.dumps(
                    {
                        "evidence_sources": [ev.source_name for ev in evidence_results],
                        "structured_fields": structured_fields,
                        "prefilled_fields": prefilled_fields,
                        "llm_output": llm_payload,
                        "validated_fields": validated_fields,
                        "accepted": total_accepted,
                        "missing_fields": missing_fields,
                        "conflict_fields": conflict_fields,
                    },
                    separators=(",", ":"),
                ),
                "created_at_utc": utc_now(),
            },
        )


async def _call_llm_with_heartbeat(
    *,
    ctx: AgentContext,
    provider: str,
    model: str,
    llm_tool: LLMTool,
    record: dict[str, Any],
    missing_fields: list[str],
    conflict_fields: list[str],
    evidence_results: list[EvidenceResult],
    label: str,
    ordinal: int,
    total: int,
) -> dict[str, Any]:
    prompt = _build_llm_prompt(record, missing_fields, conflict_fields, evidence_results, label)
    task = asyncio.create_task(
        llm_tool.call(
            ctx,
            provider=provider,
            model=model,
            system=(
                "You enrich satellite metadata for Atlas Weave. "
                "Extract ONLY fields you can directly support from the evidence. "
                "Return factual JSON only — never guess or hallucinate values."
            ),
            messages=[{"role": "user", "content": prompt}],
            json_schema=_llm_schema(),
            max_tokens=600,
            temperature=0.1,
        )
    )

    heartbeat_count = 0
    while not task.done():
        try:
            return await asyncio.wait_for(asyncio.shield(task), timeout=5.0)
        except asyncio.TimeoutError:
            heartbeat_count += 1
            ctx.emit.log(
                ctx.node_id,
                "info",
                f"[{ordinal}/{total}] Waiting on {provider}:{model} for {label} ({heartbeat_count * 5}s).",
            )
    return await task


def _llm_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "confidence": {"type": "number"},
            "fields": {
                "type": "object",
                "properties": {
                    "operator_name": {"type": "string"},
                    "owner_name": {"type": "string"},
                    "purpose_primary": {"type": "string"},
                    "purpose_secondary": {"type": "string"},
                    "manufacturer_name": {"type": "string"},
                    "bus_platform": {"type": "string"},
                    "dry_mass_kg": {"type": "number"},
                    "design_life_years": {"type": "number"},
                    "program_name": {"type": "string"},
                    "constellation_name": {"type": "string"},
                    "operator_country_code": {"type": "string"},
                    "operator_country_name": {"type": "string"},
                    "owner_country_code": {"type": "string"},
                    "owner_country_name": {"type": "string"},
                    "mission_class": {"type": "string"},
                    "operator_type": {"type": "string"},
                    "civilian_military": {"type": "string"},
                    "object_type": {"type": "string"},
                    "launch_date": {"type": "string"},
                },
                "additionalProperties": False,
            },
            "evidence_urls": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["confidence", "fields", "evidence_urls"],
        "additionalProperties": False,
    }


_ORBITAL_FIELDS = {
    "tle_line1", "tle_line2", "inclination_deg", "eccentricity", "period_min",
    "mean_motion_rev_per_day", "semi_major_axis_km", "perigee_km", "apogee_km",
    "altitude_km", "raan_deg", "arg_perigee_deg", "mean_anomaly_deg", "epoch_utc",
    "source_space_track", "source_discos", "source_ucs", "source_celestrak",
    "source_llm", "data_completeness_pct", "enrichment_confidence",
    "created_at_utc", "updated_at_utc", "last_verified_at_utc",
    "llm_research_status", "radar_cross_section_m2", "alternate_names_json",
}


def _slim_record(record: dict[str, Any]) -> dict[str, Any]:
    """Strip orbital/TLE/stage fields — the LLM doesn't need them."""
    return {k: v for k, v in record.items() if k not in _ORBITAL_FIELDS and v not in {None, ""}}


def _build_llm_prompt(
    record: dict[str, Any],
    missing_fields: list[str],
    conflict_fields: list[str],
    evidence_results: list[EvidenceResult],
    label: str,
) -> str:
    """Build a structured LLM prompt with evidence sections."""
    norad_id = record.get("norad_id", "unknown")
    slim = _slim_record(record)
    slim_json = json.dumps(slim, indent=2, default=str)

    missing_bullets = "\n".join(f"- {f}" for f in missing_fields) if missing_fields else "- (none)"
    conflict_bullets = "\n".join(f"- {f}" for f in conflict_fields) if conflict_fields else "- (none)"

    evidence_sections: list[str] = []
    for ev in evidence_results:
        if ev.scraped_text:
            urls = ", ".join(ev.evidence_urls) if ev.evidence_urls else "N/A"
            # Limit each source to 1500 chars
            text = ev.scraped_text[:1500]
            evidence_sections.append(f"### {ev.source_name.title()} ({urls})\n{text}")

    evidence_text = "\n\n".join(evidence_sections) if evidence_sections else "(no evidence available)"

    return f"""You are enriching satellite metadata for **{label}** (NORAD {norad_id}).

## Current Record (relevant fields only)
```json
{slim_json}
```

## Fields Needed
{missing_bullets}

## Conflicting Fields
{conflict_bullets}

## Evidence Sources
{evidence_text}

Extract ONLY fields you can directly support from the evidence above.
Set confidence 0.9+ if evidence directly states values,
0.7–0.9 if strongly implied, below 0.7 if uncertain.
Include evidence_urls for each source you used."""


# CelesTrak meta-groups that shouldn't be used as categories — they're aggregation groups, not classifications.
_META_CELESTRAK_GROUPS = {
    "active", "visual", "analyst", "tle-new", "last-30-days",
    "active-geo", "geo-protected", "other",
}

# Mapping from CelesTrak group slugs to human-readable labels
_CELESTRAK_GROUP_LABELS: dict[str, str] = {
    "stations": "Space Stations",
    "weather": "Weather",
    "noaa": "NOAA",
    "goes": "GOES",
    "resource": "Earth Resources",
    "earth-resources": "Earth Resources",
    "sarsat": "Search & Rescue (SARSAT)",
    "dmc": "Disaster Monitoring",
    "tdrss": "Tracking & Data Relay",
    "argos": "ARGOS",
    "planet": "Planet Labs",
    "spire": "Spire",
    "geo": "Geostationary",
    "intelsat": "Intelsat",
    "intelsat-geo": "Intelsat GEO",
    "ses": "SES",
    "iridium": "Iridium",
    "starlink": "Starlink",
    "oneweb": "OneWeb",
    "orbcomm": "Orbcomm",
    "globalstar": "Globalstar",
    "amateur": "Amateur Radio",
    "x-comm": "Experimental Comms",
    "other-comm": "Other Comms",
    "communications": "Communications",
    "gps-ops": "GPS",
    "glo-ops": "GLONASS",
    "galileo": "Galileo",
    "beidou": "BeiDou",
    "gnss": "GNSS",
    "navigation": "Navigation",
    "satnogs": "SatNOGS",
    "cubesat": "CubeSats",
    "education": "Education",
    "engineering": "Engineering",
    "geodetic": "Geodetic",
    "science": "Science",
    "radar": "Radar",
    "military": "Military",
    "musson": "Musson",
}


def _category_key(candidate: dict[str, Any]) -> str:
    """Derive a category key from CelesTrak groups first, then fall back to record fields."""
    record = candidate.get("record", candidate)
    celestrak_groups = list(candidate.get("celestrak_groups") or [])

    if record.get("is_debris"):
        return "orbital_debris"
    object_name = str(record.get("object_name") or "").upper()
    object_type = str(record.get("object_type") or "").upper()
    if "R/B" in object_name or "ROCKET" in object_type:
        return "rocket_bodies"

    # Use the most specific CelesTrak group as the category
    specific_groups = [g for g in celestrak_groups if g not in _META_CELESTRAK_GROUPS]
    if specific_groups:
        # Prefer the most specific (shortest) group name
        best = sorted(specific_groups, key=len)[0]
        return f"celestrak_{_slugify(best)}"

    # Fall back to constellation_name from the record
    constellation_name = str(record.get("constellation_name") or "").strip().lower()
    if constellation_name and constellation_name not in _META_CELESTRAK_GROUPS:
        return f"celestrak_{_slugify(constellation_name)}"

    # Last resort: orbit class grouping
    orbit_class = str(record.get("orbit_class") or "").strip().upper() or "UNKNOWN"
    return f"other_{orbit_class.lower()}"


def _category_label(candidate: dict[str, Any]) -> str:
    key = _category_key(candidate)
    if key == "orbital_debris":
        return "Orbital Debris"
    if key == "rocket_bodies":
        return "Rocket Bodies"
    if key.startswith("celestrak_"):
        slug = key[len("celestrak_"):]
        # Check the label map
        for group_slug, label in _CELESTRAK_GROUP_LABELS.items():
            if _slugify(group_slug) == slug:
                return label
        # Fall back to titleizing the slug
        return slug.replace("_", " ").title()
    if key.startswith("other_"):
        orbit_class = key[len("other_"):].upper()
        return f"Other {orbit_class}"
    return key.replace("_", " ").title()


def _plan_categories(candidates: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    plans: dict[str, dict[str, Any]] = {}
    for candidate in candidates:
        key = _category_key(candidate)
        if key not in plans:
            label = _category_label(candidate)
            plans[key] = {
                "node_id": f"research_category_{_slugify(key)}",
                "label": label,
                "description": f"Research bucket for {label}",
                "planned": 0,
            }
        plans[key]["planned"] = int(plans[key]["planned"]) + 1
    return plans


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    return slug or "unknown"


def _bounded_concurrency(value: Any, candidate_count: int, default: int) -> int:
    try:
        parsed = int(value) if value not in {None, ""} else default
    except (TypeError, ValueError):
        parsed = default
    return max(1, min(parsed, max(1, candidate_count), 24))


def _validated_fields(fields: dict[str, Any]) -> dict[str, Any]:
    validated: dict[str, Any] = {}
    for field_name, value in fields.items():
        if field_name not in LLM_ALLOWED_FIELDS:
            continue
        if field_name in {"dry_mass_kg", "design_life_years"}:
            try:
                numeric = float(value)
            except (TypeError, ValueError):
                continue
            if field_name == "dry_mass_kg" and not (1 <= numeric <= 50000):
                continue
            if field_name == "design_life_years" and not (0 < numeric <= 50):
                continue
            validated[field_name] = round(numeric, 3)
            continue
        if field_name.endswith("_country_code"):
            text = str(value).strip().upper()
            if len(text) in {2, 3} and text.isalpha():
                validated[field_name] = text
            continue
        if isinstance(value, str) and value.strip():
            validated[field_name] = value.strip()
    return validated
