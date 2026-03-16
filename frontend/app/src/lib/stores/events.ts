import { writable } from 'svelte/store';

export type RunViewStatus = 'idle' | 'running' | 'completed' | 'failed' | 'cancelled';

export type AtlasWeaveEvent = {
  type: string;
  run_id: string;
  node_id?: string;
  level?: string;
  message?: string;
  progress?: number;
  duration_ms?: number;
  summary?: Record<string, unknown>;
  error?: string;
  timestamp?: string;
};

type EventState = {
  activeRunId: string | null;
  status: RunViewStatus;
  events: AtlasWeaveEvent[];
  total: number;
  page: number;
  pageSize: number;
};

const initialState: EventState = {
  activeRunId: null,
  status: 'idle',
  events: [],
  total: 0,
  page: 1,
  pageSize: 0
};

function createEventStore() {
  const { subscribe, set, update } = writable<EventState>(initialState);

  return {
    subscribe,
    clear() {
      set(initialState);
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
        total,
        page,
        pageSize
      });
    },
    prependPage(events: AtlasWeaveEvent[], page: number, total: number, pageSize: number) {
      update((state) => ({
        ...state,
        events: [...events, ...state.events],
        page,
        total,
        pageSize
      }));
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

        return {
          ...state,
          status,
          total: Math.max(state.total, state.events.length + 1),
          events: [...state.events, event]
        };
      });
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
