<script lang="ts">
  import NodeLogs from '$lib/features/dag/NodeLogs.svelte';
  import NodeSummary from '$lib/features/dag/NodeSummary.svelte';
  import type { DagNodeState } from '$lib/stores/dag';
  import type { AtlasWeaveEvent } from '$lib/stores/events';

  export let node: DagNodeState | null = null;
  export let events: AtlasWeaveEvent[] = [];

  let activeTab: 'summary' | 'logs' | 'tools' | 'data' = 'summary';

  $: if (!node) {
    activeTab = 'summary';
  }
</script>

<section class="detail-shell">
  <div class="detail-header">
    <div>
      <p class="text-xs uppercase tracking-[0.3em] text-slate-400">Node Detail</p>
      <h3 class="mt-2 text-2xl font-semibold text-mist">
        {node?.label ?? 'Select a node'}
      </h3>
      <p class="mt-2 text-sm text-slate-300">
        {node?.description ?? 'Click a node in the DAG to inspect its state, logs, and outputs.'}
      </p>
    </div>
  </div>

  {#if node}
    <div class="tab-row">
      {#each [
        ['summary', 'Summary'],
        ['logs', 'Logs'],
        ['tools', 'Tools'],
        ['data', 'Data']
      ] as [tabId, label]}
        <button
          class:active={activeTab === tabId}
          class="tab-button"
          on:click={() => (activeTab = tabId as typeof activeTab)}
        >
          {label}
        </button>
      {/each}
    </div>

    <div class="mt-5">
      {#if activeTab === 'summary'}
        <NodeSummary {node} />
      {:else if activeTab === 'logs'}
        <NodeLogs {events} />
      {:else if activeTab === 'tools'}
        <div class="empty-panel">
          Tool call inspection arrives in a later phase once agents emit structured tool traces.
        </div>
      {:else}
        <div class="empty-panel">
          Data inspection arrives in a later phase once recipe output databases are exposed read-only.
        </div>
      {/if}
    </div>
  {:else}
    <div class="empty-panel mt-5">
      No node is selected yet.
    </div>
  {/if}
</section>

<style>
  .detail-shell {
    height: 100%;
    border-radius: 2rem;
    border: 1px solid rgba(255, 255, 255, 0.08);
    background: rgba(255, 255, 255, 0.05);
    padding: 1.4rem;
  }

  .detail-header {
    border-bottom: 1px solid rgba(255, 255, 255, 0.08);
    padding-bottom: 1rem;
  }

  .tab-row {
    display: flex;
    flex-wrap: wrap;
    gap: 0.75rem;
    padding-top: 1.25rem;
  }

  .tab-button {
    border-radius: 9999px;
    border: 1px solid rgba(255, 255, 255, 0.08);
    background: rgba(2, 6, 23, 0.45);
    padding: 0.65rem 1rem;
    color: #cbd5e1;
    transition: border-color 160ms ease, background 160ms ease, color 160ms ease;
  }

  .tab-button:hover,
  .tab-button.active {
    border-color: rgba(125, 211, 252, 0.45);
    background: rgba(14, 116, 144, 0.18);
    color: #f0f9ff;
  }

  .empty-panel {
    border-radius: 1.5rem;
    border: 1px dashed rgba(148, 163, 184, 0.26);
    background: rgba(2, 6, 23, 0.35);
    padding: 1.25rem;
    color: rgba(203, 213, 225, 0.88);
  }
</style>
