import dagre from '@dagrejs/dagre';

import type { DagEdgeState, DagNodeState } from '$lib/stores/dag';

export const DAG_NODE_WIDTH = 112;
export const DAG_NODE_HEIGHT = 112;

export type DagLayoutNode = DagNodeState & {
  x: number;
  y: number;
  width: number;
  height: number;
  centerX: number;
  centerY: number;
};

export type DagLayoutEdge = DagEdgeState & {
  path: string;
};

export type DagLayoutModel = {
  nodes: DagLayoutNode[];
  edges: DagLayoutEdge[];
  width: number;
  height: number;
  bounds: {
    minX: number;
    minY: number;
    maxX: number;
    maxY: number;
  };
};

export function buildDagLayout(
  nodes: DagNodeState[],
  edges: DagEdgeState[],
  direction: 'TB' | 'LR' = 'TB'
): DagLayoutModel {
  const graph = new dagre.graphlib.Graph();
  graph.setGraph({
    rankdir: direction,
    nodesep: 40,
    ranksep: 76,
    marginx: 40,
    marginy: 40
  });
  graph.setDefaultEdgeLabel(() => ({}));

  for (const node of nodes) {
    graph.setNode(node.id, {
      width: DAG_NODE_WIDTH,
      height: DAG_NODE_HEIGHT
    });
  }

  for (const edge of edges) {
    graph.setEdge(edge.source, edge.target);
  }

  dagre.layout(graph);

  const positionedNodes = nodes.map((node) => {
    const layout = graph.node(node.id) as { x: number; y: number };
    const x = layout.x - DAG_NODE_WIDTH / 2;
    const y = layout.y - DAG_NODE_HEIGHT / 2;

    return {
      ...node,
      x,
      y,
      width: DAG_NODE_WIDTH,
      height: DAG_NODE_HEIGHT,
      centerX: layout.x,
      centerY: layout.y
    };
  });

  const nodeLookup = new Map(positionedNodes.map((node) => [node.id, node]));
  const positionedEdges = edges.map((edge) => {
    const source = nodeLookup.get(edge.source);
    const target = nodeLookup.get(edge.target);

    if (!source || !target) {
      return {
        ...edge,
        path: ''
      };
    }

    const startX = source.centerX;
    const startY = source.y + source.height;
    const endX = target.centerX;
    const endY = target.y;
    const controlY = startY + (endY - startY) / 2;

    return {
      ...edge,
      path: `M ${startX} ${startY} C ${startX} ${controlY}, ${endX} ${controlY}, ${endX} ${endY}`
    };
  });

  const xs = positionedNodes.flatMap((node) => [node.x, node.x + node.width]);
  const ys = positionedNodes.flatMap((node) => [node.y, node.y + node.height]);
  const minX = xs.length > 0 ? Math.min(...xs) : 0;
  const minY = ys.length > 0 ? Math.min(...ys) : 0;
  const maxX = xs.length > 0 ? Math.max(...xs) : DAG_NODE_WIDTH;
  const maxY = ys.length > 0 ? Math.max(...ys) : DAG_NODE_HEIGHT;

  return {
    nodes: positionedNodes,
    edges: positionedEdges,
    width: maxX - minX,
    height: maxY - minY,
    bounds: {
      minX,
      minY,
      maxX,
      maxY
    }
  };
}
