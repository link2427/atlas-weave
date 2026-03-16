import { invoke } from '@tauri-apps/api/core';

export type StartRunResponse = {
  runId: string;
  status: string;
};

export function startRun(recipe: string): Promise<StartRunResponse> {
  return invoke<StartRunResponse>('start_run', { recipe });
}
