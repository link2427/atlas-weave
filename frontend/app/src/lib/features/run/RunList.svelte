<script lang="ts">
  import { createEventDispatcher } from 'svelte';

  import type { RunHistoryItem } from '$lib/api/tauri/runs';

  export let recipeName = '';
  export let activeRunId = '';
  export let items: RunHistoryItem[] = [];
  export let loading = false;

  const dispatch = createEventDispatcher<{ select: { runId: string } }>();

  function formatTime(value?: string | null): string {
    return value ? new Date(value).toLocaleString() : '-';
  }
</script>

<aside class="panel">
  <div class="mb-5">
    <p class="eyebrow">Run History</p>
    <h3 class="mt-2 text-xl font-semibold text-mist">
      {recipeName || 'Recipe history'}
    </h3>
  </div>

  {#if loading}
    <div class="empty-state">Loading runs...</div>
  {:else if items.length === 0}
    <div class="empty-state">No recorded runs for this recipe yet.</div>
  {:else}
    <div class="space-y-3">
      {#each items as item}
        <button
          class:active={item.id === activeRunId}
          class="history-item"
          on:click={() => dispatch('select', { runId: item.id })}
        >
          <div class="flex items-center justify-between gap-4">
            <div>
              <p class="font-medium text-mist">{item.status}</p>
              <p class="mt-1 text-xs text-slate-400">{formatTime(item.startedAt)}</p>
            </div>
            <span class="text-xs text-slate-500">{item.completedNodes}/{item.completedNodes + item.failedNodes + item.skippedNodes + item.cancelledNodes + item.runningNodes + item.pendingNodes} nodes</span>
          </div>
          {#if item.error}
            <p class="mt-3 text-sm text-rose-200">{item.error}</p>
          {/if}
        </button>
      {/each}
    </div>
  {/if}
</aside>

<style>
  .panel {
    border-radius: 2rem;
    border: 1px solid rgba(255, 255, 255, 0.08);
    background: rgba(255, 255, 255, 0.05);
    padding: 1.25rem;
  }

  .eyebrow {
    font-size: 0.72rem;
    letter-spacing: 0.24em;
    text-transform: uppercase;
    color: rgba(148, 163, 184, 0.84);
  }

  .empty-state {
    border-radius: 1.5rem;
    border: 1px dashed rgba(148, 163, 184, 0.26);
    background: rgba(2, 6, 23, 0.35);
    padding: 1rem;
    color: rgba(203, 213, 225, 0.88);
  }

  .history-item {
    width: 100%;
    border-radius: 1.5rem;
    border: 1px solid rgba(255, 255, 255, 0.08);
    background: rgba(2, 6, 23, 0.35);
    padding: 0.95rem 1rem;
    text-align: left;
    transition: border-color 160ms ease, background 160ms ease;
  }

  .history-item.active,
  .history-item:hover {
    border-color: rgba(125, 211, 252, 0.35);
    background: rgba(14, 116, 144, 0.18);
  }
</style>
