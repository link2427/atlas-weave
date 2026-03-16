<script lang="ts">
  import { listen, type UnlistenFn } from '@tauri-apps/api/event';
  import { page } from '$app/stores';
  import { onDestroy, onMount } from 'svelte';

  import DagViewer from '$lib/features/dag/DagViewer.svelte';
  import NodeDetail from '$lib/features/dag/NodeDetail.svelte';
  import RunLogViewer from '$lib/features/dag/RunLogViewer.svelte';
  import { getRecipeDetail } from '$lib/api/tauri/recipes';
  import { getRun, getRunEvents } from '$lib/api/tauri/runs';
  import { dagStore } from '$lib/stores/dag';
  import {
    eventStore,
    normalizeRunStatus,
    type AtlasWeaveEvent,
    type RunViewStatus
  } from '$lib/stores/events';

  let loading = true;
  let loadError = '';
  let mounted = false;
  let requestedRunId = '';
  let unlisten: UnlistenFn | null = null;
  let runStartedAt: string | null = null;
  let runCompletedAt: string | null = null;

  $: dagState = $dagStore;
  $: eventState = $eventStore;
  $: routeRunId = $page.params.id;
  $: latestRunTerminalEvent =
    [...eventState.events].reverse().find((event) => event.type === 'run_completed' || event.type === 'run_failed') ??
    null;
  $: selectedNode = dagState.nodes.find((node) => node.id === dagState.selectedNodeId) ?? null;
  $: selectedNodeEvents = selectedNode
    ? eventState.events.filter((event) => event.node_id === selectedNode.id)
    : [];
  $: if (mounted && routeRunId && routeRunId !== requestedRunId) {
    requestedRunId = routeRunId;
    void initializeRun(routeRunId);
  }

  onMount(() => {
    mounted = true;
  });

  onDestroy(() => {
    cleanup();
  });

  async function initializeRun(runId: string): Promise<void> {
    cleanupListener();
    dagStore.clear();
    eventStore.clear();
    runStartedAt = null;
    runCompletedAt = null;
    loading = true;
    loadError = '';

    try {
      const run = await getRun(runId);
      const [recipe, rawEvents] = await Promise.all([getRecipeDetail(run.recipeName), getRunEvents(runId)]);
      const events = rawEvents.map(asAtlasWeaveEvent).filter((event) => event.run_id === runId);

      dagStore.hydrate(recipe, run);
      eventStore.setRun(run.id, normalizeRunStatus(run.status), events);
      runStartedAt = run.startedAt ?? null;
      runCompletedAt = run.completedAt ?? null;
      await attachListener(runId);
    } catch (error) {
      dagStore.clear();
      eventStore.clear();
      runStartedAt = null;
      runCompletedAt = null;
      loadError = error instanceof Error ? error.message : 'Failed to load this run.';
    } finally {
      loading = false;
    }
  }

  async function attachListener(runId: string): Promise<void> {
    cleanupListener();
    unlisten = await listen<AtlasWeaveEvent>('atlas-weave:event', (event) => {
      if (event.payload.run_id !== runId) {
        return;
      }

      eventStore.push(event.payload);
      dagStore.applyEvent(event.payload);
    });
  }

  function cleanupListener(): void {
    if (unlisten) {
      void unlisten();
      unlisten = null;
    }
  }

  function cleanup(): void {
    cleanupListener();
    dagStore.clear();
    eventStore.clear();
    runStartedAt = null;
    runCompletedAt = null;
  }

  function asAtlasWeaveEvent(payload: Record<string, unknown>): AtlasWeaveEvent {
    return payload as AtlasWeaveEvent;
  }

  function formatTime(value?: string | null): string {
    return value ? new Date(value).toLocaleString() : '—';
  }

  function statusClasses(status: RunViewStatus | null): string {
    if (status === 'completed') {
      return 'status completed';
    }
    if (status === 'failed') {
      return 'status failed';
    }
    return 'status running';
  }
</script>

<svelte:head>
  <title>Atlas Weave Run</title>
  <meta name="description" content="Atlas Weave run detail and DAG visualizer" />
</svelte:head>

<div class="min-h-screen px-6 py-8 text-slate-50 lg:px-10">
  <div class="mx-auto max-w-7xl space-y-6">
    <section class="rounded-[32px] border border-white/10 bg-ink/70 p-6 shadow-glow">
      <div class="flex flex-col gap-5 border-b border-white/10 pb-6 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <p class="text-xs uppercase tracking-[0.35em] text-sea">Atlas Weave Run</p>
          <h1 class="mt-3 text-3xl font-semibold text-mist">
            {dagState.recipe?.name ?? routeRunId}
          </h1>
          <p class="mt-3 text-sm text-slate-300">
            Run ID <code>{routeRunId}</code>
          </p>
        </div>

        <div class="grid gap-3 text-sm text-slate-300 md:grid-cols-3">
          <div class="stat-card">
            <p class="eyebrow">Status</p>
            <p class={statusClasses(eventState.status)}>{eventState.status}</p>
          </div>
          <div class="stat-card">
            <p class="eyebrow">Started</p>
            <p class="stat-value">{formatTime(runStartedAt)}</p>
          </div>
          <div class="stat-card">
            <p class="eyebrow">Completed</p>
            <p class="stat-value">{formatTime(latestRunTerminalEvent?.timestamp ?? runCompletedAt)}</p>
          </div>
        </div>
      </div>

      {#if loading}
        <div class="empty-state">Loading run graph...</div>
      {:else if loadError}
        <div class="mt-6 rounded-[28px] border border-rose-400/30 bg-rose-500/10 px-5 py-5 text-sm text-rose-100">
          <p class="font-semibold">Run could not be loaded.</p>
          <p class="mt-2">{loadError}</p>
          <a class="mt-4 inline-flex text-sm text-rose-50 underline" href="/">Back to recipes</a>
        </div>
      {:else}
        <div class="mt-6 rounded-[30px] border border-white/10 bg-white/4 p-4">
          <DagViewer
            nodes={dagState.nodes}
            edges={dagState.edges}
            selectedNodeId={dagState.selectedNodeId}
            on:select={(event) => dagStore.selectNode(event.detail.nodeId)}
          />
        </div>
      {/if}
    </section>

    {#if !loading && !loadError}
      <section class="grid gap-6 xl:grid-cols-[1.15fr,0.85fr]">
        <NodeDetail node={selectedNode} events={selectedNodeEvents} />
        <RunLogViewer events={eventState.events} />
      </section>
    {/if}
  </div>
</div>

<style>
  .stat-card {
    border-radius: 1.35rem;
    border: 1px solid rgba(255, 255, 255, 0.08);
    background: rgba(255, 255, 255, 0.04);
    padding: 0.9rem 1rem;
  }

  .eyebrow {
    font-size: 0.72rem;
    letter-spacing: 0.24em;
    text-transform: uppercase;
    color: rgba(148, 163, 184, 0.84);
  }

  .status {
    margin-top: 0.75rem;
    font-size: 0.95rem;
    font-weight: 600;
    text-transform: capitalize;
  }

  .status.running {
    color: #99f6e4;
  }

  .status.completed {
    color: #bae6fd;
  }

  .status.failed {
    color: #fecdd3;
  }

  .stat-value {
    margin-top: 0.75rem;
    color: #e2e8f0;
  }

  .empty-state {
    display: grid;
    min-height: 26rem;
    place-items: center;
    color: rgba(226, 232, 240, 0.76);
  }
</style>
