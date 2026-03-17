<script lang="ts">
  import { createEventDispatcher } from 'svelte';

  import { Button } from '$lib/components/ui/button';
  import NodeLogs from '$lib/features/dag/NodeLogs.svelte';
  import type { AtlasWeaveEvent } from '$lib/stores/events';

  export let events: AtlasWeaveEvent[] = [];
  export let total = 0;
  export let canLoadOlder = false;
  export let loadingOlder = false;

  const dispatch = createEventDispatcher<{ loadOlder: undefined }>();
</script>

<section class="h-full rounded-xl border border-white/8 bg-white/[0.04] p-4">
  <div class="mb-4 flex items-center justify-between gap-3">
    <div>
      <p class="text-xs font-medium uppercase tracking-widest text-muted-foreground">Run Log</p>
      <h3 class="mt-2 text-lg font-semibold text-mist">Persisted Event Stream</h3>
    </div>
    <span class="text-xs text-muted-foreground">{events.length}/{total} events</span>
  </div>

  {#if canLoadOlder}
    <div class="mb-3">
      <Button variant="outline" size="sm" disabled={loadingOlder} onclick={() => dispatch('loadOlder')}>
        {loadingOlder ? 'Loading...' : 'Load older events'}
      </Button>
    </div>
  {/if}

  <NodeLogs {events} />
</section>
