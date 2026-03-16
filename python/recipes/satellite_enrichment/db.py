from __future__ import annotations

import json
import shutil
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from atlas_weave.runtime import data_dir
from recipes.satellite_enrichment.schema import (
    SQLITE_COLUMN_TYPES,
    EnrichedSatellite,
    QualityFinding,
    RunManifest,
    field_names,
)

RECIPE_NAME = "satellite_enrichment"


def recipe_dir() -> Path:
    path = data_dir() / "recipes" / RECIPE_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def runs_dir() -> Path:
    path = recipe_dir() / "runs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def cache_dir() -> Path:
    path = recipe_dir() / "cache"
    path.mkdir(parents=True, exist_ok=True)
    return path


def run_db_path(run_id: str) -> Path:
    path = runs_dir() / run_id / f"{RECIPE_NAME}.sqlite"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def latest_db_path() -> Path:
    return recipe_dir() / "latest.sqlite"


@contextmanager
def connect(db_path: str | Path) -> Iterator[sqlite3.Connection]:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def initialize_database(db_path: str | Path) -> None:
    with connect(db_path) as conn:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA foreign_keys = ON")
        _create_satellites_table(conn)
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS run_manifest (
                run_id TEXT PRIMARY KEY,
                recipe_name TEXT NOT NULL,
                output_db_path TEXT NOT NULL,
                latest_db_path TEXT NOT NULL,
                total_records INTEGER NOT NULL DEFAULT 0,
                active_records INTEGER NOT NULL DEFAULT 0,
                research_candidates INTEGER NOT NULL DEFAULT 0,
                researched_records INTEGER NOT NULL DEFAULT 0,
                accepted_llm_records INTEGER NOT NULL DEFAULT 0,
                anomaly_count INTEGER NOT NULL DEFAULT 0,
                source_breakdown_json TEXT NOT NULL DEFAULT '{}',
                source_status_json TEXT NOT NULL DEFAULT '{}',
                cached_sources_json TEXT NOT NULL DEFAULT '[]',
                stale_sources_json TEXT NOT NULL DEFAULT '[]',
                space_track_mode TEXT NOT NULL DEFAULT 'prefer_cache',
                field_completion_rates_json TEXT NOT NULL DEFAULT '{}',
                created_at_utc TEXT NOT NULL,
                updated_at_utc TEXT NOT NULL
            )
            """
        )
        _ensure_run_manifest_columns(conn)
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS field_coverage (
                run_id TEXT NOT NULL,
                field_name TEXT NOT NULL,
                populated_records INTEGER NOT NULL,
                coverage_pct REAL NOT NULL,
                PRIMARY KEY (run_id, field_name)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS quality_findings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                norad_id INTEGER,
                severity TEXT NOT NULL,
                code TEXT NOT NULL,
                message TEXT NOT NULL,
                created_at_utc TEXT NOT NULL
            )
            """
        )
        for table_name in (
            "stage_space_track_satcat",
            "stage_space_track_gp",
            "stage_celestrak_satcat",
            "stage_discos",
            "stage_ucs",
            "research_queue",
            "research_results",
            "source_snapshots",
            "unresolved_identities",
        ):
            conn.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {table_name} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL,
                    norad_id INTEGER,
                    source_key TEXT,
                    label TEXT,
                    status TEXT,
                    payload_json TEXT NOT NULL,
                    created_at_utc TEXT NOT NULL
                )
                """
            )
            conn.execute(
                f"CREATE INDEX IF NOT EXISTS idx_{table_name}_run_id ON {table_name}(run_id)"
            )
            conn.execute(
                f"CREATE INDEX IF NOT EXISTS idx_{table_name}_norad_id ON {table_name}(norad_id)"
            )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS merge_lineage (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                norad_id INTEGER NOT NULL,
                field_name TEXT NOT NULL,
                chosen_source TEXT,
                chosen_value_json TEXT,
                candidate_values_json TEXT NOT NULL DEFAULT '[]',
                conflict_count INTEGER NOT NULL DEFAULT 0,
                created_at_utc TEXT NOT NULL
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_merge_lineage_run_id ON merge_lineage(run_id)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_merge_lineage_norad_id ON merge_lineage(norad_id)"
        )


def insert_stage_rows(
    db_path: str | Path,
    table_name: str,
    rows: list[dict[str, Any]],
) -> int:
    if not rows:
        return 0
    with connect(db_path) as conn:
        conn.executemany(
            f"""
            INSERT INTO {table_name} (run_id, norad_id, source_key, label, status, payload_json, created_at_utc)
            VALUES (:run_id, :norad_id, :source_key, :label, :status, :payload_json, :created_at_utc)
            """,
            rows,
        )
    return len(rows)


def replace_stage_rows(
    db_path: str | Path,
    table_name: str,
    run_id: str,
    rows: list[dict[str, Any]],
) -> int:
    with connect(db_path) as conn:
        conn.execute(f"DELETE FROM {table_name} WHERE run_id = ?", [run_id])
        if rows:
            conn.executemany(
                f"""
                INSERT INTO {table_name} (run_id, norad_id, source_key, label, status, payload_json, created_at_utc)
                VALUES (:run_id, :norad_id, :source_key, :label, :status, :payload_json, :created_at_utc)
                """,
                rows,
            )
    return len(rows)


def fetch_stage_payloads(
    db_path: str | Path,
    table_name: str,
    run_id: str,
) -> list[dict[str, Any]]:
    with connect(db_path) as conn:
        rows = conn.execute(
            f"""
            SELECT norad_id, source_key, label, status, payload_json, created_at_utc
            FROM {table_name}
            WHERE run_id = ?
            ORDER BY id ASC
            """,
            [run_id],
        ).fetchall()
    payloads = []
    for row in rows:
        payload = json.loads(row["payload_json"])
        payloads.append(
            {
                "norad_id": row["norad_id"],
                "source_key": row["source_key"],
                "label": row["label"],
                "status": row["status"],
                "created_at_utc": row["created_at_utc"],
                "payload": payload,
            }
        )
    return payloads


def upsert_satellites(db_path: str | Path, satellites: list[dict[str, Any]]) -> int:
    if not satellites:
        return 0
    columns = field_names()
    assignments = ", ".join(
        f"{column} = excluded.{column}" for column in columns if column != "norad_id"
    )
    sql = (
        f"INSERT INTO satellites ({', '.join(columns)}) "
        f"VALUES ({', '.join('?' for _ in columns)}) "
        f"ON CONFLICT(norad_id) DO UPDATE SET {assignments}"
    )
    normalized_rows = [EnrichedSatellite.model_validate(satellite).model_dump(mode="python") for satellite in satellites]
    with connect(db_path) as conn:
        conn.executemany(sql, [[row.get(column) for column in columns] for row in normalized_rows])
    return len(normalized_rows)


def fetch_satellites(db_path: str | Path) -> list[dict[str, Any]]:
    with connect(db_path) as conn:
        rows = conn.execute("SELECT * FROM satellites ORDER BY norad_id ASC").fetchall()
    return [dict(row) for row in rows]


def fetch_satellite(db_path: str | Path, norad_id: int) -> dict[str, Any] | None:
    with connect(db_path) as conn:
        row = conn.execute("SELECT * FROM satellites WHERE norad_id = ?", [norad_id]).fetchone()
    return dict(row) if row else None


def upsert_manifest(db_path: str | Path, manifest: dict[str, Any]) -> None:
    row = RunManifest.model_validate(manifest).model_dump(mode="python")
    columns = list(row.keys())
    assignments = ", ".join(
        f"{column} = excluded.{column}" for column in columns if column != "run_id"
    )
    with connect(db_path) as conn:
        conn.execute(
            f"""
            INSERT INTO run_manifest ({', '.join(columns)})
            VALUES ({', '.join('?' for _ in columns)})
            ON CONFLICT(run_id) DO UPDATE SET {assignments}
            """,
            [row[column] for column in columns],
        )


def replace_field_coverage(
    db_path: str | Path,
    run_id: str,
    coverage_rows: list[dict[str, Any]],
) -> None:
    with connect(db_path) as conn:
        conn.execute("DELETE FROM field_coverage WHERE run_id = ?", [run_id])
        if coverage_rows:
            conn.executemany(
                """
                INSERT INTO field_coverage (run_id, field_name, populated_records, coverage_pct)
                VALUES (:run_id, :field_name, :populated_records, :coverage_pct)
                """,
                coverage_rows,
            )


def replace_quality_findings(
    db_path: str | Path,
    run_id: str,
    findings: list[dict[str, Any]],
) -> None:
    with connect(db_path) as conn:
        conn.execute("DELETE FROM quality_findings WHERE run_id = ?", [run_id])
        if findings:
            normalized = [QualityFinding.model_validate(finding).model_dump(mode="python") for finding in findings]
            conn.executemany(
                """
                INSERT INTO quality_findings (run_id, norad_id, severity, code, message, created_at_utc)
                VALUES (:run_id, :norad_id, :severity, :code, :message, :created_at_utc)
                """,
                normalized,
            )


def replace_merge_lineage(
    db_path: str | Path,
    run_id: str,
    rows: list[dict[str, Any]],
) -> int:
    with connect(db_path) as conn:
        conn.execute("DELETE FROM merge_lineage WHERE run_id = ?", [run_id])
        if rows:
            conn.executemany(
                """
                INSERT INTO merge_lineage (
                    run_id,
                    norad_id,
                    field_name,
                    chosen_source,
                    chosen_value_json,
                    candidate_values_json,
                    conflict_count,
                    created_at_utc
                )
                VALUES (
                    :run_id,
                    :norad_id,
                    :field_name,
                    :chosen_source,
                    :chosen_value_json,
                    :candidate_values_json,
                    :conflict_count,
                    :created_at_utc
                )
                """,
                rows,
            )
    return len(rows)


def promote_latest(db_path: str | Path) -> Path:
    source_path = Path(db_path)
    target_path = latest_db_path()
    target_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = target_path.with_suffix(".tmp")
    shutil.copy2(source_path, temp_path)
    temp_path.replace(target_path)
    return target_path


def _create_satellites_table(conn: sqlite3.Connection) -> None:
    columns = ",\n                ".join(
        f"{column} {column_type}" for column, column_type in SQLITE_COLUMN_TYPES.items()
    )
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS satellites (
                {columns}
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_satellites_international_designator ON satellites(international_designator)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_satellites_object_name ON satellites(object_name)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_satellites_operator_name ON satellites(operator_name)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_satellites_constellation_name ON satellites(constellation_name)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_satellites_active_status ON satellites(active_status)"
    )


def _ensure_run_manifest_columns(conn: sqlite3.Connection) -> None:
    existing_columns = {
        str(row["name"])
        for row in conn.execute("PRAGMA table_info(run_manifest)").fetchall()
    }
    required_columns = {
        "source_status_json": "TEXT NOT NULL DEFAULT '{}'",
        "cached_sources_json": "TEXT NOT NULL DEFAULT '[]'",
        "stale_sources_json": "TEXT NOT NULL DEFAULT '[]'",
        "space_track_mode": "TEXT NOT NULL DEFAULT 'prefer_cache'",
    }
    for column_name, column_sql in required_columns.items():
        if column_name not in existing_columns:
            conn.execute(f"ALTER TABLE run_manifest ADD COLUMN {column_name} {column_sql}")
