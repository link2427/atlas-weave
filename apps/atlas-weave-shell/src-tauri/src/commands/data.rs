use std::collections::HashSet;
use std::fs::File;
use std::io::{BufWriter, Write};
use std::path::PathBuf;

use rusqlite::{Connection, OpenFlags};
use serde::{Deserialize, Serialize};
use serde_json::Value;

use crate::services::paths;
use crate::{AppError, AppResult};

const DEFAULT_PAGE: u32 = 1;
const DEFAULT_PAGE_SIZE: u32 = 100;

#[derive(Debug, Clone, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct ColumnFilter {
    pub column: String,
    pub operator: String,
    pub value: Option<String>,
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct ColumnInfo {
    pub name: String,
    pub data_type: String,
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct QueryResultDto {
    pub columns: Vec<ColumnInfo>,
    pub rows: Vec<Vec<Value>>,
    pub total: i64,
    pub page: u32,
    pub page_size: u32,
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct TableInfoDto {
    pub name: String,
    pub row_count: i64,
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct ExportResultDto {
    pub rows_exported: i64,
    pub file_path: String,
}

fn open_readonly(db_path: &str) -> AppResult<Connection> {
    let conn = Connection::open_with_flags(db_path, OpenFlags::SQLITE_OPEN_READ_ONLY)?;
    Ok(conn)
}

fn get_table_names(conn: &Connection) -> AppResult<HashSet<String>> {
    let mut stmt = conn.prepare(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'",
    )?;
    let names: HashSet<String> = stmt
        .query_map([], |row| row.get::<_, String>(0))?
        .filter_map(|r| r.ok())
        .collect();
    Ok(names)
}

fn get_column_info(conn: &Connection, table: &str) -> AppResult<Vec<ColumnInfo>> {
    let mut stmt = conn.prepare(&format!("PRAGMA table_info(\"{}\")", table))?;
    let columns: Vec<ColumnInfo> = stmt
        .query_map([], |row| {
            Ok(ColumnInfo {
                name: row.get::<_, String>(1)?,
                data_type: row.get::<_, String>(2)?,
            })
        })?
        .filter_map(|r| r.ok())
        .collect();
    Ok(columns)
}

fn validate_table(conn: &Connection, table: &str) -> AppResult<()> {
    let tables = get_table_names(conn)?;
    if !tables.contains(table) {
        return Err(AppError::Message(format!("table not found: {table}")));
    }
    Ok(())
}

fn validate_column(columns: &[ColumnInfo], name: &str) -> AppResult<()> {
    if !columns.iter().any(|c| c.name == name) {
        return Err(AppError::Message(format!("column not found: {name}")));
    }
    Ok(())
}

fn sqlite_value_to_json(val: rusqlite::types::Value) -> Value {
    match val {
        rusqlite::types::Value::Null => Value::Null,
        rusqlite::types::Value::Integer(i) => Value::Number(i.into()),
        rusqlite::types::Value::Real(f) => {
            serde_json::Number::from_f64(f).map_or(Value::Null, Value::Number)
        }
        rusqlite::types::Value::Text(s) => Value::String(s),
        rusqlite::types::Value::Blob(b) => {
            Value::String(format!("<blob {} bytes>", b.len()))
        }
    }
}

struct WhereClause {
    sql: String,
    params: Vec<Box<dyn rusqlite::types::ToSql>>,
}

fn build_where(
    columns: &[ColumnInfo],
    search: &Option<String>,
    filters: &Option<Vec<ColumnFilter>>,
) -> AppResult<WhereClause> {
    let mut conditions: Vec<String> = Vec::new();
    let mut params: Vec<Box<dyn rusqlite::types::ToSql>> = Vec::new();

    if let Some(ref term) = search {
        if !term.is_empty() {
            let search_conditions: Vec<String> = columns
                .iter()
                .map(|c| format!("CAST(\"{}\" AS TEXT) LIKE ?", c.name))
                .collect();
            let pattern = format!("%{term}%");
            for _ in &search_conditions {
                params.push(Box::new(pattern.clone()));
            }
            conditions.push(format!("({})", search_conditions.join(" OR ")));
        }
    }

    if let Some(ref filter_list) = filters {
        for f in filter_list {
            validate_column(columns, &f.column)?;
            let col = format!("\"{}\"", f.column);

            match f.operator.as_str() {
                "is_null" => {
                    conditions.push(format!("{col} IS NULL"));
                }
                "is_not_null" => {
                    conditions.push(format!("{col} IS NOT NULL"));
                }
                "eq" => {
                    conditions.push(format!("{col} = ?"));
                    params.push(Box::new(f.value.clone().unwrap_or_default()));
                }
                "neq" => {
                    conditions.push(format!("{col} != ?"));
                    params.push(Box::new(f.value.clone().unwrap_or_default()));
                }
                "contains" => {
                    conditions.push(format!("CAST({col} AS TEXT) LIKE ?"));
                    params.push(Box::new(format!(
                        "%{}%",
                        f.value.as_deref().unwrap_or_default()
                    )));
                }
                "gt" => {
                    conditions.push(format!("{col} > ?"));
                    params.push(Box::new(f.value.clone().unwrap_or_default()));
                }
                "lt" => {
                    conditions.push(format!("{col} < ?"));
                    params.push(Box::new(f.value.clone().unwrap_or_default()));
                }
                "gte" => {
                    conditions.push(format!("{col} >= ?"));
                    params.push(Box::new(f.value.clone().unwrap_or_default()));
                }
                "lte" => {
                    conditions.push(format!("{col} <= ?"));
                    params.push(Box::new(f.value.clone().unwrap_or_default()));
                }
                op => {
                    return Err(AppError::Message(format!("unsupported operator: {op}")));
                }
            }
        }
    }

    let sql = if conditions.is_empty() {
        String::new()
    } else {
        format!(" WHERE {}", conditions.join(" AND "))
    };

    Ok(WhereClause { sql, params })
}

#[tauri::command]
pub fn get_recipe_db_tables(db_path: String) -> AppResult<Vec<TableInfoDto>> {
    let conn = open_readonly(&db_path)?;
    let table_names = get_table_names(&conn)?;
    let mut tables: Vec<TableInfoDto> = Vec::new();

    for name in &table_names {
        let count: i64 =
            conn.query_row(&format!("SELECT COUNT(*) FROM \"{}\"", name), [], |row| {
                row.get(0)
            })?;
        tables.push(TableInfoDto {
            name: name.clone(),
            row_count: count,
        });
    }

    tables.sort_by(|a, b| a.name.cmp(&b.name));
    Ok(tables)
}

#[tauri::command]
pub fn query_recipe_db(
    db_path: String,
    table: String,
    page: Option<u32>,
    page_size: Option<u32>,
    sort_column: Option<String>,
    sort_direction: Option<String>,
    search: Option<String>,
    filters: Option<Vec<ColumnFilter>>,
) -> AppResult<QueryResultDto> {
    let conn = open_readonly(&db_path)?;
    validate_table(&conn, &table)?;
    let columns = get_column_info(&conn, &table)?;

    let page = page.unwrap_or(DEFAULT_PAGE);
    let page_size = page_size.unwrap_or(DEFAULT_PAGE_SIZE);
    let offset = (page.saturating_sub(1)) * page_size;

    let where_clause = build_where(&columns, &search, &filters)?;

    // Build ORDER BY
    let order_by = if let Some(ref col) = sort_column {
        validate_column(&columns, col)?;
        let dir = match sort_direction.as_deref() {
            Some("desc") | Some("DESC") => "DESC",
            _ => "ASC",
        };
        format!(" ORDER BY \"{col}\" {dir}")
    } else {
        String::new()
    };

    // COUNT query
    let count_sql = format!("SELECT COUNT(*) FROM \"{table}\"{}", where_clause.sql);
    let count_params: Vec<&dyn rusqlite::types::ToSql> =
        where_clause.params.iter().map(|p| p.as_ref()).collect();
    let total: i64 = conn.query_row(&count_sql, count_params.as_slice(), |row| row.get(0))?;

    // Data query
    let data_sql = format!(
        "SELECT * FROM \"{table}\"{}{} LIMIT ? OFFSET ?",
        where_clause.sql, order_by
    );
    // Rebuild where clause for data query (count query consumed the refs)
    let where_clause2 = build_where(&columns, &search, &filters)?;
    let mut all_params: Vec<Box<dyn rusqlite::types::ToSql>> = where_clause2.params;
    all_params.push(Box::new(page_size));
    all_params.push(Box::new(offset));

    let param_refs: Vec<&dyn rusqlite::types::ToSql> =
        all_params.iter().map(|p| p.as_ref()).collect();

    let mut stmt = conn.prepare(&data_sql)?;
    let col_count = stmt.column_count();
    let rows: Vec<Vec<Value>> = stmt
        .query_map(param_refs.as_slice(), |row| {
            let mut values = Vec::with_capacity(col_count);
            for i in 0..col_count {
                let val: rusqlite::types::Value = row.get(i)?;
                values.push(sqlite_value_to_json(val));
            }
            Ok(values)
        })?
        .filter_map(|r| r.ok())
        .collect();

    Ok(QueryResultDto {
        columns,
        rows,
        total,
        page,
        page_size,
    })
}

#[tauri::command]
pub fn resolve_recipe_db_path(recipe_name: String) -> AppResult<Option<String>> {
    let repo_root = paths::repo_root()?;
    let db_path = repo_root
        .join(".atlas-weave")
        .join("recipes")
        .join(&recipe_name)
        .join("latest.sqlite");

    if db_path.exists() {
        Ok(Some(
            db_path
                .to_str()
                .unwrap_or_default()
                .to_string(),
        ))
    } else {
        Ok(None)
    }
}

#[tauri::command]
pub fn export_csv(
    db_path: String,
    table: String,
    output_path: String,
    search: Option<String>,
    filters: Option<Vec<ColumnFilter>>,
) -> AppResult<ExportResultDto> {
    let conn = open_readonly(&db_path)?;
    validate_table(&conn, &table)?;
    let columns = get_column_info(&conn, &table)?;
    let where_clause = build_where(&columns, &search, &filters)?;

    let query = format!("SELECT * FROM \"{table}\"{}", where_clause.sql);
    let param_refs: Vec<&dyn rusqlite::types::ToSql> =
        where_clause.params.iter().map(|p| p.as_ref()).collect();

    let mut stmt = conn.prepare(&query)?;
    let col_count = stmt.column_count();

    let out_path = PathBuf::from(&output_path);
    let file = File::create(&out_path)?;
    let mut writer = BufWriter::new(file);

    // Write header
    let header: Vec<&str> = columns.iter().map(|c| c.name.as_str()).collect();
    writeln!(writer, "{}", header.join(","))?;

    let mut rows_exported: i64 = 0;
    let mut rows = stmt.query(param_refs.as_slice())?;
    while let Some(row) = rows.next()? {
        let mut fields = Vec::with_capacity(col_count);
        for i in 0..col_count {
            let val: rusqlite::types::Value = row.get(i)?;
            let field = match val {
                rusqlite::types::Value::Null => String::new(),
                rusqlite::types::Value::Integer(i) => i.to_string(),
                rusqlite::types::Value::Real(f) => f.to_string(),
                rusqlite::types::Value::Text(s) => {
                    if s.contains(',') || s.contains('"') || s.contains('\n') {
                        format!("\"{}\"", s.replace('"', "\"\""))
                    } else {
                        s
                    }
                }
                rusqlite::types::Value::Blob(b) => format!("<blob {} bytes>", b.len()),
            };
            fields.push(field);
        }
        writeln!(writer, "{}", fields.join(","))?;
        rows_exported += 1;
    }

    writer.flush()?;

    Ok(ExportResultDto {
        rows_exported,
        file_path: output_path,
    })
}
