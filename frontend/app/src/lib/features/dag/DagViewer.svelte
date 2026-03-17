<script lang="ts">
  import { createEventDispatcher, onMount, tick } from 'svelte';

  import { Button } from '$lib/components/ui/button';
  import DagEdge from '$lib/features/dag/DagEdge.svelte';
  import DagNode from '$lib/features/dag/DagNode.svelte';
  import { buildDagLayout } from '$lib/features/dag/dag-layout';
  import type { DagEdgeState, DagNodeState } from '$lib/stores/dag';

  export let nodes: DagNodeState[] = [];
  export let edges: DagEdgeState[] = [];
  export let selectedNodeId: string | null = null;

  const dispatch = createEventDispatcher<{ select: { nodeId: string } }>();
  const padding = 56;

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
    if (!container) return;

    const observer = new ResizeObserver(() => {
      if (!hasInteracted) fitToView();
    });

    observer.observe(container);
    void tick().then(() => fitToView());

    return () => {
      observer.disconnect();
    };
  });

  function fitToView(): void {
    if (!container || layout.nodes.length === 0) return;
    const width = container.clientWidth;
    const height = container.clientHeight;
    const scaleX = (width - padding * 2) / Math.max(layout.width, 1);
    const scaleY = (height - padding * 2) / Math.max(layout.height, 1);
    const scale = Math.max(0.14, Math.min(Math.min(scaleX, scaleY), 1.3));
    viewport = {
      scale,
      x: (width - layout.width * scale) / 2 - layout.bounds.minX * scale,
      y: (height - layout.height * scale) / 2 - layout.bounds.minY * scale
    };
  }

  function clampScale(value: number): number {
    return Math.min(2.2, Math.max(0.06, value));
  }

  function handleWheel(event: WheelEvent): void {
    event.preventDefault();
    if (!container) return;
    const rect = container.getBoundingClientRect();
    const pointX = event.clientX - rect.left;
    const pointY = event.clientY - rect.top;
    const delta = event.deltaY < 0 ? 1.12 : 0.88;
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
    if (event.button !== 0) return;
    drag = {
      startClientX: event.clientX,
      startClientY: event.clientY,
      startX: viewport.x,
      startY: viewport.y
    };
    hasInteracted = true;
  }

  function handlePointerMove(event: PointerEvent): void {
    if (!drag) return;
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

<div class="flex h-full min-h-[600px] flex-col">
  <div class="flex items-center justify-between gap-4 pb-4">
    <div>
      <p class="text-xs font-medium uppercase tracking-widest text-muted-foreground">Execution Graph</p>
      <p class="mt-1 text-sm text-muted-foreground">
        Zoom with the mouse wheel, drag to pan, click a node for detail.
      </p>
    </div>
    <Button variant="outline" size="sm" onclick={() => ((hasInteracted = false), fitToView())}>
      Fit View
    </Button>
  </div>

  <div
    bind:this={container}
    class="relative flex-1 cursor-grab overflow-hidden rounded-lg border border-white/8 active:cursor-grabbing"
    style="background: radial-gradient(circle at top, rgba(56, 189, 248, 0.08), transparent 34%), linear-gradient(180deg, rgba(2, 6, 23, 0.84) 0%, rgba(7, 16, 29, 0.96) 100%);"
    role="presentation"
    on:wheel={handleWheel}
    on:pointerdown={handlePointerDown}
    on:pointermove={handlePointerMove}
    on:pointerup={handlePointerUp}
    on:pointerleave={handlePointerUp}
  >
    {#if layout.nodes.length === 0}
      <div class="grid h-full place-items-center text-muted-foreground">No DAG nodes available for this run.</div>
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
