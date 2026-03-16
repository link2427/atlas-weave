<script lang="ts">
  import type { AtlasWeaveEvent } from '$lib/stores/events';

  export let events: AtlasWeaveEvent[] = [];

  function formatEvent(event: AtlasWeaveEvent): string {
    if (event.message) {
      return event.message;
    }
    if (event.error) {
      return event.error;
    }
    if (event.summary) {
      return JSON.stringify(event.summary);
    }
    return JSON.stringify(event);
  }

  function formatTime(value?: string): string {
    return value ? new Date(value).toLocaleTimeString() : '--:--:--';
  }

  function levelFor(event: AtlasWeaveEvent): string {
    return (event.level ?? event.type).toUpperCase();
  }
</script>

<div class="log-shell">
  {#if events.length === 0}
    <p class="empty-copy">No events have been recorded for this node yet.</p>
  {:else}
    {#each events as event, index (`${event.type}-${event.timestamp ?? index}`)}
      <div class="log-row">
        <div class="log-meta">
          <span>{formatTime(event.timestamp)}</span>
          <span class={`level ${event.level ?? event.type}`}>{levelFor(event)}</span>
        </div>
        <div class="log-message">{formatEvent(event)}</div>
      </div>
    {/each}
  {/if}
</div>

<style>
  .log-shell {
    max-height: 22rem;
    overflow-y: auto;
    border-radius: 1.5rem;
    border: 1px solid rgba(255, 255, 255, 0.08);
    background: rgba(2, 6, 23, 0.78);
    padding: 1rem;
    font-family: Consolas, "Courier New", monospace;
  }

  .log-row {
    display: grid;
    gap: 0.45rem;
    border-bottom: 1px solid rgba(255, 255, 255, 0.05);
    padding: 0.75rem 0;
  }

  .log-row:first-child {
    padding-top: 0;
  }

  .log-row:last-child {
    border-bottom: none;
    padding-bottom: 0;
  }

  .log-meta {
    display: flex;
    flex-wrap: wrap;
    gap: 0.75rem;
    font-size: 0.78rem;
    color: rgba(148, 163, 184, 0.92);
  }

  .level {
    letter-spacing: 0.14em;
  }

  .level.info,
  .level.node_log,
  .level.run_completed {
    color: #7dd3fc;
  }

  .level.error,
  .level.node_failed,
  .level.run_failed {
    color: #fda4af;
  }

  .level.node_started,
  .level.node_progress {
    color: #99f6e4;
  }

  .level.node_skipped {
    color: #fde68a;
  }

  .level.node_cancelled,
  .level.run_cancelled {
    color: #fdba74;
  }

  .log-message {
    white-space: pre-wrap;
    color: #e2e8f0;
    line-height: 1.5;
  }

  .empty-copy {
    margin: 0;
    color: rgba(148, 163, 184, 0.92);
  }
</style>
