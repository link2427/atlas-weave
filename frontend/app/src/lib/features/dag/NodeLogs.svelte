<script lang="ts">
  import type { AtlasWeaveEvent } from '$lib/stores/events';

  export let events: AtlasWeaveEvent[] = [];

  const ROW_HEIGHT = 52;
  const BUFFER = 10;

  let scrollTop = 0;
  let containerHeight = 400;
  let container: HTMLDivElement | undefined = undefined;

  $: totalHeight = events.length * ROW_HEIGHT;
  $: startIndex = Math.max(0, Math.floor(scrollTop / ROW_HEIGHT) - BUFFER);
  $: endIndex = Math.min(events.length, Math.ceil((scrollTop + containerHeight) / ROW_HEIGHT) + BUFFER);
  $: visibleEvents = events.slice(startIndex, endIndex);
  $: offsetY = startIndex * ROW_HEIGHT;

  function handleScroll() {
    if (container) {
      scrollTop = container.scrollTop;
      containerHeight = container.clientHeight;
    }
  }

  function formatEvent(event: AtlasWeaveEvent): string {
    if (event.message) return event.message;
    if (event.error) return event.error;
    if (event.summary) return JSON.stringify(event.summary);
    return JSON.stringify(event);
  }

  function formatTime(value?: string): string {
    return value ? new Date(value).toLocaleTimeString() : '--:--:--';
  }

  function levelFor(event: AtlasWeaveEvent): string {
    return (event.level ?? event.type).toUpperCase();
  }

  function levelColor(event: AtlasWeaveEvent): string {
    const level = event.level ?? event.type;
    if (['info', 'node_log', 'run_completed'].includes(level)) return 'text-sky-300';
    if (['error', 'node_failed', 'run_failed'].includes(level)) return 'text-rose-300';
    if (['node_started', 'node_progress'].includes(level)) return 'text-teal-300';
    if (level === 'node_skipped') return 'text-amber-300';
    if (['node_cancelled', 'run_cancelled'].includes(level)) return 'text-orange-300';
    return 'text-muted-foreground';
  }
</script>

<div
  bind:this={container}
  on:scroll={handleScroll}
  class="max-h-[22rem] overflow-y-auto rounded-lg border border-white/8 bg-[rgba(2,6,23,0.78)] p-3 font-mono text-sm [&::-webkit-scrollbar]:w-2 [&::-webkit-scrollbar-track]:bg-transparent [&::-webkit-scrollbar-thumb]:rounded-full [&::-webkit-scrollbar-thumb]:bg-white/10"
>
  {#if events.length === 0}
    <p class="text-muted-foreground">No events have been recorded for this node yet.</p>
  {:else}
    <div style="height: {totalHeight}px; position: relative;">
      <div style="transform: translateY({offsetY}px);">
        {#each visibleEvents as event, i (startIndex + i)}
          <div class="border-b border-white/5 py-2" style="height: {ROW_HEIGHT}px;">
            <div class="flex flex-wrap gap-3 text-xs text-muted-foreground">
              <span>{formatTime(event.timestamp)}</span>
              <span class={levelColor(event)}>{levelFor(event)}</span>
            </div>
            <div class="mt-1 truncate leading-relaxed text-slate-200">{formatEvent(event)}</div>
          </div>
        {/each}
      </div>
    </div>
  {/if}
</div>
