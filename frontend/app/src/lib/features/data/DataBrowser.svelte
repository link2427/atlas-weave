<script lang="ts">
  import { onMount } from 'svelte';

  import { Badge } from '$lib/components/ui/badge';
  import { Button } from '$lib/components/ui/button';
  import { Separator } from '$lib/components/ui/separator';
  import {
    getRecipeDbTables,
    queryRecipeDb,
    exportCsv,
    pickSaveCsvFile,
    type TableInfo,
    type QueryResult,
    type ColumnFilter,
    type ColumnInfo
  } from '$lib/api/tauri/data';
  import DataTable from './DataTable.svelte';
  import RecordDetail from './RecordDetail.svelte';
  import CoverageDashboard from './CoverageDashboard.svelte';

  export let dbPath: string;
  export let recipeName: string;

  const SATELLITES_DEFAULT_COLS = new Set([
    'norad_id', 'object_name', 'object_type', 'active_status',
    'operator_name', 'purpose_primary', 'orbit_class',
    'constellation_name', 'data_completeness_pct'
  ]);

  let tables: TableInfo[] = [];
  let selectedTable = '';
  let result: QueryResult | null = null;
  let loading = false;
  let error = '';

  // Query state
  let currentPage = 1;
  let pageSize = 100;
  let sortColumn: string | null = null;
  let sortDirection: string | null = null;
  let searchTerm = '';
  let searchDebounced = '';
  let filters: ColumnFilter[] = [];
  let visibleColumns: Set<string> | null = null;

  // UI state
  let sidebarOpen = true;
  let selectedRow: Record<string, unknown> | null = null;
  let showColumnPicker = false;
  let showFilterDialog = false;
  let exporting = false;
  let exportMessage = '';

  // Filter dialog state
  let newFilterColumn = '';
  let newFilterOperator = 'contains';
  let newFilterValue = '';

  let searchTimeout: ReturnType<typeof setTimeout>;

  $: totalPages = result ? Math.max(1, Math.ceil(result.total / pageSize)) : 1;

  onMount(async () => {
    try {
      tables = await getRecipeDbTables(dbPath);
      const satTable = tables.find((t) => t.name === 'satellites');
      selectedTable = satTable ? satTable.name : tables[0]?.name ?? '';
      if (selectedTable) {
        await fetchData();
      }
    } catch (e) {
      error = e instanceof Error ? e.message : 'Failed to load tables.';
    }
  });

  function handleSearchInput(event: Event) {
    const value = (event.target as HTMLInputElement).value;
    searchTerm = value;
    clearTimeout(searchTimeout);
    searchTimeout = setTimeout(() => {
      searchDebounced = value;
      currentPage = 1;
      void fetchData();
    }, 300);
  }

  async function fetchData() {
    if (!selectedTable) return;
    loading = true;
    error = '';
    try {
      result = await queryRecipeDb({
        dbPath,
        table: selectedTable,
        page: currentPage,
        pageSize,
        sortColumn,
        sortDirection,
        search: searchDebounced || null,
        filters: filters.length > 0 ? filters : null
      });

      // Set default visible columns
      if (!visibleColumns) {
        if (selectedTable === 'satellites' && result.columns.some((c) => SATELLITES_DEFAULT_COLS.has(c.name))) {
          visibleColumns = new Set(SATELLITES_DEFAULT_COLS);
        } else {
          visibleColumns = new Set(result.columns.map((c) => c.name));
        }
      }
    } catch (e) {
      error = e instanceof Error ? e.message : 'Query failed.';
    } finally {
      loading = false;
    }
  }

  function selectTable(name: string) {
    selectedTable = name;
    currentPage = 1;
    sortColumn = null;
    sortDirection = null;
    searchTerm = '';
    searchDebounced = '';
    filters = [];
    visibleColumns = null;
    selectedRow = null;
    void fetchData();
  }

  function handleSort(column: string) {
    if (sortColumn === column) {
      sortDirection = sortDirection === 'asc' ? 'desc' : 'asc';
    } else {
      sortColumn = column;
      sortDirection = 'asc';
    }
    currentPage = 1;
    void fetchData();
  }

  function handlePageChange(page: number) {
    currentPage = page;
    void fetchData();
  }

  function handleRowSelect(row: Record<string, unknown>) {
    selectedRow = row;
  }

  function addFilter() {
    if (!newFilterColumn) return;
    filters = [...filters, {
      column: newFilterColumn,
      operator: newFilterOperator,
      value: ['is_null', 'is_not_null'].includes(newFilterOperator) ? null : newFilterValue
    }];
    newFilterColumn = '';
    newFilterOperator = 'contains';
    newFilterValue = '';
    showFilterDialog = false;
    currentPage = 1;
    void fetchData();
  }

  function removeFilter(index: number) {
    filters = filters.filter((_, i) => i !== index);
    currentPage = 1;
    void fetchData();
  }

  function toggleColumn(colName: string) {
    if (!visibleColumns) return;
    const next = new Set(visibleColumns);
    if (next.has(colName)) {
      if (next.size > 1) next.delete(colName);
    } else {
      next.add(colName);
    }
    visibleColumns = next;
  }

  function showAllColumns() {
    if (!result) return;
    visibleColumns = new Set(result.columns.map((c) => c.name));
  }

  async function handleExport() {
    exporting = true;
    exportMessage = '';
    try {
      const outputPath = await pickSaveCsvFile();
      if (!outputPath) {
        exporting = false;
        return;
      }
      const res = await exportCsv({
        dbPath,
        table: selectedTable,
        outputPath,
        search: searchDebounced || null,
        filters: filters.length > 0 ? filters : null
      });
      exportMessage = `Exported ${res.rowsExported.toLocaleString()} rows`;
      setTimeout(() => { exportMessage = ''; }, 4000);
    } catch (e) {
      exportMessage = e instanceof Error ? e.message : 'Export failed.';
    } finally {
      exporting = false;
    }
  }

  function operatorLabel(op: string): string {
    const labels: Record<string, string> = {
      eq: '=', neq: '!=', contains: 'contains', gt: '>', lt: '<',
      gte: '>=', lte: '<=', is_null: 'is null', is_not_null: 'is not null'
    };
    return labels[op] ?? op;
  }
