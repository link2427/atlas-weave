<script lang="ts">
  import { createEventDispatcher, onMount, tick } from 'svelte';

  import { Button } from '$lib/components/ui/button';
  import DagEdge from '$lib/features/dag/DagEdge.svelte';
  import DagNode from '$lib/features/dag/DagNode.svelte';
  import { buildDagLayout } from '$lib/features/dag/dag-layout';
  import type { DagEdgeState, DagNodeState, DagNodeStatus } from '$lib/stores/dag';

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
  $: zoomPercent = Math.round(viewport.scale * 100);
  $: showMinimap = layout.nodes.length > 3;

  const minimapFillByStatus: Record<DagNodeStatus, string> = {
    pending: '#64748b',
    running: '#34d399',
    completed: '#38bdf8',
    failed: '#f43f5e',
    skipped: '#eab308',
    cancelled: '#fb923c'
  };

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

  function zoomBy(factor: number): void {
    if (!container) return;
    const cx = container.clientWidth / 2;
    const cy = container.clientHeight / 2;
    const nextScale = clampScale(viewport.scale * factor);
    const ratio = nextScale / viewport.scale;
    viewport = {
      scale: nextScale,
      x: cx - (cx - viewport.x) * ratio,
      y: cy - (cy - viewport.y) * ratio
    };
    hasInteracted = true;
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

  function handleMinimapClick(event: MouseEvent): void {
    if (!container) return;
    const svg = event.currentTarget as SVGSVGElement;
    const rect = svg.getBoundingClientRect();
    const clickX = event.clientX - rect.left;
    const clickY = event.clientY - rect.top;
    const minimapScale = Math.min(160 / Math.max(layout.width, 1), 120 / Math.max(layout.height, 1)) * 0.85;
    const dagX = (clickX - 4) / minimapScale + layout.bounds.minX;
    const dagY = (clickY - 4) / minimapScale + layout.bounds.minY;
    viewport = {
      ...viewport,
      x: container.clientWidth / 2 - dagX * viewport.scale,
      y: container.clientHeight / 2 - dagY * viewport.scale
    };
    hasInteracted = true;
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
    <div class="flex items-center gap-1">
      <Button variant="outline" size="sm" onclick={() => zoomBy(0.8)}>
        &minus;
      </Button>
      <span class="w-12 text-center text-xs text-muted-foreground">{zoomPercent}%</span>
      <Button variant="outline" size="sm" onclick={() => zoomBy(1.25)}>
        +
      </Button>
      <Button variant="outline" size="sm" onclick={() => ((hasInteracted = false), fitToView())}>
        Fit View
      </Button>
    </div>
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

      {#if showMinimap}
        {@const minimapW = 160}
        {@const minimapH = 120}
        {@const minimapScale = Math.min(minimapW / Math.max(layout.width, 1), minimapH / Math.max(layout.height, 1)) * 0.85}
        {@const containerW = container?.clientWidth ?? 1200}
        {@const containerH = container?.clientHeight ?? 720}
        {@const vpX = (-viewport.x / viewport.scale - layout.bounds.minX) * minimapScale + 4}
        {@const vpY = (-viewport.y / viewport.scale - layout.bounds.minY) * minimapScale + 4}
        {@const vpW = (containerW / viewport.scale) * minimapScale}
        {@const vpH = (containerH / viewport.scale) * minimapScale}
        <!-- svelte-ignore a11y-click-events-have-key-events -->
        <svg
          class="absolute bottom-3 right-3 cursor-pointer rounded border border-white/10 backdrop-blur"
          style="background: rgba(8, 17, 31, 0.8);"
          width={minimapW}
          height={minimapH}
          role="presentation"
          on:click={handleMinimapClick}
        >
          {#each layout.nodes as node}
            <rect
              x={(node.centerX - layout.bounds.minX) * minimapScale + 4 - 3}
              y={(node.centerY - layout.bounds.minY) * minimapScale + 4 - 2}
              width="6"
              height="4"
              rx="1"
              fill={minimapFillByStatus[node.status] ?? '#64748b'}
            />
          {/each}
          <rect
            x={vpX}
            y={vpY}
            width={vpW}
            height={vpH}
            fill="rgba(56, 189, 248, 0.08)"
            stroke="rgba(56, 189, 248, 0.4)"
            stroke-width="1"
            rx="2"
          />
        </svg>
      {/if}
    {/if}
  </div>
</div>
