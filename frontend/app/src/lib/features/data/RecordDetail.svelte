<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  import { fly } from 'svelte/transition';

  export let row: Record<string, unknown>;
  export let table: string;

  const dispatch = createEventDispatcher<{ close: undefined }>();

  type FieldGroup = { label: string; fields: string[] };

  const SATELLITE_GROUPS: FieldGroup[] = [
    { label: 'Identity', fields: ['norad_id', 'cospar_id', 'object_name', 'object_type', 'alternate_name'] },
    { label: 'Ownership', fields: ['owner_country', 'owner_country_code', 'operator_name', 'operator_country', 'operator_country_code'] },
    { label: 'Mission', fields: ['purpose_primary', 'purpose_secondary', 'purpose_detailed', 'active_status', 'constellation_name', 'constellation_size'] },
    { label: 'Hardware', fields: ['mass_kg', 'dry_mass_kg', 'power_watts', 'design_life_years', 'bus_type', 'propulsion_type', 'payload_description'] },
    { label: 'Orbital', fields: ['orbit_class', 'orbit_type', 'perigee_km', 'apogee_km', 'inclination_deg', 'period_minutes', 'eccentricity', 'semi_major_axis_km', 'mean_motion', 'raan_deg', 'arg_perigee_deg', 'mean_anomaly_deg', 'tle_epoch', 'tle_line1', 'tle_line2'] },
    { label: 'Launch', fields: ['launch_date', 'launch_site', 'launch_vehicle', 'launch_mass_kg', 'decay_date', 'reentry_date'] },
    { label: 'Derived', fields: ['data_completeness_pct', 'enrichment_confidence', 'anomaly_flags', 'anomaly_count'] },
    { label: 'Source Tracking', fields: ['source_celestrak', 'source_ucs', 'source_spacetrack', 'source_research', 'source_tle', 'research_sources_json', 'merge_lineage_json', 'last_updated', 'created_at'] },
  ];

  let collapsedGroups = new Set<string>();

  function toggleGroup(label: string) {
    const next = new Set(collapsedGroups);
    if (next.has(label)) {
      next.delete(label);
    } else {
      next.add(label);
    }
    collapsedGroups = next;
  }

  $: groups = table === 'satellites' ? buildSatelliteGroups() : [{ label: 'All Fields', fields: Object.keys(row) }];

  function buildSatelliteGroups(): FieldGroup[] {
    const allKeys = new Set(Object.keys(row));
    const assignedKeys = new Set(SATELLITE_GROUPS.flatMap((g) => g.fields));
    const ungrouped = [...allKeys].filter((k) => !assignedKeys.has(k));

    const result = SATELLITE_GROUPS.map((g) => ({
      label: g.label,
      fields: g.fields.filter((f) => allKeys.has(f))
    })).filter((g) => g.fields.length > 0);

    if (ungrouped.length > 0) {
      result.push({ label: 'Other', fields: ungrouped });
    }
    return result;
  }

  function formatValue(key: string, value: unknown): string {
    if (value === null || value === undefined) return '—';
    if (key.endsWith('_json') && typeof value === 'string') {
      try {
        return JSON.stringify(JSON.parse(value), null, 2);
      } catch {
        return String(value);
      }
    }
    return String(value);
  }

  function isProgressField(key: string): boolean {
    return key === 'data_completeness_pct' || key === 'enrichment_confidence';
  }

  function isSourceField(key: string): boolean {
    return key.startsWith('source_');
  }

  function isJsonField(key: string): boolean {
    return key.endsWith('_json');
  }

  function progressPercent(value: unknown): number {
    if (typeof value === 'number') return Math.min(100, Math.max(0, value));
    if (typeof value === 'string') {
      const n = parseFloat(value);
      return isNaN(n) ? 0 : Math.min(100, Math.max(0, n));
    }
    return 0;
  }
</script>

<!-- Backdrop -->
<!-- svelte-ignore a11y-click-events-have-key-events -->
<!-- svelte-ignore a11y-no-static-element-interactions -->
<div
  class="fixed inset-0 z-40 bg-black/40 backdrop-blur-sm"
  on:click={() => dispatch('close')}
  transition:fly={{ duration: 150 }}
/>

<!-- Panel -->
<div
  class="fixed inset-y-0 right-0 z-50 flex w-[480px] flex-col border-l border-white/8 bg-[#0c0e14] shadow-2xl"
  transition:fly={{ x: 480, duration: 200 }}
>
  <!-- Header -->
  <div class="flex items-center justify-between border-b border-white/8 px-5 py-4">
    <div>
      <p class="text-xs font-medium uppercase tracking-widest text-sea">Record Detail</p>
      <p class="mt-1 text-sm text-mist">
        {#if row['object_name']}
          {row['object_name']}
        {:else if row['norad_id']}
          NORAD {row['norad_id']}
        {:else}
          {table}
        {/if}
      </p>
    </div>
    <button
      class="rounded p-1.5 text-muted-foreground hover:bg-white/10 hover:text-mist"
      on:click={() => dispatch('close')}
    >
      <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 6 6 18"/><path d="m6 6 12 12"/></svg>
    </button>
  </div>

  <!-- Body -->
  <div class="flex-1 overflow-y-auto px-5 py-4">
    {#each groups as group}
      <div class="mb-4">
        <button
          class="mb-2 flex w-full items-center gap-2 text-xs font-medium uppercase tracking-widest text-muted-foreground hover:text-mist"
          on:click={() => toggleGroup(group.label)}
        >
          <svg
            xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"
            class="transition-transform {collapsedGroups.has(group.label) ? '-rotate-90' : ''}"
          ><path d="m6 9 6 6 6-6"/></svg>
          {group.label}
        </button>

        {#if !collapsedGroups.has(group.label)}
          <div class="space-y-1">
            {#each group.fields as field}
              {@const value = row[field]}
              <div class="grid grid-cols-[140px,1fr] gap-2 rounded px-2 py-1.5 hover:bg-white/[0.03]">
                <span class="truncate text-xs text-muted-foreground" title={field}>{field}</span>
                <div class="min-w-0 text-sm">
                  {#if isProgressField(field) && value !== null && value !== undefined}
                    {@const pct = progressPercent(value)}
                    <div class="flex items-center gap-2">
                      <div class="h-1.5 flex-1 rounded-full bg-white/10">
                        <div
                          class="h-1.5 rounded-full {pct >= 80 ? 'bg-sea' : pct >= 50 ? 'bg-flare' : 'bg-destructive'}"
                          style="width: {pct}%"
                        />
                      </div>
                      <span class="text-xs text-slate-200">{typeof value === 'number' ? value.toFixed(1) : value}%</span>
                    </div>
                  {:else if isJsonField(field) && value !== null && value !== undefined}
                    <pre class="max-h-40 overflow-auto whitespace-pre-wrap break-words rounded bg-black/30 px-2 py-1 text-xs text-slate-300">{formatValue(field, value)}</pre>
                  {:else if isSourceField(field)}
                    {#if value !== null && value !== undefined && value !== ''}
                      <span class="inline-flex items-center rounded bg-sea/15 px-1.5 py-0.5 text-xs text-sea">{value}</span>
                    {:else}
                      <span class="text-muted-foreground/50">—</span>
                    {/if}
                  {:else if value === null || value === undefined}
                    <span class="text-muted-foreground/50">—</span>
                  {:else}
                    <span class="break-words text-slate-200">{formatValue(field, value)}</span>
                  {/if}
                </div>
              </div>
            {/each}
          </div>
        {/if}
      </div>
    {/each}
  </div>
</div>
