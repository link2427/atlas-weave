<script lang="ts">
  import type { DagNodeState } from '$lib/stores/dag';

  export let node: DagNodeState;

  $: metrics = Object.entries(node.summary ?? {});

  function formatKey(key: string): string {
    return key
      .replace(/_/g, ' ')
      .replace(/\b\w/g, (char) => char.toUpperCase());
  }

  function formatTime(value: string | null): string {
    return value ? new Date(value).toLocaleString() : '-';
  }
</script>

<div class="space-y-5">
  <div class="grid gap-4 md:grid-cols-2">
    <div class="summary-card">
      <p class="eyebrow">Status</p>
      <div class="mt-3 flex items-center gap-3">
        <span class={`status-badge ${node.status}`}>{node.status}</span>
        <span class="text-sm text-slate-300">{node.message ?? 'No recent status message.'}</span>
      </div>
    </div>

    <div class="summary-card">
      <p class="eyebrow">Progress</p>
      <div class="mt-3">
        <div class="progress-rail">
          <div class="progress-fill" style={`width: ${Math.round((node.progress ?? 0) * 100)}%`}></div>
        </div>
        <p class="mt-3 text-sm text-slate-300">{Math.round((node.progress ?? 0) * 100)}% complete</p>
      </div>
    </div>
  </div>

  <div class="grid gap-4 md:grid-cols-3">
    <div class="summary-card">
      <p class="eyebrow">Started</p>
      <p class="mt-3 text-sm text-slate-200">{formatTime(node.startedAt)}</p>
    </div>
    <div class="summary-card">
      <p class="eyebrow">Completed</p>
      <p class="mt-3 text-sm text-slate-200">{formatTime(node.completedAt)}</p>
    </div>
    <div class="summary-card">
      <p class="eyebrow">Duration</p>
      <p class="mt-3 text-sm text-slate-200">
        {#if node.durationMs !== null}
          {node.durationMs} ms
        {:else}
          -
        {/if}
      </p>
    </div>
  </div>

  {#if node.error}
    <div class="rounded-[22px] border border-rose-400/30 bg-rose-500/10 px-4 py-4 text-sm text-rose-100">
      {node.error}
    </div>
  {/if}

  <div class="summary-card">
    <div class="flex items-center justify-between gap-3">
      <p class="eyebrow">Completion Summary</p>
      <span class="text-xs uppercase tracking-[0.26em] text-slate-500">{metrics.length} fields</span>
    </div>

    {#if metrics.length === 0}
      <p class="mt-4 text-sm text-slate-400">No structured summary has been emitted for this node yet.</p>
    {:else}
      <div class="mt-4 grid gap-3 md:grid-cols-2">
        {#each metrics as [key, value]}
          <div class="rounded-2xl border border-white/8 bg-black/20 px-4 py-3">
            <p class="text-xs uppercase tracking-[0.24em] text-slate-500">{formatKey(key)}</p>
            <p class="mt-2 break-words text-sm text-slate-100">
              {typeof value === 'object' ? JSON.stringify(value) : String(value)}
            </p>
          </div>
        {/each}
      </div>
    {/if}
  </div>
</div>

<style>
  .summary-card {
    border-radius: 1.5rem;
    border: 1px solid rgba(255, 255, 255, 0.08);
    background: rgba(255, 255, 255, 0.04);
    padding: 1rem 1.1rem;
  }

  .eyebrow {
    font-size: 0.72rem;
    letter-spacing: 0.24em;
    text-transform: uppercase;
    color: rgba(148, 163, 184, 0.84);
  }

  .status-badge {
    border-radius: 9999px;
    padding: 0.35rem 0.8rem;
    font-size: 0.78rem;
    letter-spacing: 0.18em;
    text-transform: uppercase;
  }

  .status-badge.pending {
    background: rgba(148, 163, 184, 0.16);
    color: #cbd5e1;
  }

  .status-badge.running {
    background: rgba(45, 212, 191, 0.18);
    color: #99f6e4;
  }

  .status-badge.completed {
    background: rgba(56, 189, 248, 0.18);
    color: #bae6fd;
  }

  .status-badge.failed {
    background: rgba(251, 113, 133, 0.18);
    color: #fecdd3;
  }

  .status-badge.skipped {
    background: rgba(251, 191, 36, 0.18);
    color: #fde68a;
  }

  .status-badge.cancelled {
    background: rgba(249, 115, 22, 0.18);
    color: #fdba74;
  }

  .progress-rail {
    overflow: hidden;
    border-radius: 9999px;
    background: rgba(148, 163, 184, 0.16);
  }

  .progress-fill {
    height: 0.7rem;
    border-radius: 9999px;
    background: linear-gradient(90deg, #2dd4bf 0%, #38bdf8 100%);
    transition: width 220ms ease;
  }
</style>
