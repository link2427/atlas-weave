<script lang="ts">
  import { goto } from '$app/navigation';
  import { listen, type UnlistenFn } from '@tauri-apps/api/event';
  import { page } from '$app/stores';
  import { onDestroy, onMount } from 'svelte';

  import { getRecipeDetail } from '$lib/api/tauri/recipes';
  import { cancelRun, getRun, getRunEvents, getRunHistory, type RunDetail, type RunHistoryItem } from '$lib/api/tauri/runs';
  import DagViewer from '$lib/features/dag/DagViewer.svelte';
  import NodeDetail from '$lib/features/dag/NodeDetail.svelte';
  import RunLogViewer from '$lib/features/dag/RunLogViewer.svelte';
  import RunList from '$lib/features/run/RunList.svelte';
  import RunSummary from '$lib/features/run/RunSummary.svelte';
  import { dagStore } from '$lib/stores/dag';
  import {
    eventStore,
    normalizeRunStatus,
    type AtlasWeaveEvent
  } from '$lib/stores/events';

  const EVENT_PAGE_SIZE = 200;

  let loading = true;
  let loadingHistory = false;
  let loadingOlderEvents = false;
  let loadError = '';
  let mounted = false;
  let requestedRunId = '';
  let unlisten: UnlistenFn | null = null;
  let runDetail: RunDetail | null = null;
  let historyItems: RunHistoryItem[] = [];
  let cancelling = false;

  $: dagState = $dagStore;
  $: eventState = $eventStore;
  $: routeRunId = $page.params.id;
  $: selectedNode = dagState.nodes.find((node) => node.id === dagState.selectedNodeId) ?? null;
  $: selectedNodeEvents = selectedNode
    ? eventState.events.filter((event) => event.node_id === selectedNode.id)
    : [];
  $: canLoadOlder = eventState.events.length < eventState.total;
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
    runDetail = null;
    historyItems = [];
    cancelling = false;
    loading = true;
    loadError = '';

    try {
      const run = await getRun(runId);
      const [recipe, eventPage] = await Promise.all([
        getRecipeDetail(run.recipeName),
        getRunEvents(runId, undefined, 1, EVENT_PAGE_SIZE)
      ]);
      const events = eventPage.items.map(asAtlasWeaveEvent).reverse();

      runDetail = run;
      dagStore.hydrate(recipe, run);
      eventStore.setRun(
        run.id,
        normalizeRunStatus(run.status),
        events,
        eventPage.total,
        eventPage.page,
        eventPage.pageSize
      );
      void loadHistory(run.recipeName);

      if (run.status === 'running') {
        await attachListener(runId);
      }
    } catch (error) {
      dagStore.clear();
      eventStore.clear();
      runDetail = null;
      loadError = error instanceof Error ? error.message : 'Failed to load this run.';
    } finally {
      loading = false;
    }
  }

  async function loadHistory(recipeName: string): Promise<void> {
    loadingHistory = true;
    try {
      const history = await getRunHistory(recipeName, 1, 20);
      historyItems = history.items;
    } catch (error) {
      loadError = error instanceof Error ? error.message : 'Failed to load run history.';
    } finally {
      loadingHistory = false;
    }
  }

  async function loadOlderEvents(): Promise<void> {
    if (!runDetail || loadingOlderEvents || !canLoadOlder) {
      return;
    }

    loadingOlderEvents = true;
    try {
      const nextPage = eventState.page + 1;
      const response = await getRunEvents(runDetail.id, undefined, nextPage, eventState.pageSize || EVENT_PAGE_SIZE);
      eventStore.prependPage(response.items.map(asAtlasWeaveEvent).reverse(), response.page, response.total, response.pageSize);
    } finally {
      loadingOlderEvents = false;
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

      if (
        event.payload.type === 'run_completed' ||
        event.payload.type === 'run_failed' ||
        event.payload.type === 'run_cancelled'
      ) {
        void refreshRun(runId);
      }
    });
  }

  async function refreshRun(runId: string): Promise<void> {
    runDetail = await getRun(runId);
    if (runDetail.status !== 'running') {
      cleanupListener();
      cancelling = false;
    }
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
    runDetail = null;
  }

  async function handleCancel(): Promise<void> {
    if (!runDetail || cancelling) {
      return;
    }

    cancelling = true;
    try {
      await cancelRun(runDetail.id);
    } catch (error) {
      loadError = error instanceof Error ? error.message : 'Failed to cancel run.';
      cancelling = false;
    }
  }

  function asAtlasWeaveEvent(payload: Record<string, unknown>): AtlasWeaveEvent {
    return payload as AtlasWeaveEvent;
  }

  function formatTime(value?: string | null): string {
    return value ? new Date(value).toLocaleString() : '-';
  }

  function statusClasses(status: string | null): string {
    if (status === 'completed') {
      return 'status completed';
    }
    if (status === 'failed') {
      return 'status failed';
    }
    if (status === 'cancelled') {
      return 'status cancelled';
    }
    return 'status running';
  }
