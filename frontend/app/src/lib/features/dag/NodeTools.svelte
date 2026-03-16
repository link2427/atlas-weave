<script lang="ts">
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

  $: toolEvents = events.filter((event) =>
    ['tool_call', 'tool_result', 'llm_call', 'llm_result'].includes(event.type)
  );
  $: groups = buildGroups(toolEvents);

  function buildGroups(input: AtlasWeaveEvent[]): ToolGroup[] {
    const grouped = new Map<string, ToolGroup>();

    for (const event of input) {
      const key = event.request_id ?? `${event.type}-${event.timestamp ?? Math.random()}`;
      const existing =
        grouped.get(key) ??
        {
          id: key,
          label: event.model ?? event.tool ?? event.provider ?? 'Tool event',
          kind: kindFor(event),
          status: 'pending',
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
      grouped.set(key, existing);
    }

    return [...grouped.values()].sort((left, right) =>
      (left.timestamp ?? '').localeCompare(right.timestamp ?? '')
    );
  }

  function kindFor(event: AtlasWeaveEvent): string {
    if (event.type.startsWith('llm_')) {
      return 'LLM';
    }
    if (event.tool === 'http') {
      return 'HTTP';
    }
    if (event.tool === 'web_search') {
      return 'Search';
    }
    if (event.tool === 'web_scrape') {
      return 'Scrape';
    }
    return 'Tool';
  }

  function pretty(value: unknown): string {
    return JSON.stringify(value ?? {}, null, 2);
  }

  function subtitle(group: ToolGroup): string {
    if (group.result?.error) {
      return group.result.error;
    }
    if (group.result?.duration_ms !== undefined) {
      const suffix =
        group.result.cache_hit !== undefined ? `, cache ${group.result.cache_hit ? 'hit' : 'miss'}` : '';
      return `${group.result.duration_ms}ms${suffix}`;
    }
    return 'Waiting for result';
  }

  function llmUsage(group: ToolGroup): string | null {
    if (!group.result || group.kind !== 'LLM') {
      return null;
    }

    const prompt = group.result.prompt_tokens ?? 0;
    const completion = group.result.completion_tokens ?? 0;
    const cost = group.result.estimated_cost_usd ?? 0;
    return `${prompt} in / ${completion} out, $${cost.toFixed(4)}`;
  }
</script>

{#if groups.length === 0}
  <div class="empty-panel">
    No structured tool activity has been recorded for this node yet.
  </div>
{:else}
  <div class="tool-stack">
    {#each groups as group}
      <details class="tool-card" open>
        <summary>
          <div>
            <p class="eyebrow">{group.kind}</p>
            <h4>{group.label}</h4>
            <p class="subtitle">{subtitle(group)}</p>
          </div>
          <div class="meta">
            <span class={`status ${group.status}`}>{group.status}</span>
            {#if llmUsage(group)}
              <span class="usage">{llmUsage(group)}</span>
            {/if}
          </div>
        </summary>

        <div class="payload-grid">
          <div class="payload-card">
            <p class="eyebrow">Request</p>
            <pre>{pretty(group.call?.input ?? {})}</pre>
          </div>
          <div class="payload-card">
            <p class="eyebrow">Result</p>
            <pre>{pretty(group.result?.output ?? {})}</pre>
          </div>
        </div>
      </details>
    {/each}
  </div>
{/if}

<style>
  .empty-panel {
    border-radius: 1.5rem;
    border: 1px dashed rgba(148, 163, 184, 0.26);
    background: rgba(2, 6, 23, 0.35);
    padding: 1.25rem;
    color: rgba(203, 213, 225, 0.88);
  }

  .tool-stack {
    display: grid;
    gap: 1rem;
  }

  .tool-card {
    border-radius: 1.5rem;
    border: 1px solid rgba(255, 255, 255, 0.08);
    background: rgba(2, 6, 23, 0.38);
    padding: 1rem;
  }

  summary {
    display: flex;
    cursor: pointer;
    align-items: flex-start;
    justify-content: space-between;
    gap: 1rem;
    list-style: none;
  }

  summary::-webkit-details-marker {
    display: none;
  }

  h4 {
    margin-top: 0.35rem;
    font-size: 1rem;
    font-weight: 600;
    color: #f8fafc;
  }

  .eyebrow {
    font-size: 0.72rem;
    letter-spacing: 0.24em;
    text-transform: uppercase;
    color: rgba(125, 211, 252, 0.85);
  }

  .subtitle {
    margin-top: 0.45rem;
    color: rgba(203, 213, 225, 0.82);
  }

  .meta {
    display: grid;
    gap: 0.5rem;
    justify-items: end;
  }

  .status,
  .usage {
    border-radius: 9999px;
    padding: 0.3rem 0.75rem;
    font-size: 0.72rem;
  }

  .status {
    text-transform: uppercase;
    letter-spacing: 0.18em;
  }

  .status.pending {
    background: rgba(148, 163, 184, 0.16);
    color: #cbd5e1;
  }

  .status.completed {
    background: rgba(45, 212, 191, 0.16);
    color: #99f6e4;
  }

  .status.failed {
    background: rgba(251, 113, 133, 0.18);
    color: #fecdd3;
  }

  .usage {
    background: rgba(59, 130, 246, 0.15);
    color: #bfdbfe;
  }

  .payload-grid {
    margin-top: 1rem;
    display: grid;
    gap: 1rem;
    grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  }

  .payload-card {
    border-radius: 1.2rem;
    border: 1px solid rgba(255, 255, 255, 0.06);
    background: rgba(15, 23, 42, 0.72);
    padding: 0.9rem;
  }

  pre {
    margin-top: 0.8rem;
    max-height: 16rem;
    overflow: auto;
    white-space: pre-wrap;
    word-break: break-word;
    color: #e2e8f0;
  }
</style>
