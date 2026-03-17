<script lang="ts">
  import { Badge } from '$lib/components/ui/badge';
  import type { AtlasWeaveEvent } from '$lib/stores/events';

  export let events: AtlasWeaveEvent[] = [];

  type ToolGroup = {
    id: string;
    label: string;
    kind: string;
    status: 'pending' | 'completed' | 'failed';
    call?: AtlasWeaveEvent;
    result?: AtlasWeaveEvent;
    timestamp?: string;
  };

  // Incremental grouping: maintain map and track last processed index
  let groupMap = new Map<string, ToolGroup>();
  let lastProcessedLength = 0;
  let sortedGroups: ToolGroup[] = [];

  $: {
    const toolTypes = new Set(['tool_call', 'tool_result', 'llm_call', 'llm_result']);

    // Reset if events array was replaced (e.g., new node selected)
    if (events.length < lastProcessedLength) {
      groupMap = new Map();
      lastProcessedLength = 0;
    }

    // Only process new events
    for (let i = lastProcessedLength; i < events.length; i++) {
      const event = events[i];
      if (!toolTypes.has(event.type)) continue;

      const key = event.request_id ?? `${event.type}-${event.timestamp ?? i}`;
      const existing = groupMap.get(key) ?? {
        id: key,
        label: event.model ?? event.tool ?? event.provider ?? 'Tool event',
        kind: kindFor(event),
        status: 'pending' as const,
        timestamp: event.timestamp
      };

      if (event.type === 'tool_call' || event.type === 'llm_call') {
        existing.call = event;
      }
      if (event.type === 'tool_result' || event.type === 'llm_result') {
        existing.result = event;
        existing.status = event.error ? 'failed' : 'completed';
      }
      existing.label = event.model ?? event.tool ?? existing.label;
      existing.kind = kindFor(event);
      existing.timestamp = event.timestamp ?? existing.timestamp;
      groupMap.set(key, existing);
    }
    lastProcessedLength = events.length;

    sortedGroups = [...groupMap.values()].sort((a, b) =>
      (a.timestamp ?? '').localeCompare(b.timestamp ?? '')
    );
  }

  function kindFor(event: AtlasWeaveEvent): string {
    if (event.type.startsWith('llm_')) return 'LLM';
    if (event.tool === 'http') return 'HTTP';
    if (event.tool === 'web_search') return 'Search';
    if (event.tool === 'web_scrape') return 'Scrape';
    return 'Tool';
  }

  function pretty(value: unknown): string {
    return JSON.stringify(value ?? {}, null, 2);
  }

  function subtitle(group: ToolGroup): string {
    if (group.result?.error) return group.result.error;
    if (group.result?.duration_ms !== undefined) {
      const suffix = group.result.cache_hit !== undefined
        ? `, cache ${group.result.cache_hit ? 'hit' : 'miss'}`
        : '';
      return `${group.result.duration_ms}ms${suffix}`;
    }
    return 'Waiting for result';
  }

  function llmUsage(group: ToolGroup): string | null {
    if (!group.result || group.kind !== 'LLM') return null;
    const prompt = group.result.prompt_tokens ?? 0;
    const completion = group.result.completion_tokens ?? 0;
    const cost = group.result.estimated_cost_usd ?? 0;
    return `${prompt} in / ${completion} out, $${cost.toFixed(4)}`;
  }

  function providerAttempts(group: ToolGroup): unknown[] {
    const output = group.result?.output as Record<string, unknown> | undefined;
    const attempts = output?.provider_attempts;
    return Array.isArray(attempts) ? attempts : [];
  }

  function failures(group: ToolGroup): unknown[] {
    const output = group.result?.output as Record<string, unknown> | undefined;
    const value = output?.failures;
    return Array.isArray(value) ? value : [];
  }
</script>

{#if sortedGroups.length === 0}
  <div class="rounded-lg border border-dashed border-white/10 bg-black/20 p-4 text-sm text-muted-foreground">
    No structured tool activity has been recorded for this node yet.
  </div>
{:else}
  <div class="space-y-3">
    {#each sortedGroups as group (group.id)}
      <details class="rounded-lg border border-white/8 bg-black/20 p-4">
        <summary class="flex cursor-pointer list-none items-start justify-between gap-3 [&::-webkit-details-marker]:hidden">
          <div>
            <p class="text-xs font-medium uppercase tracking-widest text-sky-300/80">{group.kind}</p>
            <h4 class="mt-1 text-sm font-semibold text-slate-50">{group.label}</h4>
            <p class="mt-1 text-xs text-muted-foreground">{subtitle(group)}</p>
          </div>
          <div class="flex flex-col items-end gap-2">
            <Badge variant={group.status === 'completed' ? 'completed' : group.status === 'failed' ? 'failed' : 'pending'}>
              {group.status}
            </Badge>
            {#if llmUsage(group)}
              <span class="rounded-full bg-blue-500/15 px-2.5 py-0.5 text-xs text-blue-200">{llmUsage(group)}</span>
            {/if}
          </div>
        </summary>

        <div class="mt-3 grid gap-3 sm:grid-cols-2">
          <div class="rounded-lg border border-white/6 bg-slate-900/70 p-3">
            <p class="text-xs font-medium uppercase tracking-widest text-sky-300/80">Request</p>
            <pre class="mt-2 max-h-64 overflow-auto whitespace-pre-wrap break-words text-xs text-slate-200">{pretty(group.call?.input ?? {})}</pre>
          </div>
          <div class="rounded-lg border border-white/6 bg-slate-900/70 p-3">
            <p class="text-xs font-medium uppercase tracking-widest text-sky-300/80">Result</p>
            <pre class="mt-2 max-h-64 overflow-auto whitespace-pre-wrap break-words text-xs text-slate-200">{pretty(group.result?.output ?? {})}</pre>
          </div>
        </div>

        {#if providerAttempts(group).length > 0 || failures(group).length > 0}
          <div class="mt-3 grid gap-3 sm:grid-cols-2">
            {#if providerAttempts(group).length > 0}
              <div class="rounded-lg border border-white/6 bg-slate-900/70 p-3">
                <p class="text-xs font-medium uppercase tracking-widest text-sky-300/80">Provider Attempts</p>
                <pre class="mt-2 max-h-64 overflow-auto whitespace-pre-wrap break-words text-xs text-slate-200">{pretty(providerAttempts(group))}</pre>
              </div>
            {/if}
            {#if failures(group).length > 0}
              <div class="rounded-lg border border-rose-400/20 bg-rose-950/40 p-3">
                <p class="text-xs font-medium uppercase tracking-widest text-sky-300/80">Failures</p>
                <pre class="mt-2 max-h-64 overflow-auto whitespace-pre-wrap break-words text-xs text-slate-200">{pretty(failures(group))}</pre>
              </div>
            {/if}
          </div>
        {/if}
      </details>
    {/each}
  </div>
{/if}
