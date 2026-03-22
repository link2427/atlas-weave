import { describe, it, expect, beforeEach, vi, afterEach } from 'vitest';
import { get } from 'svelte/store';
import { dagStore } from './dag';
import type { DagNodeState, DagEdgeState } from './dag';
import type { RecipeDetail } from '$lib/api/tauri/recipes';
import type { RunDetail, RunNode, RunGraphNode } from '$lib/api/tauri/runs';
import type { AtlasWeaveEvent } from '$lib/stores/events';

// -- Fixtures -----------------------------------------------------------------

function makeGraphNodes(): RunGraphNode[] {
  return [
    { id: 'a', label: 'Agent A', description: 'First', kind: 'static' },
    { id: 'b', label: 'Agent B', description: 'Second', kind: 'static' },
    { id: 'c', label: 'Agent C', description: 'Third', kind: 'static' },
  ];
}

function makeRecipe(): RecipeDetail {
  return {
    name: 'test',
    description: 'test recipe',
    version: '0.1.0',
    configSchema: {},
    dag: {
      nodes: [
        { id: 'a', label: 'Agent A', description: 'First' },
        { id: 'b', label: 'Agent B', description: 'Second' },
        { id: 'c', label: 'Agent C', description: 'Third' },
      ],
      edges: [['a', 'b'], ['b', 'c']],
    },
  };
}

function makeRun(overrides: Partial<RunDetail> = {}): RunDetail {
  return {
    id: 'run-1',
    recipeName: 'test',
    status: 'running',
    config: {},
    nodes: [
      { nodeId: 'a', status: 'completed', progress: 1 },
      { nodeId: 'b', status: 'running', progress: 0.5 },
      { nodeId: 'c', status: 'pending', progress: 0 },
    ],
    graph: {
      nodes: makeGraphNodes(),
      edges: [['a', 'b'], ['b', 'c']],
    },
    ...overrides,
  };
}

function makeEvent(overrides: Partial<AtlasWeaveEvent> = {}): AtlasWeaveEvent {
  return {
    type: 'node_started',
    run_id: 'run-1',
    node_id: 'b',
    timestamp: '2026-01-01T00:00:00Z',
    ...overrides,
  };
}

// -- Tests --------------------------------------------------------------------

