<script lang="ts">
  import NodeLogs from '$lib/features/dag/NodeLogs.svelte';
  import type { AtlasWeaveEvent } from '$lib/stores/events';

  export let events: AtlasWeaveEvent[] = [];
</script>

<section class="log-panel">
  <div class="mb-4 flex items-center justify-between gap-3">
    <div>
      <p class="text-xs uppercase tracking-[0.3em] text-slate-400">Run Log</p>
      <h3 class="mt-2 text-xl font-semibold text-mist">Live Event Stream</h3>
    </div>
    <span class="text-xs uppercase tracking-[0.24em] text-slate-500">{events.length} events</span>
  </div>

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
</style>
