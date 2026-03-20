<script lang="ts">
  import { onMount } from 'svelte';
  import { queryRecipeDb, type QueryResult } from '$lib/api/tauri/data';

  export let dbPath: string;

  type CoverageRow = { fieldName: string; coveragePct: number };

  let rows: CoverageRow[] = [];
  let collapsed = false;
  let error = '';

  onMount(async () => {
    try {
      const result: QueryResult = await queryRecipeDb({
        dbPath,
        table: 'field_coverage',
        page: 1,
        pageSize: 200,
        sortColumn: null,
        sortDirection: null,
        search: null,
        filters: null
      });

      const fieldIdx = result.columns.findIndex((c) => c.name === 'field_name');
      const coverageIdx = result.columns.findIndex(
        (c) => c.name === 'coverage_pct' || c.name === 'coverage' || c.name === 'pct'
      );

      if (fieldIdx === -1 || coverageIdx === -1) {
        // Try to use first two columns as field_name and coverage
        if (result.columns.length >= 2) {
          rows = result.rows
            .map((r) => ({
              fieldName: String(r[0] ?? ''),
              coveragePct: typeof r[1] === 'number' ? r[1] : parseFloat(String(r[1] ?? '0'))
            }))
            .filter((r) => !isNaN(r.coveragePct))
            .sort((a, b) => b.coveragePct - a.coveragePct);
        }
        return;
      }

      rows = result.rows
        .map((r) => ({
          fieldName: String(r[fieldIdx] ?? ''),
          coveragePct: typeof r[coverageIdx] === 'number' ? r[coverageIdx] : parseFloat(String(r[coverageIdx] ?? '0'))
        }))
        .filter((r) => !isNaN(r.coveragePct))
        .sort((a, b) => b.coveragePct - a.coveragePct);
    } catch (e) {
      error = e instanceof Error ? e.message : 'Failed to load coverage data.';
    }
  });

  function barColor(pct: number): string {
    if (pct >= 80) return 'bg-sea';
    if (pct >= 50) return 'bg-flare';
    return 'bg-destructive';
  }
</script>

<div>
  <button
    class="mb-2 flex w-full items-center gap-2 text-xs font-medium uppercase tracking-widest text-muted-foreground hover:text-mist"
    on:click={() => { collapsed = !collapsed; }}
  >
    <svg
      xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"
      class="transition-transform {collapsed ? '-rotate-90' : ''}"
    ><path d="m6 9 6 6 6-6"/></svg>
    Field Coverage
  </button>

  {#if !collapsed}
    {#if error}
      <p class="text-xs text-rose-300">{error}</p>
    {:else if rows.length === 0}
      <p class="text-xs text-muted-foreground">No coverage data available.</p>
    {:else}
      <div class="space-y-1.5">
        {#each rows as row}
          <div class="group">
            <div class="flex items-center justify-between text-xs">
              <span class="max-w-[140px] truncate text-muted-foreground" title={row.fieldName}>{row.fieldName}</span>
              <span class="{row.coveragePct >= 80 ? 'text-sea' : row.coveragePct >= 50 ? 'text-flare' : 'text-destructive'}">{row.coveragePct.toFixed(1)}%</span>
            </div>
            <div class="mt-0.5 h-1.5 rounded-full bg-white/10">
              <div
                class="h-1.5 rounded-full transition-all {barColor(row.coveragePct)}"
                style="width: {Math.min(100, row.coveragePct)}%"
              />
            </div>
          </div>
        {/each}
      </div>
    {/if}
  {/if}
</div>
