<script lang="ts">
  import { createEventDispatcher } from 'svelte';

  import { Badge } from '$lib/components/ui/badge';
  import { ScrollArea } from '$lib/components/ui/scroll-area';
  import { Skeleton } from '$lib/components/ui/skeleton';
  import type { RunHistoryItem } from '$lib/api/tauri/runs';

  export let recipeName = '';
  export let activeRunId = '';
  export let items: RunHistoryItem[] = [];
  export let loading = false;

  const dispatch = createEventDispatcher<{ select: { runId: string } }>();

  function formatTime(value?: string | null): string {
    return value ? new Date(value).toLocaleString() : '-';
  }

  function statusVariant(s: string): 'running' | 'completed' | 'failed' | 'cancelled' | 'pending' {
    if (s === 'completed') return 'completed';
    if (s === 'failed') return 'failed';
    if (s === 'cancelled') return 'cancelled';
    if (s === 'running') return 'running';
    return 'pending';
  }
</script>

<aside class="rounded-xl border border-white/8 bg-white/[0.04] p-4">
  <div class="mb-4">
    <p class="text-xs font-medium uppercase tracking-widest text-muted-foreground">Run History</p>
    <h3 class="mt-2 text-lg font-semibold text-mist">
      {recipeName || 'Recipe history'}
    </h3>
  </div>

  {#if loading}
    <div class="space-y-3">
      <Skeleton class="h-16 w-full" />
      <Skeleton class="h-16 w-full" />
      <Skeleton class="h-16 w-full" />
    </div>
  {:else if items.length === 0}
    <div class="rounded-lg border border-dashed border-white/10 bg-black/20 p-4 text-sm text-muted-foreground">
      No recorded runs for this recipe yet.
    </div>
  {:else}
    <ScrollArea class="max-h-[32rem]">
      <div class="space-y-2">
        {#each items as item}
          <button
            class="w-full rounded-lg border bg-black/20 p-3 text-left transition hover:bg-white/5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring {item.id === activeRunId ? 'border-sky-400/40 bg-sky-950/20' : 'border-white/8 hover:border-sky-400/30'}"
            on:click={() => dispatch('select', { runId: item.id })}
          >
            <div class="flex items-center justify-between gap-3">
              <div class="min-w-0">
                <Badge variant={statusVariant(item.status)}>{item.status}</Badge>
                <p class="mt-1.5 truncate text-xs text-muted-foreground">{formatTime(item.startedAt)}</p>
              </div>
              <span class="text-xs text-muted-foreground">
                {item.completedNodes}/{item.completedNodes + item.failedNodes + item.skippedNodes + item.cancelledNodes + item.runningNodes + item.pendingNodes} nodes
              </span>
            </div>
            {#if item.error}
              <p class="mt-2 truncate text-xs text-rose-300">{item.error}</p>
            {/if}
          </button>
        {/each}
      </div>
    </ScrollArea>
  {/if}
</aside>
