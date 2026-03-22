<script lang="ts">
  import { createEventDispatcher } from 'svelte';

  import { Badge } from '$lib/components/ui/badge';
  import { Button } from '$lib/components/ui/button';
  import { Card, CardHeader, CardTitle, CardContent } from '$lib/components/ui/card';
  import { Separator } from '$lib/components/ui/separator';
  import type { RunDetail, RunStatus } from '$lib/api/tauri/runs';

  export let run: RunDetail | null = null;
  export let status: RunStatus | 'idle' = 'idle';
  export let cancelling = false;

  const dispatch = createEventDispatcher<{ cancel: undefined; retry: undefined }>();

  type SummaryData = {
    toolCalls: number;
    llmCalls: number;
    promptTokens: number;
    completionTokens: number;
    llmCostUsd: number;
    totalRecords: number;
    activeRecords: number;
    researchedRecords: number;
    acceptedLlmRecords: number;
    anomalyCount: number;
    coverageOperatorPurpose: number;
    coverageMass: number;
    outputDbPath: string;
    latestDbPath: string;
    sourceStatus: Record<string, string>;
    cachedSources: string[];
    staleSources: string[];
    spaceTrackMode: string;
    llmResearchStatus: string;
    showUsageStats: boolean;
    showSatelliteStats: boolean;
    showSourceStats: boolean;
  };

  $: data = deriveSummary(run);

  function deriveSummary(run: RunDetail | null): SummaryData {
    const s = (run?.summary ?? {}) as Record<string, unknown>;
    const num = (v: unknown) => (typeof v === 'number' ? v : 0);
    const str = (v: unknown) => (typeof v === 'string' ? v : '');
    const strArr = (v: unknown) => (Array.isArray(v) ? v.filter((x): x is string => typeof x === 'string') : []);
    const rec = (v: unknown): Record<string, string> => {
      if (!v || typeof v !== 'object' || Array.isArray(v)) return {};
      return Object.fromEntries(Object.entries(v).filter((e): e is [string, string] => typeof e[1] === 'string'));
    };

    const toolCalls = num(s.tool_calls);
    const llmCalls = num(s.llm_calls);
    const promptTokens = num(s.llm_prompt_tokens);
    const completionTokens = num(s.llm_completion_tokens);
    const llmCostUsd = num(s.llm_cost_usd);
    const totalRecords = num(s.total_records);
    const activeRecords = num(s.active_records);
    const researchedRecords = num(s.researched_records);
    const acceptedLlmRecords = num(s.accepted_llm_records);
    const anomalyCount = num(s.anomaly_count);
    const coverageOperatorPurpose = num(s.coverage_operator_purpose_pct);
    const coverageMass = num(s.coverage_mass_pct);
    const outputDbPath = str(s.output_db_path);
    const latestDbPath = str(s.latest_db_path);
    const sourceStatus = rec(s.source_status);
    const cachedSources = strArr(s.cached_sources);
    const staleSources = strArr(s.stale_sources);
    const spaceTrackMode = str(s.space_track_mode);
    const llmResearchStatus = str(s.llm_research_status);

    return {
      toolCalls, llmCalls, promptTokens, completionTokens, llmCostUsd,
      totalRecords, activeRecords, researchedRecords, acceptedLlmRecords,
      anomalyCount, coverageOperatorPurpose, coverageMass,
      outputDbPath, latestDbPath, sourceStatus, cachedSources, staleSources,
      spaceTrackMode, llmResearchStatus,
      showUsageStats: toolCalls > 0 || llmCalls > 0 || promptTokens > 0 || completionTokens > 0 || llmCostUsd > 0,
      showSatelliteStats: totalRecords > 0 || activeRecords > 0 || researchedRecords > 0 || acceptedLlmRecords > 0 || anomalyCount > 0 || coverageOperatorPurpose > 0 || coverageMass > 0 || Boolean(outputDbPath) || Boolean(latestDbPath),
      showSourceStats: Object.keys(sourceStatus).length > 0 || cachedSources.length > 0 || staleSources.length > 0 || Boolean(spaceTrackMode) || Boolean(llmResearchStatus)
    };
  }

  function statusVariant(s: string): 'running' | 'completed' | 'failed' | 'cancelled' | 'pending' {
    if (s === 'completed') return 'completed';
    if (s === 'failed') return 'failed';
    if (s === 'cancelled') return 'cancelled';
    if (s === 'running') return 'running';
    return 'pending';
  }

  function formatTime(value?: string | null): string {
    return value ? new Date(value).toLocaleString() : '-';
  }

  function pretty(value: unknown): string {
    return JSON.stringify(value ?? {}, null, 2);
  }
