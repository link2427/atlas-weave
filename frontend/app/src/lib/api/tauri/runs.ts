import { invoke } from '@tauri-apps/api/core';

export type StartRunResponse = {
  runId: string;
  status: string;
};

export function startRun(
  recipe: string,
  config: Record<string, unknown> = {}
): Promise<StartRunResponse> {
  return invoke<StartRunResponse>('start_run', { recipe, config });
}