</script>

<svelte:head>
  <title>Atlas Weave Run</title>
  <meta name="description" content="Atlas Weave run detail and DAG visualizer" />
</svelte:head>

<div class="min-h-screen px-6 py-8 text-slate-50 lg:px-10">
  <div class="mx-auto max-w-[1600px] space-y-6">
    <section class="rounded-[32px] border border-white/10 bg-ink/70 p-6 shadow-glow">
      <div class="flex flex-col gap-5 border-b border-white/10 pb-6 xl:flex-row xl:items-end xl:justify-between">
        <div>
          <p class="text-xs uppercase tracking-[0.35em] text-sea">Atlas Weave Run</p>
          <h1 class="mt-3 text-3xl font-semibold text-mist">
            {dagState.recipe?.name ?? routeRunId}
          </h1>
          <p class="mt-3 text-sm text-slate-300">
            Run ID <code>{routeRunId}</code>
          </p>
          <div class="mt-4 flex flex-wrap gap-3">
            <button class="nav-button" on:click={() => goto('/')}>
              Back to launcher
            </button>
            <button class="nav-button alt" on:click={() => goto('/')}>
              Start another run
            </button>
          </div>
        </div>

        <div class="grid gap-3 text-sm text-slate-300 md:grid-cols-2 2xl:grid-cols-3">
          <div class="stat-card">
            <p class="eyebrow">Status</p>
            <p class={statusClasses(eventState.status !== 'idle' ? eventState.status : runDetail?.status ?? null)}>
              {eventState.status !== 'idle' ? eventState.status : runDetail?.status}
            </p>
          </div>
          <div class="stat-card">
            <p class="eyebrow">Started</p>
            <p class="stat-value">{formatTime(runDetail?.startedAt)}</p>
          </div>
          <div class="stat-card">
            <p class="eyebrow">Completed</p>
            <p class="stat-value">{formatTime(runDetail?.completedAt)}</p>
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
        <div class="mt-6 grid gap-6 2xl:grid-cols-[320px,minmax(0,1fr)]">
          <RunList
            recipeName={runDetail?.recipeName ?? ''}
            activeRunId={routeRunId}
            items={historyItems}
            loading={loadingHistory}
            on:select={(event) => goto(`/run/${event.detail.runId}`)}
          />

          <div class="space-y-6">
            <RunSummary
              run={runDetail}
              status={eventState.status !== 'idle' ? eventState.status : runDetail?.status ?? 'idle'}
              {cancelling}
              on:cancel={handleCancel}
            />

            <div class="rounded-[30px] border border-white/10 bg-white/4 p-4">
              <DagViewer
                nodes={dagState.nodes}
                edges={dagState.edges}
                selectedNodeId={dagState.selectedNodeId}
                on:select={(event) => dagStore.selectNode(event.detail.nodeId)}
              />
            </div>
          </div>
        </div>
      {/if}
    </section>

    {#if !loading && !loadError}
      <section class="grid gap-6 2xl:grid-cols-[minmax(0,1.05fr),minmax(420px,0.95fr)]">
        <NodeDetail node={selectedNode} events={selectedNodeEvents} />
        <RunLogViewer
          events={eventState.events}
          total={eventState.total}
          canLoadOlder={canLoadOlder}
          loadingOlder={loadingOlderEvents}
          on:loadOlder={loadOlderEvents}
        />
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

  .status.cancelled {
    color: #fde68a;
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

  .nav-button {
    border-radius: 9999px;
    border: 1px solid rgba(125, 211, 252, 0.25);
    background: rgba(8, 15, 30, 0.72);
    padding: 0.75rem 1rem;
    color: #e0f2fe;
    transition: border-color 160ms ease, background 160ms ease;
  }

  .nav-button:hover {
    border-color: rgba(125, 211, 252, 0.55);
    background: rgba(14, 116, 144, 0.2);
  }

  .nav-button.alt {
    border-color: rgba(45, 212, 191, 0.28);
    background: rgba(15, 118, 110, 0.18);
    color: #ccfbf1;
  }
</style>
