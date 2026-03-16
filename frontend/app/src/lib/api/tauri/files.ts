import { invoke } from '@tauri-apps/api/core';

export function pickCsvFile(): Promise<string | null> {
  return invoke<string | null>('pick_csv_file');
}
