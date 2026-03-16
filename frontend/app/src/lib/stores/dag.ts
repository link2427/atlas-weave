import { writable } from 'svelte/store';

import type { RecipeDagNode, RecipeDetail } from '$lib/api/tauri/recipes';
import type { RunDetail, RunNode, RunStatus } from '$lib/api/tauri/runs';
import type { AtlasWeaveEvent } from '$lib/stores/events';

export type DagNodeStatus = RunStatus;
export type DagEdgeVisualState =
  | 'idle'
  | 'active'
  | 'completed'
  | 'failed'
  | 'skipped'
  | 'cancelled'
  | 'flowing';

export type DagNodeState = RecipeDagNode & {
  status: DagNodeStatus;
  progress: number;
  message: string | null;
  startedAt: string | null;
  completedAt: string | null;
  durationMs: number | null;
  summary: Record<string, unknown> | null;
  error: string | null;
};

export type DagEdgeState = {
  id: string;
  source: string;
  target: string;
  state: DagEdgeVisualState;
  pulsing: boolean;
};

type DagStoreState = {
  runId: string | null;
  recipe: RecipeDetail | null;
  runStatus: RunStatus | null;
  runError: string | null;
  nodes: DagNodeState[];
  edges: DagEdgeState[];
  selectedNodeId: string | null;
};

const EDGE_PULSE_MS = 1200;

const initialState: DagStoreState = {
  runId: null,
  recipe: null,
  runStatus: null,
  runError: null,
  nodes: [],
  edges: [],
  selectedNodeId: null
};

function edgeId(source: string, target: string): string {
  return `${source}->${target}`;
}

function baseNodeState(node: RecipeDagNode): DagNodeState {
  return {
    ...node,
    status: 'pending',
    progress: 0,
    message: null,
    startedAt: null,
    completedAt: null,
    durationMs: null,
    summary: null,
    error: null
  };
}

function chooseDefaultNode(nodes: DagNodeState[]): string | null {
  return (
    nodes.find((node) => node.status === 'running')?.id ??
    nodes.find((node) => node.status === 'failed')?.id ??
    nodes[0]?.id ??
    null
  );
}

function computeEdgeState(
  sourceStatus: DagNodeStatus,
  targetStatus: DagNodeStatus,
  pulsing: boolean
): DagEdgeVisualState {
  if (pulsing) {
    return 'flowing';
  }
  if (sourceStatus === 'failed' || targetStatus === 'failed') {
    return 'failed';
  }
  if (sourceStatus === 'cancelled' || targetStatus === 'cancelled') {
    return 'cancelled';
  }
  if (sourceStatus === 'skipped' || targetStatus === 'skipped') {
    return 'skipped';
  }
  if (targetStatus === 'running') {
    return 'active';
  }
  if (sourceStatus === 'completed') {
    return 'completed';
  }
  return 'idle';
}

function rederiveEdges(state: DagStoreState): DagStoreState {
  const nodeById = new Map(state.nodes.map((node) => [node.id, node]));
  return {
    ...state,
    edges: state.edges.map((edge) => {
      const sourceStatus = nodeById.get(edge.source)?.status ?? 'pending';
      const targetStatus = nodeById.get(edge.target)?.status ?? 'pending';
      return {
        ...edge,
        state: computeEdgeState(sourceStatus, targetStatus, edge.pulsing)
      };
    })
  };
}

function applyRunSnapshot(node: DagNodeState, snapshot?: RunNode): DagNodeState {
  if (!snapshot) {
    return node;
  }

  return {
    ...node,
    status: snapshot.status,
    progress: snapshot.progress ?? 0,
    message: snapshot.message ?? null,
    startedAt: snapshot.startedAt ?? null,
    completedAt: snapshot.completedAt ?? null,
    durationMs: snapshot.durationMs ?? null,
    summary: snapshot.summary ?? null,
    error: snapshot.error ?? null
  };
}

