import { writable } from 'svelte/store';

export type RunViewStatus = 'idle' | 'running' | 'completed' | 'failed' | 'cancelled';

export type AtlasWeaveEvent = {
  type: string;
  run_id: string;
  node_id?: string;
  nodes?: Array<Record<string, unknown>>;
  edges?: Array<[string, string]>;
  tool?: string;
  provider?: string;
  model?: string;
  request_id?: string;
  level?: string;
  message?: string;
  progress?: number;
  duration_ms?: number;
  summary?: Record<string, unknown>;
  error?: string;
  input?: unknown;
  output?: unknown;
  cache_hit?: boolean;
  failures?: unknown;
  provider_attempts?: unknown;
  prompt_tokens?: number;
  completion_tokens?: number;
  estimated_cost_usd?: number;
  timestamp?: string;
};

type EventState = {
  activeRunId: string | null;
  status: RunViewStatus;
  events: AtlasWeaveEvent[];
  nodeIndex: Map<string, number[]>;
  version: number;
  total: number;
  page: number;
  pageSize: number;
};

const initialState: EventState = {
  activeRunId: null,
  status: 'idle',
  events: [],
  nodeIndex: new Map(),
  version: 0,
  total: 0,
  page: 1,
  pageSize: 0
};

function buildNodeIndex(events: AtlasWeaveEvent[]): Map<string, number[]> {
  const index = new Map<string, number[]>();
  for (let i = 0; i < events.length; i++) {
    const nodeId = events[i].node_id;
    if (nodeId) {
      let indices = index.get(nodeId);
      if (!indices) {
        indices = [];
        index.set(nodeId, indices);
      }
      indices.push(i);
    }
  }
  return index;
}

function createEventStore() {
  const { subscribe, set, update } = writable<EventState>(initialState);

  return {
    subscribe,
    clear() {
      set({ ...initialState, nodeIndex: new Map() });
    },
    setRun(
      runId: string,
      status: RunViewStatus,
      events: AtlasWeaveEvent[] = [],
      total = events.length,
      page = 1,
      pageSize = events.length
    ) {
      set({
        activeRunId: runId,
        status,
        events,
        nodeIndex: buildNodeIndex(events),
        version: 0,
        total,
        page,
        pageSize
      });
    },
    prependPage(events: AtlasWeaveEvent[], page: number, total: number, pageSize: number) {
      update((state) => {
        const merged = [...events, ...state.events];
        return {
          ...state,
          events: merged,
          nodeIndex: buildNodeIndex(merged),
          version: state.version + 1,
          page,
          total,
          pageSize
        };
      });
    },
    push(event: AtlasWeaveEvent) {
      update((state) => {
        if (state.activeRunId !== event.run_id) {
          return state;
        }

        const status =
          event.type === 'run_completed'
            ? 'completed'
            : event.type === 'run_failed'
              ? 'failed'
              : event.type === 'run_cancelled'
                ? 'cancelled'
                : state.status;

        // Mutate in place for O(1) push
        const idx = state.events.length;
        state.events.push(event);

        if (event.node_id) {
          let indices = state.nodeIndex.get(event.node_id);
          if (!indices) {
            indices = [];
            state.nodeIndex.set(event.node_id, indices);
          }
          indices.push(idx);
        }

        return {
          ...state,
          status,
          version: state.version + 1,
          total: Math.max(state.total, state.events.length)
        };
      });
    },
    getNodeEvents(state: EventState, nodeId: string): AtlasWeaveEvent[] {
      const indices = state.nodeIndex.get(nodeId);
      if (!indices) return [];
      return indices.map((i) => state.events[i]);
    }
  };
}

export const eventStore = createEventStore();

export function normalizeRunStatus(status: string): RunViewStatus {
  if (status === 'completed') {
    return 'completed';
  }
  if (status === 'failed') {
    return 'failed';
  }
  if (status === 'cancelled') {
    return 'cancelled';
  }
  return 'running';
}
