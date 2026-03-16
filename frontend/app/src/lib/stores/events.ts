import { writable } from 'svelte/store';

export type RunViewStatus = 'idle' | 'running' | 'completed' | 'failed';

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
};

const initialState: EventState = {
  activeRunId: null,
  status: 'idle',
  events: []
};

function createEventStore() {
  const { subscribe, set, update } = writable<EventState>(initialState);

  return {
    subscribe,
    clear() {
      set(initialState);
    },
    setRun(runId: string, status: RunViewStatus, events: AtlasWeaveEvent[] = []) {
      set({
        activeRunId: runId,
        status,
        events
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
              : state.status;

        return {
          ...state,
          status,
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
  return 'running';
}