function nextNodeState(node: DagNodeState, event: AtlasWeaveEvent): DagNodeState {
  switch (event.type) {
    case 'node_started':
      return {
        ...node,
        status: 'running',
        progress: node.progress || 0,
        startedAt: event.timestamp ?? node.startedAt,
        error: null
      };
    case 'node_progress':
      return {
        ...node,
        status: 'running',
        progress: event.progress ?? node.progress,
        message: event.message ?? node.message
      };
    case 'node_log':
      return {
        ...node,
        message: event.message ?? node.message
      };
    case 'node_completed':
      return {
        ...node,
        status: 'completed',
        progress: 1,
        message: event.message ?? node.message,
        completedAt: event.timestamp ?? node.completedAt,
        durationMs: event.duration_ms ?? node.durationMs,
        summary: event.summary ?? node.summary,
        error: null
      };
    case 'node_failed':
      return {
        ...node,
        status: 'failed',
        completedAt: event.timestamp ?? node.completedAt,
        error: event.error ?? node.error
      };
    case 'node_skipped':
      return {
        ...node,
        status: 'skipped',
        message: event.message ?? node.message,
        completedAt: event.timestamp ?? node.completedAt
      };
    case 'node_cancelled':
      return {
        ...node,
        status: 'cancelled',
        message: event.message ?? node.message,
        completedAt: event.timestamp ?? node.completedAt
      };
    default:
      return node;
  }
}

function createDagStore() {
  const { subscribe, set, update } = writable<DagStoreState>(initialState);
  const edgePulseTimers = new Map<string, number>();

  function clearEdgeTimers(): void {
    for (const timer of edgePulseTimers.values()) {
      window.clearTimeout(timer);
    }
    edgePulseTimers.clear();
  }

  function pulseOutgoingEdges(nodeId: string): void {
    update((state) => {
      if (state.runId === null) {
        return state;
      }

      const edgesToPulse = state.edges.filter((edge) => edge.source === nodeId);
      for (const edge of edgesToPulse) {
        const existingTimer = edgePulseTimers.get(edge.id);
        if (existingTimer) {
          window.clearTimeout(existingTimer);
        }

        const timer = window.setTimeout(() => {
          update((current) =>
            rederiveEdges({
              ...current,
              edges: current.edges.map((candidate) =>
                candidate.id === edge.id ? { ...candidate, pulsing: false } : candidate
              )
            })
          );
          edgePulseTimers.delete(edge.id);
        }, EDGE_PULSE_MS);

        edgePulseTimers.set(edge.id, timer);
      }

      return rederiveEdges({
        ...state,
        edges: state.edges.map((edge) =>
          edge.source === nodeId ? { ...edge, pulsing: true } : edge
        )
      });
    });
  }

  return {
    subscribe,
    clear() {
      clearEdgeTimers();
      set(initialState);
    },
    hydrate(recipe: RecipeDetail, run: RunDetail) {
      clearEdgeTimers();

      const snapshotByNodeId = new Map(run.nodes.map((node) => [node.nodeId, node]));
      const nodes = recipe.dag.nodes.map((node) =>
        applyRunSnapshot(baseNodeState(node), snapshotByNodeId.get(node.id))
      );
      const edges = recipe.dag.edges.map(([source, target]) => ({
        id: edgeId(source, target),
        source,
        target,
        state: 'idle' as DagEdgeVisualState,
        pulsing: false
      }));

      set(
        rederiveEdges({
          runId: run.id,
          recipe,
          runStatus: run.status,
          runError: run.error ?? null,
          nodes,
          edges,
          selectedNodeId: chooseDefaultNode(nodes)
        })
      );
    },
    applyEvent(event: AtlasWeaveEvent) {
      let shouldPulse = false;
      let completedNodeId: string | null = null;

      update((state) => {
        if (state.runId !== event.run_id) {
          return state;
        }

        const nextState: DagStoreState = {
          ...state,
          runStatus:
            event.type === 'run_completed'
              ? 'completed'
              : event.type === 'run_failed'
                ? 'failed'
                : event.type === 'run_cancelled'
                  ? 'cancelled'
                : state.runStatus,
          runError:
            event.type === 'run_failed'
              ? (event.error ?? state.runError)
              : state.runError,
          nodes: state.nodes.map((node) =>
            node.id === event.node_id ? nextNodeState(node, event) : node
          )
        };

        if (event.type === 'node_completed' && event.node_id) {
          shouldPulse = true;
          completedNodeId = event.node_id;
        }

        return rederiveEdges(nextState);
      });

      if (shouldPulse && completedNodeId) {
        pulseOutgoingEdges(completedNodeId);
      }
    },
    selectNode(nodeId: string) {
      update((state) => ({
        ...state,
        selectedNodeId: nodeId
      }));
    }
  };
}

export const dagStore = createDagStore();
