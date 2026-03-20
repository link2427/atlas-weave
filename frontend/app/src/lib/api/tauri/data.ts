import { invoke } from '@tauri-apps/api/core';

export type ColumnInfo = { name: string; dataType: string };

export type ColumnFilter = { column: string; operator: string; value?: string | null };

export type QueryResult = {
  columns: ColumnInfo[];
  rows: (string | number | boolean | null)[][];
  total: number;
  page: number;
  pageSize: number;
};

export type TableInfo = { name: string; rowCount: number };

export type ExportResult = { rowsExported: number; filePath: string };

export function getRecipeDbTables(dbPath: string): Promise<TableInfo[]> {
  return invoke<TableInfo[]>('get_recipe_db_tables', { dbPath });
}

export function queryRecipeDb(params: {
  dbPath: string;
  table: string;
  page?: number;
  pageSize?: number;
  sortColumn?: string | null;
  sortDirection?: string | null;
  search?: string | null;
  filters?: ColumnFilter[] | null;
}): Promise<QueryResult> {
  return invoke<QueryResult>('query_recipe_db', params);
}

export function resolveRecipeDbPath(recipeName: string): Promise<string | null> {
  return invoke<string | null>('resolve_recipe_db_path', { recipeName });
}

export function exportCsv(params: {
  dbPath: string;
  table: string;
  outputPath: string;
  search?: string | null;
  filters?: ColumnFilter[] | null;
}): Promise<ExportResult> {
  return invoke<ExportResult>('export_csv', params);
}

export function pickSaveCsvFile(): Promise<string | null> {
  return invoke<string | null>('pick_save_csv_file');
}