describe('dagStore', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    dagStore.clear();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  describe('hydrate', () => {
    it('populates nodes with correct statuses from run snapshot', () => {
      dagStore.hydrate(makeRecipe(), makeRun());
      const state = get(dagStore);

      expect(state.nodes).toHaveLength(3);
      const nodeA = state.nodes.find((n) => n.id === 'a')!;
      const nodeB = state.nodes.find((n) => n.id === 'b')!;
      const nodeC = state.nodes.find((n) => n.id === 'c')!;

      expect(nodeA.status).toBe('completed');
      expect(nodeB.status).toBe('running');
      expect(nodeC.status).toBe('pending');
    });

    it('auto-selects running node', () => {
      dagStore.hydrate(makeRecipe(), makeRun());
      expect(get(dagStore).selectedNodeId).toBe('b');
    });

    it('auto-selects failed node when no running node', () => {
      dagStore.hydrate(
        makeRecipe(),
        makeRun({
          nodes: [
            { nodeId: 'a', status: 'completed', progress: 1 },
            { nodeId: 'b', status: 'failed', progress: 0 },
            { nodeId: 'c', status: 'skipped', progress: 0 },
          ],
        })
      );
      expect(get(dagStore).selectedNodeId).toBe('b');
    });

    it('auto-selects first node when no running or failed', () => {
      dagStore.hydrate(
        makeRecipe(),
        makeRun({
          nodes: [
            { nodeId: 'a', status: 'pending', progress: 0 },
            { nodeId: 'b', status: 'pending', progress: 0 },
            { nodeId: 'c', status: 'pending', progress: 0 },
          ],
        })
      );
      expect(get(dagStore).selectedNodeId).toBe('a');
    });
  });

  describe('applyEvent', () => {
    beforeEach(() => {
      dagStore.hydrate(makeRecipe(), makeRun());
    });

    it('node_started sets status to running', () => {
      dagStore.applyEvent(makeEvent({ type: 'node_started', node_id: 'c' }));
      const nodeC = get(dagStore).nodes.find((n) => n.id === 'c')!;
      expect(nodeC.status).toBe('running');
    });

    it('node_progress updates progress and message', () => {
      dagStore.applyEvent(
        makeEvent({ type: 'node_progress', node_id: 'b', progress: 0.8, message: '80%' })
      );
      const nodeB = get(dagStore).nodes.find((n) => n.id === 'b')!;
      expect(nodeB.progress).toBe(0.8);
      expect(nodeB.message).toBe('80%');
    });

    it('node_log updates message', () => {
      dagStore.applyEvent(
        makeEvent({ type: 'node_log', node_id: 'b', message: 'Processing...' })
      );
      const nodeB = get(dagStore).nodes.find((n) => n.id === 'b')!;
      expect(nodeB.message).toBe('Processing...');
    });

    it('node_completed sets status and triggers edge pulse', () => {
      dagStore.applyEvent(
        makeEvent({
          type: 'node_completed',
          node_id: 'b',
          duration_ms: 200,
          summary: { ok: true },
        })
      );
      const state = get(dagStore);
      const nodeB = state.nodes.find((n) => n.id === 'b')!;
      expect(nodeB.status).toBe('completed');
      expect(nodeB.durationMs).toBe(200);

      // Edge b→c should be pulsing/flowing
      const edgeBC = state.edges.find((e) => e.source === 'b' && e.target === 'c')!;
      expect(edgeBC.pulsing).toBe(true);
      expect(edgeBC.state).toBe('flowing');

      // After pulse timeout, pulsing should stop
      vi.advanceTimersByTime(1300);
      const stateAfter = get(dagStore);
      const edgeBCAfter = stateAfter.edges.find((e) => e.source === 'b' && e.target === 'c')!;
      expect(edgeBCAfter.pulsing).toBe(false);
    });

    it('node_failed sets status and error', () => {
      dagStore.applyEvent(
        makeEvent({ type: 'node_failed', node_id: 'b', error: 'boom' })
      );
      const nodeB = get(dagStore).nodes.find((n) => n.id === 'b')!;
      expect(nodeB.status).toBe('failed');
      expect(nodeB.error).toBe('boom');
    });

    it('node_skipped sets status and message', () => {
      dagStore.applyEvent(
        makeEvent({ type: 'node_skipped', node_id: 'c', message: 'dep failed' })
      );
      const nodeC = get(dagStore).nodes.find((n) => n.id === 'c')!;
      expect(nodeC.status).toBe('skipped');
      expect(nodeC.message).toBe('dep failed');
    });

    it('node_cancelled sets status', () => {
      dagStore.applyEvent(
        makeEvent({ type: 'node_cancelled', node_id: 'b', message: 'user cancelled' })
      );
      const nodeB = get(dagStore).nodes.find((n) => n.id === 'b')!;
      expect(nodeB.status).toBe('cancelled');
    });

    it('graph_patch merges new nodes and edges', () => {
      dagStore.applyEvent(
        makeEvent({
          type: 'graph_patch',
          nodes: [{ id: 'd', label: 'Agent D', description: 'Dynamic', kind: 'runtime' }],
          edges: [['c', 'd']],
        })
      );
      const state = get(dagStore);
      expect(state.nodes.find((n) => n.id === 'd')).toBeDefined();
      expect(state.edges.find((e) => e.source === 'c' && e.target === 'd')).toBeDefined();
    });

    it('run_completed/run_failed/run_cancelled updates runStatus', () => {
      dagStore.applyEvent(makeEvent({ type: 'run_completed' }));
      expect(get(dagStore).runStatus).toBe('completed');

      dagStore.hydrate(makeRecipe(), makeRun());
      dagStore.applyEvent(makeEvent({ type: 'run_failed', error: 'oops' }));
      expect(get(dagStore).runStatus).toBe('failed');
      expect(get(dagStore).runError).toBe('oops');

      dagStore.hydrate(makeRecipe(), makeRun());
      dagStore.applyEvent(makeEvent({ type: 'run_cancelled' }));
      expect(get(dagStore).runStatus).toBe('cancelled');
    });

    it('ignores events for wrong run_id', () => {
      dagStore.applyEvent(makeEvent({ run_id: 'other-run', type: 'node_failed', node_id: 'b' }));
      const nodeB = get(dagStore).nodes.find((n) => n.id === 'b')!;
      expect(nodeB.status).toBe('running'); // unchanged
    });
  });

  describe('edge state derivation', () => {
    it('completed source + running target = active', () => {
      dagStore.hydrate(makeRecipe(), makeRun());
      // a is completed, b is running → edge a→b should be 'active'
      const edgeAB = get(dagStore).edges.find((e) => e.source === 'a' && e.target === 'b')!;
      expect(edgeAB.state).toBe('active');
    });
  });

  describe('selectNode/deselectNode', () => {
    it('selectNode sets selectedNodeId', () => {
      dagStore.hydrate(makeRecipe(), makeRun());
      dagStore.selectNode('c');
      expect(get(dagStore).selectedNodeId).toBe('c');
    });

    it('deselectNode clears selectedNodeId', () => {
      dagStore.hydrate(makeRecipe(), makeRun());
      dagStore.deselectNode();
      expect(get(dagStore).selectedNodeId).toBeNull();
    });
  });

  describe('clear', () => {
    it('resets state and clears timers', () => {
      dagStore.hydrate(makeRecipe(), makeRun());
      // Trigger a pulse timer
      dagStore.applyEvent(
        makeEvent({ type: 'node_completed', node_id: 'b', duration_ms: 100, summary: {} })
      );
      dagStore.clear();
      const state = get(dagStore);

      expect(state.runId).toBeNull();
      expect(state.nodes).toHaveLength(0);
      expect(state.edges).toHaveLength(0);
      expect(state.selectedNodeId).toBeNull();
    });
  });
});
