<script lang="ts">
  import { Tabs, TabsList, TabsTrigger, TabsContent } from '$lib/components/ui/tabs';
  import NodeLogs from '$lib/features/dag/NodeLogs.svelte';
  import NodeSummary from '$lib/features/dag/NodeSummary.svelte';
  import NodeTools from '$lib/features/dag/NodeTools.svelte';
  import type { DagNodeState } from '$lib/stores/dag';
  import type { AtlasWeaveEvent } from '$lib/stores/events';

  export let node: DagNodeState | null = null;
  export let events: AtlasWeaveEvent[] = [];

  let activeTab = 'summary';
  $: if (!node) {
    activeTab = 'summary';
  }
</script>

<section class="h-full rounded-xl border border-white/8 bg-white/[0.04] p-4">
  <div class="border-b border-white/8 pb-4">
    <p class="text-xs font-medium uppercase tracking-widest text-muted-foreground">Node Detail</p>
    <h3 class="mt-2 text-2xl font-semibold text-mist">
      {node?.label ?? 'Select a node'}
    </h3>
    <p class="mt-2 text-sm text-muted-foreground">
      {node?.description ?? 'Click a node in the DAG to inspect its state, logs, and outputs.'}
    </p>
  </div>

  {#if node}
    <Tabs bind:value={activeTab} class="mt-4">
      <TabsList>
        <TabsTrigger value="summary">Summary</TabsTrigger>
        <TabsTrigger value="logs">Logs</TabsTrigger>
        <TabsTrigger value="tools">Tools</TabsTrigger>
        <TabsTrigger value="data">Data</TabsTrigger>
      </TabsList>

      <TabsContent value="summary">
        <NodeSummary {node} />
      </TabsContent>
      <TabsContent value="logs">
        <NodeLogs {events} />
      </TabsContent>
      <TabsContent value="tools">
        <NodeTools {events} />
      </TabsContent>
      <TabsContent value="data">
        <div class="rounded-lg border border-dashed border-white/10 bg-black/20 p-4 text-sm text-muted-foreground">
          Data inspection arrives in a later phase once recipe output databases are exposed read-only.
        </div>
      </TabsContent>
    </Tabs>
  {:else}
    <div class="mt-4 rounded-lg border border-dashed border-white/10 bg-black/20 p-4 text-sm text-muted-foreground">
      No node is selected yet.
    </div>
  {/if}
</section>
