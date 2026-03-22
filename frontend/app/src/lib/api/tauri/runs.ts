import { invoke } from '@tauri-apps/api/core';
import type { AtlasWeaveEvent } from '$lib/stores/events';

export type RunStatus =
  | 'pending'
  | 'running'
  | 'completed'
  | 'failed'
  | 'skipped'
  | 'cancelled';

export type StartRunResponse = {
  runId: string;
  status: string;
};

export type CancelRunResponse = {
  status: 'cancelling';
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

export type RunGraphNode = {
  id: string;
  label: string;
  description: string;
  kind: 'static' | 'runtime' | string;
  parentId?: string | null;
  groupKey?: string | null;
  collapsedByDefault?: boolean;
};

export type RunGraph = {
  nodes: RunGraphNode[];
  edges: [string, string][];
};

export type RunDetail = {
  id: string;
  recipeName: string;
  status: RunStatus;
  startedAt?: string | null;
  completedAt?: string | null;
  config: Record<string, unknown>;
  summary?: Record<string, unknown> | null;
  error?: string | null;
  nodes: RunNode[];
  graph: RunGraph;
};

export type RunHistoryItem = {
  id: string;
  recipeName: string;
  status: RunStatus;
  startedAt?: string | null;
  completedAt?: string | null;
  error?: string | null;
  pendingNodes: number;
  runningNodes: number;
  completedNodes: number;
  failedNodes: number;
  skippedNodes: number;
  cancelledNodes: number;
};

export type PaginatedResponse<T> = {
  items: T[];
  total: number;
  page: number;
  pageSize: number;
};

export function startRun(
  recipe: string,
  config: Record<string, unknown> = {}
): Promise<StartRunResponse> {
  return invoke<StartRunResponse>('start_run', { recipe, config });
}

export function cancelRun(runId: string): Promise<CancelRunResponse> {
  return invoke<CancelRunResponse>('cancel_run', { runId });
}

export function getRun(runId: string): Promise<RunDetail> {
  return invoke<RunDetail>('get_run', { runId });
}

export function getRunHistory(
  recipeName: string,
  page = 1,
  pageSize = 20
): Promise<PaginatedResponse<RunHistoryItem>> {
  return invoke<PaginatedResponse<RunHistoryItem>>('get_run_history', {
    recipeName,
    page,
    pageSize
  });
}

export function retryFailedNodes(sourceRunId: string): Promise<StartRunResponse> {
  return invoke<StartRunResponse>('retry_failed_nodes', { sourceRunId });
}

export function getRunEvents(
  runId: string,
  nodeId?: string,
  page = 1,
  pageSize = 200
): Promise<PaginatedResponse<AtlasWeaveEvent>> {
  return invoke<PaginatedResponse<AtlasWeaveEvent>>('get_run_events', {
    runId,
    nodeId,
    page,
    pageSize
  });
}
