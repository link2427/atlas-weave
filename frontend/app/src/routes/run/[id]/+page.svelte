<script lang="ts">
  import { goto } from '$app/navigation';
  import { listen, type UnlistenFn } from '@tauri-apps/api/event';
  import { page } from '$app/stores';
  import { onDestroy, onMount } from 'svelte';

  import { Button } from '$lib/components/ui/button';
  import { Badge } from '$lib/components/ui/badge';
  import { Card, CardHeader, CardTitle, CardContent } from '$lib/components/ui/card';
  import { Skeleton } from '$lib/components/ui/skeleton';
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
    ? eventStore.getNodeEvents(eventState, selectedNode.id)
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
    if (!runDetail || loadingOlderEvents || !canLoadOlder) return;
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
      if (event.payload.run_id !== runId) return;
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
    if (!runDetail || cancelling) return;
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

  function statusVariant(s: string | null): 'running' | 'completed' | 'failed' | 'cancelled' | 'pending' {
    if (s === 'completed') return 'completed';
    if (s === 'failed') return 'failed';
    if (s === 'cancelled') return 'cancelled';
    if (s === 'running') return 'running';
    return 'pending';
  }
</script>

<svelte:head>
  <title>Atlas Weave Run</title>
  <meta name="description" content="Atlas Weave run detail and DAG visualizer" />
</svelte:head>

<div class="min-h-screen px-6 py-8 text-slate-50 lg:px-10">
  <div class="mx-auto max-w-[1600px] space-y-6">
    <section class="rounded-xl border border-white/10 bg-ink/70 p-6 shadow-glow">
      <div class="flex flex-col gap-5 border-b border-white/8 pb-6 xl:flex-row xl:items-end xl:justify-between">
        <div>
          <p class="text-xs font-medium uppercase tracking-widest text-sea">Atlas Weave Run</p>
          <h1 class="mt-3 text-3xl font-semibold text-mist">
            {dagState.recipe?.name ?? routeRunId}
          </h1>
          <p class="mt-2 text-sm text-muted-foreground">
            Run ID <code class="text-xs">{routeRunId}</code>
          </p>
          <div class="mt-4 flex flex-wrap gap-3">
            <Button variant="outline" onclick={() => goto('/')}>Back to launcher</Button>
            <Button variant="outline" onclick={() => goto('/')}>Start another run</Button>
          </div>
        </div>

        <div class="grid gap-3 text-sm md:grid-cols-2 2xl:grid-cols-3">
          <Card>
            <CardHeader><CardTitle>Status</CardTitle></CardHeader>
            <CardContent>
              <Badge variant={statusVariant(eventState.status !== 'idle' ? eventState.status : runDetail?.status ?? null)}>
                {eventState.status !== 'idle' ? eventState.status : runDetail?.status ?? 'loading'}
              </Badge>
            </CardContent>
          </Card>
          <Card>
            <CardHeader><CardTitle>Started</CardTitle></CardHeader>
            <CardContent><p class="text-sm text-slate-200">{formatTime(runDetail?.startedAt)}</p></CardContent>
          </Card>
          <Card>
            <CardHeader><CardTitle>Completed</CardTitle></CardHeader>
            <CardContent><p class="text-sm text-slate-200">{formatTime(runDetail?.completedAt)}</p></CardContent>
          </Card>
        </div>
      </div>

      {#if loading}
        <div class="mt-6 space-y-4">
          <div class="grid gap-4 2xl:grid-cols-[320px,minmax(0,1fr)]">
            <div class="space-y-3">
              <Skeleton class="h-16 w-full" />
              <Skeleton class="h-16 w-full" />
              <Skeleton class="h-16 w-full" />
            </div>
            <Skeleton class="h-96 w-full" />
          </div>
        </div>
      {:else if loadError}
        <div class="mt-6 rounded-lg border border-rose-400/30 bg-rose-500/10 p-6 text-sm text-rose-100">
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
            on:select={(event: CustomEvent<{ runId: string }>) => goto(`/run/${event.detail.runId}`)}
          />

          <div class="space-y-6">
            <RunSummary
              run={runDetail}
              status={eventState.status !== 'idle' ? eventState.status : runDetail?.status ?? 'idle'}
              {cancelling}
              on:cancel={handleCancel}
            />

            <div class="rounded-lg border border-white/8 bg-white/[0.03] p-4">
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
        <NodeDetail node={selectedNode} events={selectedNodeEvents} run={runDetail} />
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
