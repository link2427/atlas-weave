<script lang="ts">
  import { createEventDispatcher } from 'svelte';

  import type { RunDetail, RunStatus } from '$lib/api/tauri/runs';

  export let run: RunDetail | null = null;
  export let status: RunStatus | 'idle' = 'idle';
  export let cancelling = false;

  const dispatch = createEventDispatcher<{ cancel: undefined }>();

  $: summary = (run?.summary ?? {}) as Record<string, unknown>;
  $: toolCalls = numberValue(summary.tool_calls);
  $: llmCalls = numberValue(summary.llm_calls);
  $: promptTokens = numberValue(summary.llm_prompt_tokens);
  $: completionTokens = numberValue(summary.llm_completion_tokens);
  $: llmCostUsd = numberValue(summary.llm_cost_usd);
  $: totalRecords = numberValue(summary.total_records);
  $: activeRecords = numberValue(summary.active_records);
  $: researchedRecords = numberValue(summary.researched_records);
  $: acceptedLlmRecords = numberValue(summary.accepted_llm_records);
  $: anomalyCount = numberValue(summary.anomaly_count);
  $: coverageOperatorPurpose = numberValue(summary.coverage_operator_purpose_pct);
  $: coverageMass = numberValue(summary.coverage_mass_pct);
  $: outputDbPath = stringValue(summary.output_db_path);
  $: latestDbPath = stringValue(summary.latest_db_path);
  $: sourceStatus = recordValue(summary.source_status);
  $: cachedSources = stringArrayValue(summary.cached_sources);
  $: staleSources = stringArrayValue(summary.stale_sources);
  $: spaceTrackMode = stringValue(summary.space_track_mode);
  $: llmResearchStatus = stringValue(summary.llm_research_status);
  $: showUsageStats =
    toolCalls > 0 || llmCalls > 0 || promptTokens > 0 || completionTokens > 0 || llmCostUsd > 0;
  $: showSatelliteStats =
    totalRecords > 0 ||
    activeRecords > 0 ||
    researchedRecords > 0 ||
    acceptedLlmRecords > 0 ||
    anomalyCount > 0 ||
    coverageOperatorPurpose > 0 ||
    coverageMass > 0 ||
    Boolean(outputDbPath) ||
    Boolean(latestDbPath);
  $: showSourceStats =
    Object.keys(sourceStatus).length > 0 ||
    cachedSources.length > 0 ||
    staleSources.length > 0 ||
    Boolean(spaceTrackMode) ||
    Boolean(llmResearchStatus);

  function formatTime(value?: string | null): string {
    return value ? new Date(value).toLocaleString() : '-';
  }

  function pretty(value: unknown): string {
    return JSON.stringify(value ?? {}, null, 2);
  }

  function numberValue(value: unknown): number {
    return typeof value === 'number' ? value : 0;
  }

  function stringValue(value: unknown): string {
    return typeof value === 'string' ? value : '';
  }

  function stringArrayValue(value: unknown): string[] {
    return Array.isArray(value) ? value.filter((item): item is string => typeof item === 'string') : [];
  }

  function recordValue(value: unknown): Record<string, string> {
    if (!value || typeof value !== 'object' || Array.isArray(value)) {
      return {};
    }
    return Object.fromEntries(
      Object.entries(value).filter((entry): entry is [string, string] => typeof entry[1] === 'string')
    );
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

    {#if showUsageStats}
      <div class="mt-4 grid gap-4 md:grid-cols-4">
        <div class="stat-card">
          <p class="eyebrow">Tool Calls</p>
          <p class="mt-3 text-lg font-semibold text-mist">{toolCalls}</p>
        </div>
        <div class="stat-card">
          <p class="eyebrow">LLM Calls</p>
          <p class="mt-3 text-lg font-semibold text-mist">{llmCalls}</p>
        </div>
        <div class="stat-card">
          <p class="eyebrow">Tokens</p>
          <p class="mt-3 text-sm text-slate-200">{promptTokens} in / {completionTokens} out</p>
        </div>
        <div class="stat-card">
          <p class="eyebrow">LLM Cost</p>
          <p class="mt-3 text-lg font-semibold text-mist">${llmCostUsd.toFixed(4)}</p>
        </div>
      </div>
    {/if}

    {#if showSatelliteStats}
      <div class="mt-4 grid gap-4 md:grid-cols-4">
        <div class="stat-card">
          <p class="eyebrow">Records</p>
          <p class="mt-3 text-lg font-semibold text-mist">{totalRecords}</p>
          <p class="mt-2 text-xs text-slate-400">{activeRecords} active</p>
        </div>
        <div class="stat-card">
          <p class="eyebrow">Coverage</p>
          <p class="mt-3 text-sm text-slate-200">{coverageOperatorPurpose.toFixed(1)}% operator/purpose</p>
          <p class="mt-2 text-xs text-slate-400">{coverageMass.toFixed(1)}% mass</p>
        </div>
        <div class="stat-card">
          <p class="eyebrow">Research</p>
          <p class="mt-3 text-sm text-slate-200">{researchedRecords} researched</p>
          <p class="mt-2 text-xs text-slate-400">{acceptedLlmRecords} accepted</p>
        </div>
        <div class="stat-card">
          <p class="eyebrow">Anomalies</p>
          <p class="mt-3 text-lg font-semibold text-mist">{anomalyCount}</p>
          <p class="mt-2 text-xs text-slate-400">Quality findings</p>
        </div>
      </div>
    {/if}

    {#if showSourceStats}
      <div class="mt-4 grid gap-4 md:grid-cols-4">
        <div class="stat-card">
          <p class="eyebrow">Source Mode</p>
          <p class="mt-3 text-sm text-slate-200">{spaceTrackMode || 'prefer_cache'}</p>
          <p class="mt-2 text-xs text-slate-400">{llmResearchStatus || 'LLM status pending'}</p>
        </div>
        <div class="stat-card md:col-span-2">
          <p class="eyebrow">Source Status</p>
          <p class="mt-3 text-sm text-slate-200">
            {#if Object.keys(sourceStatus).length}
              {Object.entries(sourceStatus).map(([key, value]) => `${key}: ${value}`).join(' | ')}
            {:else}
              No source status captured.
            {/if}
          </p>
        </div>
        <div class="stat-card">
          <p class="eyebrow">Cache</p>
          <p class="mt-3 text-sm text-slate-200">
            {cachedSources.length ? cachedSources.join(', ') : 'No cached sources used'}
          </p>
          <p class="mt-2 text-xs text-slate-400">
            {staleSources.length ? `Stale: ${staleSources.join(', ')}` : 'No stale sources'}
          </p>
        </div>
      </div>
    {/if}

    {#if run.error}
      <div class="error-panel">{run.error}</div>
    {/if}

    {#if outputDbPath || latestDbPath}
      <div class="mt-4 grid gap-4 2xl:grid-cols-2">
        {#if outputDbPath}
          <div class="json-panel">
            <div class="flex items-center justify-between gap-3">
              <p class="eyebrow">Run Output DB</p>
              <span class="text-xs uppercase tracking-[0.2em] text-slate-500">Per run</span>
            </div>
            <pre>{outputDbPath}</pre>
          </div>
        {/if}
        {#if latestDbPath}
          <div class="json-panel">
            <div class="flex items-center justify-between gap-3">
              <p class="eyebrow">Latest Output DB</p>
              <span class="text-xs uppercase tracking-[0.2em] text-slate-500">Promoted</span>
            </div>
            <pre>{latestDbPath}</pre>
          </div>
        {/if}
      </div>
    {/if}

    <div class="mt-5 grid gap-4 2xl:grid-cols-2">
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