</script>

<div class="flex h-full min-h-0 flex-1">
  <!-- Sidebar -->
  {#if sidebarOpen}
    <aside class="flex w-[280px] flex-shrink-0 flex-col border-r border-white/8 bg-white/[0.02]">
      <div class="flex items-center justify-between border-b border-white/8 px-4 py-3">
        <div>
          <p class="text-xs font-medium uppercase tracking-widest text-sea">Data Inspector</p>
          <p class="mt-1 text-sm text-mist">{recipeName}</p>
        </div>
        <button
          class="rounded p-1 text-muted-foreground hover:bg-white/10 hover:text-mist"
          on:click={() => { sidebarOpen = false; }}
          title="Collapse sidebar"
        >
          <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m15 18-6-6 6-6"/></svg>
        </button>
      </div>

      <div class="flex-1 overflow-y-auto px-4 py-3">
        <!-- Tables -->
        <p class="mb-2 text-xs font-medium uppercase tracking-widest text-muted-foreground">Tables</p>
        <div class="space-y-1">
          {#each tables as table}
            <button
              class="flex w-full items-center justify-between rounded-md px-3 py-2 text-left text-sm transition {selectedTable === table.name ? 'bg-sea/15 text-sea' : 'text-muted-foreground hover:bg-white/[0.06] hover:text-mist'}"
              on:click={() => selectTable(table.name)}
            >
              <span class="truncate">{table.name}</span>
              <Badge variant="outline" class="ml-2 text-xs">{table.rowCount.toLocaleString()}</Badge>
            </button>
          {/each}
        </div>

        <!-- Active Filters -->
        {#if filters.length > 0}
          <Separator class="my-3" />
          <p class="mb-2 text-xs font-medium uppercase tracking-widest text-muted-foreground">Active Filters</p>
          <div class="space-y-1">
            {#each filters as filter, i}
              <div class="flex items-center gap-1">
                <Badge variant="outline" class="max-w-full truncate text-xs">
                  {filter.column} {operatorLabel(filter.operator)}{filter.value != null ? ` "${filter.value}"` : ''}
                </Badge>
                <button
                  class="flex-shrink-0 rounded p-0.5 text-muted-foreground hover:text-rose-300"
                  on:click={() => removeFilter(i)}
                  title="Remove filter"
                >
                  <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 6 6 18"/><path d="m6 6 12 12"/></svg>
                </button>
              </div>
            {/each}
          </div>
        {/if}

        <!-- Coverage -->
        {#if tables.some((t) => t.name === 'field_coverage')}
          <Separator class="my-3" />
          <CoverageDashboard {dbPath} />
        {/if}
      </div>

      <div class="border-t border-white/8 px-4 py-3">
        <a href="/" class="text-xs text-sky-300 underline hover:text-sky-200">Back to launcher</a>
      </div>
    </aside>
  {/if}

  <!-- Main Content -->
  <div class="flex min-w-0 flex-1 flex-col">
    <!-- Toolbar -->
    <div class="flex flex-wrap items-center gap-2 border-b border-white/8 px-4 py-2">
      {#if !sidebarOpen}
        <button
          class="rounded p-1 text-muted-foreground hover:bg-white/10 hover:text-mist"
          on:click={() => { sidebarOpen = true; }}
          title="Expand sidebar"
        >
          <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m9 18 6-6-6-6"/></svg>
        </button>
      {/if}

      <input
        type="text"
        placeholder="Search across all columns..."
        value={searchTerm}
        on:input={handleSearchInput}
        class="h-8 w-[300px] rounded-md border border-white/10 bg-white/[0.04] px-3 text-sm text-mist placeholder:text-muted-foreground focus:border-sea/60 focus:outline-none"
      />

      <!-- Add Filter -->
      <div class="relative">
        <Button variant="outline" size="sm" onclick={() => { showFilterDialog = !showFilterDialog; }}>
          Add Filter
        </Button>
        {#if showFilterDialog && result}
          <div class="absolute left-0 top-full z-20 mt-1 w-72 rounded-lg border border-white/10 bg-[#0f1219] p-3 shadow-xl">
            <select
              bind:value={newFilterColumn}
              class="mb-2 w-full rounded border border-white/10 bg-white/[0.04] px-2 py-1.5 text-sm text-mist"
            >
              <option value="">Select column...</option>
              {#each result.columns as col}
                <option value={col.name}>{col.name}</option>
              {/each}
            </select>
            <select
              bind:value={newFilterOperator}
              class="mb-2 w-full rounded border border-white/10 bg-white/[0.04] px-2 py-1.5 text-sm text-mist"
            >
              <option value="contains">contains</option>
              <option value="eq">equals</option>
              <option value="neq">not equals</option>
              <option value="gt">greater than</option>
              <option value="lt">less than</option>
              <option value="gte">greater or equal</option>
              <option value="lte">less or equal</option>
              <option value="is_null">is null</option>
              <option value="is_not_null">is not null</option>
            </select>
            {#if !['is_null', 'is_not_null'].includes(newFilterOperator)}
              <input
                type="text"
                bind:value={newFilterValue}
                placeholder="Value..."
                class="mb-2 w-full rounded border border-white/10 bg-white/[0.04] px-2 py-1.5 text-sm text-mist placeholder:text-muted-foreground"
              />
            {/if}
            <div class="flex justify-end gap-2">
              <Button variant="outline" size="sm" onclick={() => { showFilterDialog = false; }}>Cancel</Button>
              <Button size="sm" disabled={!newFilterColumn} onclick={addFilter}>Apply</Button>
            </div>
          </div>
        {/if}
      </div>

      <!-- Column Picker -->
      <div class="relative">
        <Button variant="outline" size="sm" onclick={() => { showColumnPicker = !showColumnPicker; }}>
          Columns
        </Button>
        {#if showColumnPicker && result}
          <div class="absolute right-0 top-full z-20 mt-1 max-h-80 w-56 overflow-y-auto rounded-lg border border-white/10 bg-[#0f1219] p-2 shadow-xl">
            <button
              class="mb-1 w-full rounded px-2 py-1 text-left text-xs text-sky-300 hover:bg-white/[0.06]"
              on:click={showAllColumns}
            >Show all</button>
            {#each result.columns as col}
              <label class="flex cursor-pointer items-center gap-2 rounded px-2 py-1 text-sm text-mist hover:bg-white/[0.06]">
                <input
                  type="checkbox"
                  checked={visibleColumns?.has(col.name) ?? true}
                  on:change={() => toggleColumn(col.name)}
                  class="accent-sea"
                />
                <span class="truncate">{col.name}</span>
              </label>
            {/each}
          </div>
        {/if}
      </div>

      <Button variant="outline" size="sm" disabled={exporting} onclick={handleExport}>
        {exporting ? 'Exporting...' : 'Export CSV'}
      </Button>

      {#if exportMessage}
        <span class="text-xs text-sea">{exportMessage}</span>
      {/if}

      <div class="ml-auto flex items-center gap-2 text-xs text-muted-foreground">
        {#if result}
          <span>{result.total.toLocaleString()} rows</span>
          <span>|</span>
          <span>Page {currentPage} of {totalPages}</span>
          <button
            class="rounded p-1 hover:bg-white/10 disabled:opacity-30"
            disabled={currentPage <= 1}
            on:click={() => handlePageChange(currentPage - 1)}
          >
            <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m15 18-6-6 6-6"/></svg>
          </button>
          <button
            class="rounded p-1 hover:bg-white/10 disabled:opacity-30"
            disabled={currentPage >= totalPages}
            on:click={() => handlePageChange(currentPage + 1)}
          >
            <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m9 18 6-6-6-6"/></svg>
          </button>
        {/if}
      </div>
    </div>

    <!-- Data Table -->
    <div class="min-h-0 flex-1 overflow-auto">
      {#if error}
        <div class="m-4 rounded-lg border border-rose-400/30 bg-rose-500/10 p-4 text-sm text-rose-200">
          {error}
        </div>
      {:else if loading}
        <div class="flex h-full items-center justify-center">
          <p class="text-sm text-muted-foreground">Loading...</p>
        </div>
      {:else if result}
        <DataTable
          columns={result.columns}
          rows={result.rows}
          {visibleColumns}
          {sortColumn}
          {sortDirection}
          total={result.total}
          page={currentPage}
          {pageSize}
          {totalPages}
          on:sort={(e) => handleSort(e.detail)}
          on:selectRow={(e) => handleRowSelect(e.detail)}
          on:pageChange={(e) => handlePageChange(e.detail)}
        />
      {/if}
    </div>
  </div>

  <!-- Record Detail -->
  {#if selectedRow}
    <RecordDetail
      row={selectedRow}
      table={selectedTable}
      on:close={() => { selectedRow = null; }}
    />
  {/if}
</div>

<!-- Close dropdowns on outside click -->
<svelte:window on:click={(e) => {
  const target = e.target;
  if (target instanceof HTMLElement) {
    if (showColumnPicker && !target.closest('.relative')) showColumnPicker = false;
    if (showFilterDialog && !target.closest('.relative')) showFilterDialog = false;
  }
}} />
