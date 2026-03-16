from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from atlas_weave.context import AgentContext
from atlas_weave.tool import Tool, run_tool_operation


class SQLiteTool(Tool):
    name = "sqlite"
    description = "Execute recipe-local SQLite queries against explicit database paths."

    async def call(
        self,
        ctx: AgentContext,
        *,
        action: str,
        db_path: str,
        sql: str | None = None,
        parameters: list[Any] | None = None,
        table: str | None = None,
        values: dict[str, Any] | None = None,
        key_columns: list[str] | None = None,
    ) -> Any:
        node_id = ctx.node_id
        input_payload = {
            "action": action,
            "db_path": db_path,
            "sql": sql,
            "table": table,
            "key_columns": key_columns or [],
        }

        async def operation() -> Any:
            if action == "execute":
                return self._execute(db_path, sql or "", parameters or [])
            if action == "fetch_all":
                return self._fetch_all(db_path, sql or "", parameters or [])
            if action == "fetch_one":
                return self._fetch_one(db_path, sql or "", parameters or [])
            if action == "upsert":
                if table is None or values is None or key_columns is None:
                    raise ValueError("upsert requires table, values, and key_columns")
                return self._upsert(db_path, table, values, key_columns)
            raise ValueError(f"unsupported sqlite action: {action}")

        return await run_tool_operation(
            ctx=ctx,
            node_id=node_id,
            tool_name=self.name,
            input_payload=input_payload,
            operation=operation,
            serialize_result=lambda result: result,
        )

    async def execute(
        self,
        ctx: AgentContext,
        *,
        db_path: str,
        sql: str,
        parameters: list[Any] | None = None,
    ) -> dict[str, Any]:
        return await self.call(
            ctx,
            action="execute",
            db_path=db_path,
            sql=sql,
            parameters=parameters,
        )

    async def fetch_all(
        self,
        ctx: AgentContext,
        *,
        db_path: str,
        sql: str,
        parameters: list[Any] | None = None,
    ) -> list[dict[str, Any]]:
        return await self.call(
            ctx,
            action="fetch_all",
            db_path=db_path,
            sql=sql,
            parameters=parameters,
        )

    async def fetch_one(
        self,
        ctx: AgentContext,
        *,
        db_path: str,
        sql: str,
        parameters: list[Any] | None = None,
    ) -> dict[str, Any] | None:
        return await self.call(
            ctx,
            action="fetch_one",
            db_path=db_path,
            sql=sql,
            parameters=parameters,
        )

    async def upsert(
        self,
        ctx: AgentContext,
        *,
        db_path: str,
        table: str,
        values: dict[str, Any],
        key_columns: list[str],
    ) -> dict[str, Any]:
        return await self.call(
            ctx,
            action="upsert",
            db_path=db_path,
            table=table,
            values=values,
            key_columns=key_columns,
        )

    def _execute(self, db_path: str, sql: str, parameters: list[Any]) -> dict[str, Any]:
        with _connect(db_path) as conn:
            cursor = conn.execute(sql, parameters)
            conn.commit()
            return {"rows_affected": cursor.rowcount}

    def _fetch_all(
        self,
        db_path: str,
        sql: str,
        parameters: list[Any],
    ) -> list[dict[str, Any]]:
        with _connect(db_path) as conn:
            rows = conn.execute(sql, parameters).fetchall()
        return [dict(row) for row in rows]

    def _fetch_one(
        self,
        db_path: str,
        sql: str,
        parameters: list[Any],
    ) -> dict[str, Any] | None:
        with _connect(db_path) as conn:
            row = conn.execute(sql, parameters).fetchone()
        return dict(row) if row is not None else None

    def _upsert(
        self,
        db_path: str,
        table: str,
        values: dict[str, Any],
        key_columns: list[str],
    ) -> dict[str, Any]:
        columns = list(values.keys())
        non_key_columns = [column for column in columns if column not in key_columns]
        placeholders = ", ".join("?" for _ in columns)
        assignments = ", ".join(
            f"{column} = excluded.{column}" for column in non_key_columns
        )
        sql = (
            f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders}) "
            f"ON CONFLICT({', '.join(key_columns)}) DO UPDATE SET {assignments}"
        )
        with _connect(db_path) as conn:
            conn.execute(sql, [values[column] for column in columns])
            conn.commit()
        return {"table": table, "key_columns": key_columns, "values": values}


def _connect(db_path: str) -> sqlite3.Connection:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn
