import { invoke } from '@tauri-apps/api/core';

export type RunStatus = 'pending' | 'running' | 'completed' | 'failed' | 'skipped';

export type StartRunResponse = {
  runId: string;
  status: string;
};

export type RunNode = {
  nodeId: string;
  status: RunStatus;
  progress: number;
  message?: string | null;
  startedAt?: string | null;
  completedAt?: string | null;
  durationMs?: number | null;
  summary?: Record<string, unknown> | null;
  error?: string | null;
};

export type RunDetail = {
  id: string;
  recipeName: string;
  status: RunStatus;
  startedAt?: string | null;
  completedAt?: string | null;
  error?: string | null;
  nodes: RunNode[];
};

export function startRun(
  recipe: string,
  config: Record<string, unknown> = {}
): Promise<StartRunResponse> {
  return invoke<StartRunResponse>('start_run', { recipe, config });
}

export function getRun(runId: string): Promise<RunDetail> {
  return invoke<RunDetail>('get_run', { runId });
}

export function getRunEvents(
  runId: string,
  nodeId?: string
): Promise<Record<string, unknown>[]> {
  return invoke<Record<string, unknown>[]>('get_run_events', { runId, nodeId });
}