</script>

<section class="rounded-xl border border-white/8 bg-white/[0.04] p-4">
  <div class="flex items-start justify-between gap-4">
    <div>
      <p class="text-xs font-medium uppercase tracking-widest text-muted-foreground">Run Summary</p>
      <h3 class="mt-2 text-2xl font-semibold text-mist">{run?.recipeName ?? 'Run detail'}</h3>
      <div class="mt-2 flex items-center gap-2">
        <Badge variant={statusVariant(status)}>{status}</Badge>
      </div>
    </div>

    <div class="flex gap-2">
      {#if status === 'running'}
        <Button variant="destructive" disabled={cancelling} onclick={() => dispatch('cancel')}>
          {cancelling ? 'Cancelling...' : 'Cancel Run'}
        </Button>
      {/if}
      {#if status === 'failed'}
        <Button variant="outline" onclick={() => dispatch('retry')}>
          Retry Failed Nodes
        </Button>
      {/if}
    </div>
  </div>

  {#if run}
    <Separator class="my-4" />

    <div class="grid gap-3 md:grid-cols-3">
      <Card>
        <CardHeader><CardTitle>Started</CardTitle></CardHeader>
        <CardContent><p class="text-sm text-slate-200">{formatTime(run.startedAt)}</p></CardContent>
      </Card>
      <Card>
        <CardHeader><CardTitle>Completed</CardTitle></CardHeader>
        <CardContent><p class="text-sm text-slate-200">{formatTime(run.completedAt)}</p></CardContent>
      </Card>
      <Card>
        <CardHeader><CardTitle>Nodes</CardTitle></CardHeader>
        <CardContent><p class="text-sm text-slate-200">{run.nodes.length}</p></CardContent>
      </Card>
    </div>

    {#if data.showUsageStats}
      <div class="mt-3 grid gap-3 md:grid-cols-4">
        <Card>
          <CardHeader><CardTitle>Tool Calls</CardTitle></CardHeader>
          <CardContent><p class="text-lg font-semibold text-mist">{data.toolCalls}</p></CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle>LLM Calls</CardTitle></CardHeader>
          <CardContent><p class="text-lg font-semibold text-mist">{data.llmCalls}</p></CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle>Tokens</CardTitle></CardHeader>
          <CardContent><p class="text-sm text-slate-200">{data.promptTokens} in / {data.completionTokens} out</p></CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle>LLM Cost</CardTitle></CardHeader>
          <CardContent><p class="text-lg font-semibold text-mist">${data.llmCostUsd.toFixed(4)}</p></CardContent>
        </Card>
      </div>
    {/if}

    {#if data.showSatelliteStats}
      <div class="mt-3 grid gap-3 md:grid-cols-4">
        <Card>
          <CardHeader><CardTitle>Records</CardTitle></CardHeader>
          <CardContent>
            <p class="text-lg font-semibold text-mist">{data.totalRecords}</p>
            <p class="mt-1 text-xs text-muted-foreground">{data.activeRecords} active</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle>Coverage</CardTitle></CardHeader>
          <CardContent>
            <p class="text-sm text-slate-200">{data.coverageOperatorPurpose.toFixed(1)}% operator/purpose</p>
            <p class="mt-1 text-xs text-muted-foreground">{data.coverageMass.toFixed(1)}% mass</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle>Research</CardTitle></CardHeader>
          <CardContent>
            <p class="text-sm text-slate-200">{data.researchedRecords} researched</p>
            <p class="mt-1 text-xs text-muted-foreground">{data.acceptedLlmRecords} accepted</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle>Anomalies</CardTitle></CardHeader>
          <CardContent>
            <p class="text-lg font-semibold text-mist">{data.anomalyCount}</p>
            <p class="mt-1 text-xs text-muted-foreground">Quality findings</p>
          </CardContent>
        </Card>
      </div>
    {/if}

    {#if data.showSourceStats}
      <div class="mt-3 grid gap-3 md:grid-cols-4">
        <Card>
          <CardHeader><CardTitle>Source Mode</CardTitle></CardHeader>
          <CardContent>
            <p class="text-sm text-slate-200">{data.spaceTrackMode || 'prefer_cache'}</p>
            <p class="mt-1 text-xs text-muted-foreground">{data.llmResearchStatus || 'LLM status pending'}</p>
          </CardContent>
        </Card>
        <Card class="md:col-span-2">
          <CardHeader><CardTitle>Source Status</CardTitle></CardHeader>
          <CardContent>
            <p class="text-sm text-slate-200">
              {#if Object.keys(data.sourceStatus).length}
                {Object.entries(data.sourceStatus).map(([k, v]) => `${k}: ${v}`).join(' | ')}
              {:else}
                No source status captured.
              {/if}
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle>Cache</CardTitle></CardHeader>
          <CardContent>
            <p class="text-sm text-slate-200">{data.cachedSources.length ? data.cachedSources.join(', ') : 'No cached sources used'}</p>
            <p class="mt-1 text-xs text-muted-foreground">{data.staleSources.length ? `Stale: ${data.staleSources.join(', ')}` : 'No stale sources'}</p>
          </CardContent>
        </Card>
      </div>
    {/if}

    {#if run.error}
      <div class="mt-3 rounded-lg border border-rose-400/30 bg-rose-500/10 p-4 text-sm text-rose-200">
        {run.error}
      </div>
    {/if}

    {#if data.outputDbPath || data.latestDbPath}
      <div class="mt-3 grid gap-3 2xl:grid-cols-2">
        {#if data.outputDbPath}
          <Card>
            <CardHeader>
              <div class="flex items-center justify-between">
                <CardTitle>Run Output DB</CardTitle>
                <div class="flex items-center gap-2">
                  <a href="/data/{run.recipeName}?db={encodeURIComponent(data.outputDbPath)}">
                    <Button variant="outline" size="sm">View Data</Button>
                  </a>
                  <span class="text-xs text-muted-foreground">Per run</span>
                </div>
              </div>
            </CardHeader>
            <CardContent><pre class="max-h-56 overflow-auto whitespace-pre-wrap break-words text-xs text-slate-200">{data.outputDbPath}</pre></CardContent>
          </Card>
        {/if}
        {#if data.latestDbPath}
          <Card>
            <CardHeader>
              <div class="flex items-center justify-between">
                <CardTitle>Latest Output DB</CardTitle>
                <div class="flex items-center gap-2">
                  <a href="/data/{run.recipeName}?db={encodeURIComponent(data.latestDbPath)}">
                    <Button variant="outline" size="sm">View Data</Button>
                  </a>
                  <span class="text-xs text-muted-foreground">Promoted</span>
                </div>
              </div>
            </CardHeader>
            <CardContent><pre class="max-h-56 overflow-auto whitespace-pre-wrap break-words text-xs text-slate-200">{data.latestDbPath}</pre></CardContent>
          </Card>
        {/if}
      </div>
    {/if}

    <Separator class="my-4" />

    <div class="grid gap-3 2xl:grid-cols-2">
      <Card>
        <CardHeader>
          <div class="flex items-center justify-between">
            <CardTitle>Persisted Config</CardTitle>
            <span class="text-xs text-muted-foreground">Redacted</span>
          </div>
        </CardHeader>
        <CardContent><pre class="max-h-56 overflow-auto whitespace-pre-wrap break-words text-xs text-slate-200">{pretty(run.config)}</pre></CardContent>
      </Card>
      <Card>
        <CardHeader>
          <div class="flex items-center justify-between">
            <CardTitle>Run Summary</CardTitle>
            <span class="text-xs text-muted-foreground">Final output</span>
          </div>
        </CardHeader>
        <CardContent><pre class="max-h-56 overflow-auto whitespace-pre-wrap break-words text-xs text-slate-200">{pretty(run.summary)}</pre></CardContent>
      </Card>
    </div>
  {/if}
</section>
