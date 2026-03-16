from __future__ import annotations

from atlas_weave import Agent, AgentContext, AgentResult
from recipes.satellite_enrichment import db
from recipes.satellite_enrichment.schema import utc_now
from recipes.satellite_enrichment.sources import fetch_source_bundle, snapshot_stage_rows, stage_rows


class StructuredDataCollector(Agent):
    name = "structured_data_collector"
    description = "Collect and stage structured satellite data from Space-Track, CelesTrak, DISCOS, and UCS."
    outputs = ["staged_sources"]

    async def execute(self, ctx: AgentContext) -> AgentResult:
        ctx.raise_if_cancelled()
        output_db_path = db.run_db_path(ctx.run_id)
        latest_db_path = db.latest_db_path()
        db.initialize_database(output_db_path)

        ctx.state["satellite_enrichment"] = {
            "db_path": str(output_db_path),
            "latest_db_path": str(latest_db_path),
        }

        bundle = await fetch_source_bundle(ctx)
        source_counts = bundle.counts()
        staged_records = 0
        staged_records += db.insert_stage_rows(
            output_db_path,
            "stage_space_track_satcat",
            stage_rows(ctx.run_id, "space_track_satcat", bundle.space_track_satcat),
        )
        staged_records += db.insert_stage_rows(
            output_db_path,
            "stage_space_track_gp",
            stage_rows(ctx.run_id, "space_track_gp", bundle.space_track_gp),
        )
        staged_records += db.insert_stage_rows(
            output_db_path,
            "stage_celestrak_satcat",
            stage_rows(ctx.run_id, "celestrak_satcat", bundle.celestrak_satcat),
        )
        staged_records += db.insert_stage_rows(
            output_db_path,
            "stage_discos",
            stage_rows(ctx.run_id, "discos", bundle.discos),
        )
        staged_records += db.insert_stage_rows(
            output_db_path,
            "stage_ucs",
            stage_rows(ctx.run_id, "ucs", bundle.ucs, status=bundle.source_status.get("ucs", "ok")),
        )
        staged_records += db.insert_stage_rows(
            output_db_path,
            "source_snapshots",
            snapshot_stage_rows(ctx.run_id, bundle.source_snapshots),
        )

        ctx.state["_run_summary"] = {
            **ctx.state.get("_run_summary", {}),
            "source_status": bundle.source_status,
            "cached_sources": bundle.cached_sources,
            "stale_sources": bundle.stale_sources,
            "space_track_mode": str(ctx.config.get("space_track_mode", "prefer_cache")),
        }

        now = utc_now()
        db.upsert_manifest(
            output_db_path,
            {
                "run_id": ctx.run_id,
                "recipe_name": db.RECIPE_NAME,
                "output_db_path": str(output_db_path),
                "latest_db_path": str(latest_db_path),
                "source_breakdown_json": "{}",
                "source_status_json": "{}",
                "cached_sources_json": "[]",
                "stale_sources_json": "[]",
                "space_track_mode": str(ctx.config.get("space_track_mode", "prefer_cache")),
                "field_completion_rates_json": "{}",
                "created_at_utc": now,
                "updated_at_utc": now,
            },
        )
        ctx.emit.log(
            self.name,
            "info",
            (
                f"Staged {staged_records} source records "
                f"(Space-Track SATCAT {source_counts['space_track_satcat']}, "
                f"GP {source_counts['space_track_gp']}, "
                f"CelesTrak {source_counts['celestrak_satcat']}, "
                f"DISCOS {source_counts['discos']}, UCS {source_counts['ucs']})."
            ),
        )
        ctx.emit.progress(self.name, 1.0, "Structured source collection complete")
        return AgentResult(
            records_processed=staged_records,
            records_created=staged_records,
            summary={
                "output_db_path": str(output_db_path),
                "latest_db_path": str(latest_db_path),
                "source_counts": source_counts,
                "source_status": bundle.source_status,
                "cached_sources": bundle.cached_sources,
                "stale_sources": bundle.stale_sources,
                "space_track_mode": str(ctx.config.get("space_track_mode", "prefer_cache")),
            },
        )
