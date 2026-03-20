<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  import type { ColumnInfo } from '$lib/api/tauri/data';

  export let columns: ColumnInfo[] = [];
  export let rows: (string | number | boolean | null)[][] = [];
  export let visibleColumns: Set<string> | null = null;
  export let sortColumn: string | null = null;
  export let sortDirection: string | null = null;
  export let total = 0;
  export let page = 1;
  export let pageSize = 100;
  export let totalPages = 1;

  const dispatch = createEventDispatcher<{
    sort: string;
    selectRow: Record<string, unknown>;
    pageChange: number;
  }>();

  let selectedRowIndex: number | null = null;

  $: displayColumns = visibleColumns
    ? columns.filter((c) => visibleColumns!.has(c.name))
    : columns;

  $: columnIndices = displayColumns.map((dc) => columns.findIndex((c) => c.name === dc.name));

  function handleRowClick(rowIndex: number) {
    selectedRowIndex = rowIndex;
    const row = rows[rowIndex];
    const record: Record<string, unknown> = {};
    columns.forEach((col, i) => {
      record[col.name] = row[i];
    });
    dispatch('selectRow', record);
  }

  function formatCell(value: string | number | boolean | null): string {
    if (value === null || value === undefined) return '';
    if (typeof value === 'boolean') return value ? 'true' : 'false';
    return String(value);
  }
</script>

<table class="w-full border-collapse text-sm">
  <thead class="sticky top-0 z-10 bg-[#0c0e14]">
    <tr class="border-b border-white/8">
      {#each displayColumns as col}
        <th
          class="cursor-pointer whitespace-nowrap px-3 py-2.5 text-left text-xs font-medium uppercase tracking-wider text-muted-foreground hover:text-mist"
          on:click={() => dispatch('sort', col.name)}
        >
          <span class="inline-flex items-center gap-1">
            {col.name}
            {#if sortColumn === col.name}
              <span class="text-sea">
                {#if sortDirection === 'asc'}
                  <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m18 15-6-6-6 6"/></svg>
                {:else}
                  <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m6 9 6 6 6-6"/></svg>
                {/if}
              </span>
            {/if}
          </span>
        </th>
      {/each}
    </tr>
  </thead>
  <tbody>
    {#each rows as row, rowIndex}
      <tr
        class="cursor-pointer border-b border-white/[0.04] transition-colors hover:bg-white/[0.04] {selectedRowIndex === rowIndex ? 'bg-sea/10' : ''}"
        on:click={() => handleRowClick(rowIndex)}
      >
        {#each columnIndices as colIdx}
          {@const value = row[colIdx]}
          <td
            class="max-w-[200px] truncate whitespace-nowrap px-3 py-2 {value === null ? 'text-muted-foreground/50' : 'text-slate-200'}"
            title={formatCell(value)}
          >
            {value === null ? '—' : formatCell(value)}
          </td>
        {/each}
      </tr>
    {/each}
  </tbody>
</table>

{#if rows.length === 0}
  <div class="flex h-32 items-center justify-center text-sm text-muted-foreground">
    No rows match the current query.
  </div>
{/if}

<!-- Bottom pagination (duplicated for convenience when scrolled down) -->
{#if rows.length > 20}
  <div class="sticky bottom-0 flex items-center justify-between border-t border-white/8 bg-[#0c0e14] px-4 py-2 text-xs text-muted-foreground">
    <span>{total.toLocaleString()} rows total</span>
    <div class="flex items-center gap-2">
      <span>Page {page} of {totalPages}</span>
      <button
        class="rounded p-1 hover:bg-white/10 disabled:opacity-30"
        disabled={page <= 1}
        on:click={() => dispatch('pageChange', page - 1)}
      >
        <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m15 18-6-6 6-6"/></svg>
      </button>
      <button
        class="rounded p-1 hover:bg-white/10 disabled:opacity-30"
        disabled={page >= totalPages}
        on:click={() => dispatch('pageChange', page + 1)}
      >
        <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m9 18 6-6-6-6"/></svg>
      </button>
    </div>
  </div>
{/if}
