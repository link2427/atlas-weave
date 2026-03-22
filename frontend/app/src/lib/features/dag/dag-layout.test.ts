import { describe, it, expect } from 'vitest';
import { buildDagLayout, DAG_NODE_WIDTH, DAG_NODE_HEIGHT } from './dag-layout';
import type { DagNodeState, DagEdgeState } from '$lib/stores/dag';

function makeNode(id: string): DagNodeState {
  return {
    id,
    label: id,
    description: '',
    kind: 'static',
    status: 'pending',
    progress: 0,
    message: null,
    startedAt: null,
    completedAt: null,
    durationMs: null,
    summary: null,
    error: null,
  };
}

function makeEdge(source: string, target: string): DagEdgeState {
  return {
    id: `${source}->${target}`,
    source,
    target,
    state: 'idle',
    pulsing: false,
  };
}

describe('buildDagLayout', () => {
  it('linear graph (A→B→C): 3 nodes vertically ordered, 2 edges with paths', () => {
    const nodes = [makeNode('a'), makeNode('b'), makeNode('c')];
    const edges = [makeEdge('a', 'b'), makeEdge('b', 'c')];
    const layout = buildDagLayout(nodes, edges);

    expect(layout.nodes).toHaveLength(3);
    expect(layout.edges).toHaveLength(2);

    // Vertical ordering: a.centerY < b.centerY < c.centerY
    const a = layout.nodes.find((n) => n.id === 'a')!;
    const b = layout.nodes.find((n) => n.id === 'b')!;
    const c = layout.nodes.find((n) => n.id === 'c')!;
    expect(a.centerY).toBeLessThan(b.centerY);
    expect(b.centerY).toBeLessThan(c.centerY);

    // Edges should have SVG path strings
    for (const edge of layout.edges) {
      expect(edge.path).toContain('M ');
      expect(edge.path).toContain('C ');
    }
  });

  it('diamond (A→B, A→C, B→D, C→D): B and C same rank, 4 edges', () => {
    const nodes = [makeNode('a'), makeNode('b'), makeNode('c'), makeNode('d')];
    const edges = [
      makeEdge('a', 'b'),
      makeEdge('a', 'c'),
      makeEdge('b', 'd'),
      makeEdge('c', 'd'),
    ];
    const layout = buildDagLayout(nodes, edges);

    expect(layout.nodes).toHaveLength(4);
    expect(layout.edges).toHaveLength(4);

    const b = layout.nodes.find((n) => n.id === 'b')!;
    const c = layout.nodes.find((n) => n.id === 'c')!;
    // Same rank → same Y
    expect(b.centerY).toBe(c.centerY);
  });

  it('parallel (A→C, B→C): A and B same rank', () => {
    const nodes = [makeNode('a'), makeNode('b'), makeNode('c')];
    const edges = [makeEdge('a', 'c'), makeEdge('b', 'c')];
    const layout = buildDagLayout(nodes, edges);

    const a = layout.nodes.find((n) => n.id === 'a')!;
    const b = layout.nodes.find((n) => n.id === 'b')!;
    expect(a.centerY).toBe(b.centerY);
  });

  it('LR direction: horizontal ordering', () => {
    const nodes = [makeNode('a'), makeNode('b')];
    const edges = [makeEdge('a', 'b')];
    const layout = buildDagLayout(nodes, edges, 'LR');

    const a = layout.nodes.find((n) => n.id === 'a')!;
    const b = layout.nodes.find((n) => n.id === 'b')!;
    expect(a.centerX).toBeLessThan(b.centerX);
  });

  it('single node: positioned with empty edges', () => {
    const nodes = [makeNode('a')];
    const layout = buildDagLayout(nodes, []);

    expect(layout.nodes).toHaveLength(1);
    expect(layout.edges).toHaveLength(0);
    expect(layout.nodes[0].width).toBe(DAG_NODE_WIDTH);
    expect(layout.nodes[0].height).toBe(DAG_NODE_HEIGHT);
  });

  it('empty graph: empty arrays with default bounds', () => {
    const layout = buildDagLayout([], []);

    expect(layout.nodes).toHaveLength(0);
    expect(layout.edges).toHaveLength(0);
    expect(layout.width).toBeGreaterThanOrEqual(0);
    expect(layout.height).toBeGreaterThanOrEqual(0);
  });
});
