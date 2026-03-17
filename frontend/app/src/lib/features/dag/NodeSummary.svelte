<script lang="ts">
  import { Badge } from '$lib/components/ui/badge';
  import { Card, CardHeader, CardTitle, CardContent } from '$lib/components/ui/card';
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

  function statusVariant(status: string): 'pending' | 'running' | 'completed' | 'failed' | 'skipped' | 'cancelled' {
    const valid = ['pending', 'running', 'completed', 'failed', 'skipped', 'cancelled'] as const;
    return valid.includes(status as typeof valid[number]) ? (status as typeof valid[number]) : 'pending';
  }
</script>

<div class="space-y-4">
  <div class="grid gap-4 md:grid-cols-2">
    <Card>
      <CardHeader>
        <CardTitle>Status</CardTitle>
      </CardHeader>
      <CardContent>
        <div class="flex items-center gap-3">
          <Badge variant={statusVariant(node.status)}>{node.status}</Badge>
          <span class="text-sm text-muted-foreground">{node.message ?? 'No recent status message.'}</span>
        </div>
      </CardContent>
    </Card>

    <Card>
      <CardHeader>
        <CardTitle>Progress</CardTitle>
      </CardHeader>
      <CardContent>
        <div class="overflow-hidden rounded-full bg-white/10">
          <div
            class="h-2 rounded-full bg-gradient-to-r from-teal-400 to-sky-400 transition-all duration-300"
            style="width: {Math.round((node.progress ?? 0) * 100)}%"
          ></div>
        </div>
        <p class="mt-2 text-sm text-muted-foreground">{Math.round((node.progress ?? 0) * 100)}% complete</p>
      </CardContent>
    </Card>
  </div>

  <div class="grid gap-4 md:grid-cols-3">
    <Card>
      <CardHeader><CardTitle>Started</CardTitle></CardHeader>
      <CardContent><p class="text-sm text-slate-200">{formatTime(node.startedAt)}</p></CardContent>
    </Card>
    <Card>
      <CardHeader><CardTitle>Completed</CardTitle></CardHeader>
      <CardContent><p class="text-sm text-slate-200">{formatTime(node.completedAt)}</p></CardContent>
    </Card>
    <Card>
      <CardHeader><CardTitle>Duration</CardTitle></CardHeader>
      <CardContent>
        <p class="text-sm text-slate-200">
          {node.durationMs !== null ? `${node.durationMs} ms` : '-'}
        </p>
      </CardContent>
    </Card>
  </div>

  {#if node.error}
    <div class="rounded-lg border border-rose-400/30 bg-rose-500/10 p-4 text-sm text-rose-100">
      {node.error}
    </div>
  {/if}

  <Card>
    <CardHeader>
      <div class="flex items-center justify-between">
        <CardTitle>Completion Summary</CardTitle>
        <span class="text-xs text-muted-foreground">{metrics.length} fields</span>
      </div>
    </CardHeader>
    <CardContent>
      {#if metrics.length === 0}
        <p class="text-sm text-muted-foreground">No structured summary has been emitted for this node yet.</p>
      {:else}
        <div class="grid gap-3 md:grid-cols-2">
          {#each metrics as [key, value]}
            <div class="rounded-lg border border-white/8 bg-black/20 p-4">
              <p class="text-xs font-medium uppercase tracking-widest text-muted-foreground">{formatKey(key)}</p>
              <p class="mt-2 break-words text-sm text-slate-100">
                {typeof value === 'object' ? JSON.stringify(value) : String(value)}
              </p>
            </div>
          {/each}
        </div>
      {/if}
    </CardContent>
  </Card>
</div>
