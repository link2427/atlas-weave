<script lang="ts">
  import { createEventDispatcher, onMount, tick } from 'svelte';

  import DagEdge from '$lib/features/dag/DagEdge.svelte';
  import DagNode from '$lib/features/dag/DagNode.svelte';
  import { buildDagLayout } from '$lib/features/dag/dag-layout';
  import type { DagEdgeState, DagNodeState } from '$lib/stores/dag';

  export let nodes: DagNodeState[] = [];
  export let edges: DagEdgeState[] = [];
  export let selectedNodeId: string | null = null;

  const dispatch = createEventDispatcher<{ select: { nodeId: string } }>();
  const padding = 88;

  let container: HTMLDivElement | null = null;
  let viewport = { x: 0, y: 0, scale: 1 };
  let hasInteracted = false;
  let drag:
    | {
        startClientX: number;
        startClientY: number;
        startX: number;
        startY: number;
      }
    | null = null;

  $: layout = buildDagLayout(nodes, edges);
  $: if (container && layout.nodes.length > 0 && !hasInteracted) {
    void tick().then(() => fitToView());
  }

  onMount(() => {
    if (!container) {
      return;
    }

    const observer = new ResizeObserver(() => {
      if (!hasInteracted) {
        fitToView();
      }
    });

    observer.observe(container);
    void tick().then(() => fitToView());

    return () => {
      observer.disconnect();
    };
  });

  function fitToView(): void {
    if (!container || layout.nodes.length === 0) {
      return;
    }

    const width = container.clientWidth;
    const height = container.clientHeight;
    const scaleX = (width - padding * 2) / Math.max(layout.width, 1);
    const scaleY = (height - padding * 2) / Math.max(layout.height, 1);
    const scale = Math.max(0.48, Math.min(Math.min(scaleX, scaleY), 1.24));

    viewport = {
      scale,
      x: (width - layout.width * scale) / 2 - layout.bounds.minX * scale,
      y: (height - layout.height * scale) / 2 - layout.bounds.minY * scale
    };
  }

  function clampScale(value: number): number {
    return Math.min(1.9, Math.max(0.42, value));
  }

  function handleWheel(event: WheelEvent): void {
    event.preventDefault();
    if (!container) {
      return;
    }

    const rect = container.getBoundingClientRect();
    const pointX = event.clientX - rect.left;
    const pointY = event.clientY - rect.top;
    const delta = event.deltaY < 0 ? 1.08 : 0.92;
    const nextScale = clampScale(viewport.scale * delta);
    const ratio = nextScale / viewport.scale;

    viewport = {
      scale: nextScale,
      x: pointX - (pointX - viewport.x) * ratio,
      y: pointY - (pointY - viewport.y) * ratio
    };
    hasInteracted = true;
  }

  function handlePointerDown(event: PointerEvent): void {
    if (event.button !== 0) {
      return;
    }

    drag = {
      startClientX: event.clientX,
      startClientY: event.clientY,
      startX: viewport.x,
      startY: viewport.y
    };
    hasInteracted = true;
  }

  function handlePointerMove(event: PointerEvent): void {
    if (!drag) {
      return;
    }

    viewport = {
      ...viewport,
      x: drag.startX + (event.clientX - drag.startClientX),
      y: drag.startY + (event.clientY - drag.startClientY)
    };
  }

  function handlePointerUp(): void {
    drag = null;
  }
</script>

<div class="dag-shell">
  <div class="dag-toolbar">
    <div>
      <p class="text-xs uppercase tracking-[0.28em] text-slate-400">Execution Graph</p>
      <p class="mt-2 text-sm text-slate-300">
        Zoom with the mouse wheel, drag to pan, click a node for detail.
      </p>
    </div>
    <button class="fit-button" on:click={() => ((hasInteracted = false), fitToView())}>
      Fit View
    </button>
  </div>

  <div
    bind:this={container}
    class="dag-canvas"
    role="presentation"
    on:wheel={handleWheel}
    on:pointerdown={handlePointerDown}
    on:pointermove={handlePointerMove}
    on:pointerup={handlePointerUp}
    on:pointerleave={handlePointerUp}
  >
    {#if layout.nodes.length === 0}
      <div class="empty-copy">No DAG nodes available for this run.</div>
    {:else}
      <svg class="h-full w-full" viewBox={`0 0 ${container?.clientWidth ?? 1200} ${container?.clientHeight ?? 720}`}>
        <g transform={`translate(${viewport.x} ${viewport.y}) scale(${viewport.scale})`}>
          {#each layout.edges as edge (edge.id)}
            <DagEdge {edge} />
          {/each}

          {#each layout.nodes as node (node.id)}
            <DagNode
              {node}
              selected={selectedNodeId === node.id}
              on:select={(event) => dispatch('select', event.detail)}
            />
          {/each}
        </g>
      </svg>
    {/if}
  </div>
</div>

<style>
  .dag-shell {
    display: flex;
    height: 100%;
    min-height: 520px;
    flex-direction: column;
  }

  .dag-toolbar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 1rem;
    padding-bottom: 1rem;
  }

  .dag-canvas {
    position: relative;
    flex: 1;
    overflow: hidden;
    border-radius: 1.5rem;
    border: 1px solid rgba(255, 255, 255, 0.08);
    background:
      radial-gradient(circle at top, rgba(56, 189, 248, 0.08), transparent 34%),
      linear-gradient(180deg, rgba(2, 6, 23, 0.84) 0%, rgba(7, 16, 29, 0.96) 100%);
    cursor: grab;
  }

  .dag-canvas:active {
    cursor: grabbing;
  }

  .fit-button {
    border-radius: 9999px;
    border: 1px solid rgba(125, 211, 252, 0.22);
    background: rgba(8, 15, 30, 0.72);
    padding: 0.7rem 1rem;
    color: #e0f2fe;
    transition: border-color 160ms ease, background 160ms ease;
  }

  .fit-button:hover {
    border-color: rgba(125, 211, 252, 0.52);
    background: rgba(14, 116, 144, 0.2);
  }

  .empty-copy {
    display: grid;
    height: 100%;
    place-items: center;
    color: rgba(226, 232, 240, 0.72);
  }
</style>
