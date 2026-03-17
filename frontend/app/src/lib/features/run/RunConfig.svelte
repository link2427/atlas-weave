<script lang="ts">
  import { createEventDispatcher } from 'svelte';

  import { Button } from '$lib/components/ui/button';
  import { Card, CardHeader, CardTitle, CardContent } from '$lib/components/ui/card';
  import { Badge } from '$lib/components/ui/badge';
  import { pickCsvFile } from '$lib/api/tauri/files';
  import type { RecipeConfigField, RecipeDetail } from '$lib/api/tauri/recipes';

  export let recipe: RecipeDetail | null = null;
  export let values: Record<string, string | number | boolean> = {};
  export let credentialPresence: Record<string, { present: boolean }> = {};
  export let starting = false;
  export let disabled = false;

  const dispatch = createEventDispatcher<{
    change: { key: string; value: string | number | boolean };
    submit: undefined;
  }>();
  let pickingKey: string | null = null;

  $: fields = Object.entries(recipe?.configSchema ?? {}) as Array<[string, RecipeConfigField]>;

  function valueFor(key: string, field: RecipeConfigField): string | number | boolean {
    return values[key] ?? field.default ?? (field.type === 'boolean' ? false : '');
  }

  function handleValueChange(key: string, field: RecipeConfigField, event: Event): void {
    const target = event.currentTarget as HTMLInputElement | HTMLSelectElement;
    let value: string | number | boolean = target.value;
    if (field.type === 'boolean' && target instanceof HTMLInputElement) {
      value = target.checked;
    } else if (field.type === 'number' || field.type === 'integer') {
      value = target.value === '' ? '' : Number(target.value);
    }
    dispatch('change', { key, value });
  }

  function isCsvPathField(key: string, field: RecipeConfigField): boolean {
    return !field.secret && field.type === 'string' && key === 'ucs_catalog_csv_path';
  }

  async function handlePickCsvFile(key: string): Promise<void> {
    pickingKey = key;
    try {
      const selected = await pickCsvFile();
      if (selected) {
        dispatch('change', { key, value: selected });
      }
    } finally {
      pickingKey = null;
    }
  }
</script>

<section class="rounded-xl border border-white/8 bg-white/[0.04] p-6">
  <div class="mb-6">
    <p class="text-xs font-medium uppercase tracking-widest text-muted-foreground">Run Config</p>
    <h2 class="mt-2 text-2xl font-semibold text-mist">
      {recipe?.name ?? 'Select a recipe'}
    </h2>
    <p class="mt-2 text-sm text-muted-foreground">
      {recipe?.description ?? 'Choose a recipe to inspect its launch configuration.'}
    </p>
  </div>

  {#if !recipe}
    <div class="rounded-lg border border-dashed border-white/10 bg-black/20 p-4 text-sm text-muted-foreground">
      Select a recipe to configure and start a run.
    </div>
  {:else if fields.length === 0}
    <div class="rounded-lg border border-dashed border-white/10 bg-black/20 p-4 text-sm text-muted-foreground">
      This recipe does not require launch-time configuration.
    </div>
  {:else}
    <div class="space-y-4">
      {#each fields as [key, field]}
        <Card>
          <CardContent class="p-4">
            <div class="mb-3">
              <div class="flex items-center gap-2">
                <span class="text-sm font-semibold text-slate-50">{key}</span>
                {#if field.required}
                  <Badge variant="completed">Required</Badge>
                {/if}
                {#if field.secret}
                  <Badge variant={credentialPresence[key]?.present ? 'completed' : 'failed'}>
                    {credentialPresence[key]?.present ? 'Saved in Settings' : 'Missing in Settings'}
                  </Badge>
                {/if}
              </div>
              {#if field.description}
                <p class="mt-1 text-sm text-muted-foreground">{field.description}</p>
              {/if}
            </div>

            {#if field.secret}
              <a class="text-sm text-sky-300 underline hover:text-sky-200" href="/settings">Manage this credential in Settings</a>
            {:else if isCsvPathField(key, field)}
              <div class="grid gap-3 md:grid-cols-[1fr,auto]">
                <input
                  type="text"
                  value={String(valueFor(key, field))}
                  on:input={(event) => handleValueChange(key, field, event)}
                  placeholder="Select a CSV file or paste a path"
                  class="w-full rounded-lg border border-white/8 bg-slate-900/90 px-3 py-2 text-sm text-slate-50 focus:outline-none focus:ring-2 focus:ring-ring"
                />
                <Button
                  variant="outline"
                  disabled={pickingKey === key}
                  onclick={() => handlePickCsvFile(key)}
                >
                  {pickingKey === key ? 'Choosing...' : 'Choose CSV'}
                </Button>
              </div>
            {:else if field.type === 'boolean'}
              <input
                type="checkbox"
                checked={Boolean(valueFor(key, field))}
                on:change={(event) => handleValueChange(key, field, event)}
                class="h-5 w-5 rounded border border-white/8 bg-slate-900/90"
              />
            {:else if field.enum}
              <select
                value={String(valueFor(key, field))}
                on:change={(event) => handleValueChange(key, field, event)}
                class="w-full rounded-lg border border-white/8 bg-slate-900/90 px-3 py-2 text-sm text-slate-50 focus:outline-none focus:ring-2 focus:ring-ring"
              >
                {#each field.enum as option}
                  <option value={String(option)}>{option}</option>
                {/each}
              </select>
            {:else}
              <input
                type={field.type === 'number' || field.type === 'integer' ? 'number' : 'text'}
                step={field.type === 'integer' ? '1' : 'any'}
                value={String(valueFor(key, field))}
                on:input={(event) => handleValueChange(key, field, event)}
                class="w-full rounded-lg border border-white/8 bg-slate-900/90 px-3 py-2 text-sm text-slate-50 focus:outline-none focus:ring-2 focus:ring-ring"
              />
            {/if}
          </CardContent>
        </Card>
      {/each}
    </div>
  {/if}

  <div class="mt-6 flex items-center justify-between gap-4">
    <p class="text-sm text-muted-foreground">
      Secret fields are injected from secure storage and never persisted with the run record.
    </p>
    <Button disabled={disabled} onclick={() => dispatch('submit')}>
      {starting ? 'Starting...' : 'Start Run'}
    </Button>
  </div>
</section>
