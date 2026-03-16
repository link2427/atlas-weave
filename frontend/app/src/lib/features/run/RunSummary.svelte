<script lang="ts">
  import { createEventDispatcher } from 'svelte';

  import type { RunDetail, RunStatus } from '$lib/api/tauri/runs';

  export let run: RunDetail | null = null;
  export let status: RunStatus | 'idle' = 'idle';
  export let cancelling = false;

  const dispatch = createEventDispatcher<{ cancel: undefined }>();

  function formatTime(value?: string | null): string {
    return value ? new Date(value).toLocaleString() : '-';
  }

  function pretty(value: unknown): string {
    return JSON.stringify(value ?? {}, null, 2);
  }
</script>

<section class="panel">
  <div class="flex items-start justify-between gap-4">
    <div>
      <p class="eyebrow">Run Summary</p>
      <h3 class="mt-2 text-2xl font-semibold text-mist">{run?.recipeName ?? 'Run detail'}</h3>
      <p class="mt-2 text-sm text-slate-300">Status: <span class="capitalize">{status}</span></p>
    </div>

    {#if status === 'running'}
      <button class="cancel-button" disabled={cancelling} on:click={() => dispatch('cancel')}>
        {cancelling ? 'Cancelling...' : 'Cancel Run'}
      </button>
    {/if}
  </div>

  {#if run}
    <div class="mt-5 grid gap-4 md:grid-cols-3">
      <div class="stat-card">
        <p class="eyebrow">Started</p>
        <p class="mt-3 text-sm text-slate-200">{formatTime(run.startedAt)}</p>
      </div>
      <div class="stat-card">
        <p class="eyebrow">Completed</p>
        <p class="mt-3 text-sm text-slate-200">{formatTime(run.completedAt)}</p>
      </div>
      <div class="stat-card">
        <p class="eyebrow">Nodes</p>
        <p class="mt-3 text-sm text-slate-200">{run.nodes.length}</p>
      </div>
    </div>

    {#if run.error}
      <div class="error-panel">{run.error}</div>
    {/if}

    <div class="mt-5 grid gap-4 xl:grid-cols-2">
      <div class="json-panel">
        <div class="flex items-center justify-between gap-3">
          <p class="eyebrow">Persisted Config</p>
          <span class="text-xs uppercase tracking-[0.2em] text-slate-500">Redacted</span>
        </div>
        <pre>{pretty(run.config)}</pre>
      </div>
      <div class="json-panel">
        <div class="flex items-center justify-between gap-3">
          <p class="eyebrow">Run Summary</p>
          <span class="text-xs uppercase tracking-[0.2em] text-slate-500">Final output</span>
        </div>
        <pre>{pretty(run.summary)}</pre>
      </div>
    </div>
  {/if}
</section>

<style>
  .panel {
    border-radius: 2rem;
    border: 1px solid rgba(255, 255, 255, 0.08);
    background: rgba(255, 255, 255, 0.05);
    padding: 1.4rem;
  }

  .eyebrow {
    font-size: 0.72rem;
    letter-spacing: 0.24em;
    text-transform: uppercase;
    color: rgba(148, 163, 184, 0.84);
  }

  .cancel-button {
    border-radius: 9999px;
    border: 1px solid rgba(248, 113, 113, 0.35);
    background: rgba(127, 29, 29, 0.32);
    padding: 0.8rem 1rem;
    color: #fecaca;
  }

  .cancel-button:disabled {
    cursor: not-allowed;
    opacity: 0.65;
  }

  .stat-card,
  .json-panel {
    border-radius: 1.5rem;
    border: 1px solid rgba(255, 255, 255, 0.08);
    background: rgba(2, 6, 23, 0.4);
    padding: 1rem;
  }

  .error-panel {
    margin-top: 1rem;
    border-radius: 1.5rem;
    border: 1px solid rgba(251, 113, 133, 0.32);
    background: rgba(127, 29, 29, 0.24);
    padding: 1rem;
    color: #fecdd3;
  }

  pre {
    margin-top: 1rem;
    max-height: 14rem;
    overflow: auto;
    white-space: pre-wrap;
    word-break: break-word;
    color: #e2e8f0;
  }
</style>
