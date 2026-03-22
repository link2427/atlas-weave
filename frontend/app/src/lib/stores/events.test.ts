import { describe, it, expect, beforeEach } from 'vitest';
import { get } from 'svelte/store';
import { eventStore, normalizeRunStatus } from './events';
import type { AtlasWeaveEvent } from './events';

function makeEvent(overrides: Partial<AtlasWeaveEvent> = {}): AtlasWeaveEvent {
  return {
    type: 'node_started',
    run_id: 'run-1',
    node_id: 'agent_a',
    timestamp: '2026-01-01T00:00:00Z',
    ...overrides,
  };
}

describe('eventStore', () => {
  beforeEach(() => {
    eventStore.clear();
  });

  it('setRun populates activeRunId, status, events, and nodeIndex', () => {
    const events = [makeEvent(), makeEvent({ type: 'node_completed', node_id: 'agent_a' })];
    eventStore.setRun('run-1', 'running', events);
    const state = get(eventStore);

    expect(state.activeRunId).toBe('run-1');
    expect(state.status).toBe('running');
    expect(state.events).toHaveLength(2);
    expect(state.nodeIndex.get('agent_a')).toEqual([0, 1]);
  });

  it('push appends event and updates status on run_completed', () => {
    eventStore.setRun('run-1', 'running');
    eventStore.push(makeEvent({ type: 'run_completed' }));
    const state = get(eventStore);

    expect(state.events).toHaveLength(1);
    expect(state.status).toBe('completed');
  });

  it('push updates status on run_failed and run_cancelled', () => {
    eventStore.setRun('run-1', 'running');
    eventStore.push(makeEvent({ type: 'run_failed' }));
    expect(get(eventStore).status).toBe('failed');

    eventStore.clear();
    eventStore.setRun('run-1', 'running');
    eventStore.push(makeEvent({ type: 'run_cancelled' }));
    expect(get(eventStore).status).toBe('cancelled');
  });

  it('push ignores events with wrong run_id', () => {
    eventStore.setRun('run-1', 'running');
    eventStore.push(makeEvent({ run_id: 'run-other' }));
    expect(get(eventStore).events).toHaveLength(0);
  });

  it('push updates nodeIndex for new node_id', () => {
    eventStore.setRun('run-1', 'running');
    eventStore.push(makeEvent({ node_id: 'agent_a' }));
    eventStore.push(makeEvent({ node_id: 'agent_b' }));
    eventStore.push(makeEvent({ node_id: 'agent_a', type: 'node_completed' }));
    const state = get(eventStore);

    expect(state.nodeIndex.get('agent_a')).toEqual([0, 2]);
    expect(state.nodeIndex.get('agent_b')).toEqual([1]);
  });

  it('getNodeEvents returns correct filtered events', () => {
    const events = [
      makeEvent({ node_id: 'agent_a', type: 'node_started' }),
      makeEvent({ node_id: 'agent_b', type: 'node_started' }),
      makeEvent({ node_id: 'agent_a', type: 'node_completed' }),
    ];
    eventStore.setRun('run-1', 'running', events);
    const state = get(eventStore);

    const nodeEvents = eventStore.getNodeEvents(state, 'agent_a');
    expect(nodeEvents).toHaveLength(2);
    expect(nodeEvents[0].type).toBe('node_started');
    expect(nodeEvents[1].type).toBe('node_completed');
  });

  it('prependPage merges events at front and rebuilds index', () => {
    eventStore.setRun('run-1', 'running', [makeEvent({ node_id: 'agent_b' })]);
    eventStore.prependPage([makeEvent({ node_id: 'agent_a' })], 1, 2, 1);
    const state = get(eventStore);

    expect(state.events).toHaveLength(2);
    expect(state.events[0].node_id).toBe('agent_a');
    expect(state.events[1].node_id).toBe('agent_b');
    expect(state.nodeIndex.get('agent_a')).toEqual([0]);
    expect(state.nodeIndex.get('agent_b')).toEqual([1]);
  });

  it('clear resets to initial state', () => {
    eventStore.setRun('run-1', 'running', [makeEvent()]);
    eventStore.clear();
    const state = get(eventStore);

    expect(state.activeRunId).toBeNull();
    expect(state.status).toBe('idle');
    expect(state.events).toHaveLength(0);
    expect(state.nodeIndex.size).toBe(0);
  });
});

describe('normalizeRunStatus', () => {
  it('maps status strings correctly', () => {
    expect(normalizeRunStatus('completed')).toBe('completed');
    expect(normalizeRunStatus('failed')).toBe('failed');
    expect(normalizeRunStatus('cancelled')).toBe('cancelled');
    expect(normalizeRunStatus('running')).toBe('running');
    expect(normalizeRunStatus('pending')).toBe('running');
    expect(normalizeRunStatus('anything_else')).toBe('running');
  });
});
