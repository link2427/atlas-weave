<script lang="ts">
  import { createEventDispatcher } from 'svelte';

  import NodeLogs from '$lib/features/dag/NodeLogs.svelte';
  import type { AtlasWeaveEvent } from '$lib/stores/events';

  export let events: AtlasWeaveEvent[] = [];
  export let total = 0;
  export let canLoadOlder = false;
  export let loadingOlder = false;

  const dispatch = createEventDispatcher<{ loadOlder: undefined }>();
</script>

<section class="log-panel">
  <div class="mb-4 flex items-center justify-between gap-3">
    <div>
      <p class="text-xs uppercase tracking-[0.3em] text-slate-400">Run Log</p>
      <h3 class="mt-2 text-xl font-semibold text-mist">Persisted Event Stream</h3>
    </div>
    <span class="text-xs uppercase tracking-[0.24em] text-slate-500">{events.length}/{total} events</span>
  </div>

  {#if canLoadOlder}
    <button class="load-button" disabled={loadingOlder} on:click={() => dispatch('loadOlder')}>
      {loadingOlder ? 'Loading...' : 'Load older events'}
    </button>
  {/if}

  <NodeLogs {events} />
</section>

<style>
  .log-panel {
    height: 100%;
    border-radius: 2rem;
    border: 1px solid rgba(255, 255, 255, 0.08);
    background: rgba(255, 255, 255, 0.05);
    padding: 1.4rem;
  }

  .load-button {
    margin-bottom: 1rem;
    border-radius: 9999px;
    border: 1px solid rgba(125, 211, 252, 0.28);
    background: rgba(14, 116, 144, 0.22);
    padding: 0.65rem 0.95rem;
    color: #bae6fd;
  }
</style>
