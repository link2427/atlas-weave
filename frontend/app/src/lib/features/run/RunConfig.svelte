<script lang="ts">
  import { createEventDispatcher } from 'svelte';

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

  function handleValueChange(
    key: string,
    field: RecipeConfigField,
    event: Event
  ): void {
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

<section class="panel">
  <div class="mb-6">
    <p class="eyebrow">Run Config</p>
    <h2 class="mt-2 text-2xl font-semibold text-mist">
      {recipe?.name ?? 'Select a recipe'}
    </h2>
    <p class="mt-3 text-sm leading-6 text-slate-300">
      {recipe?.description ?? 'Choose a recipe to inspect its launch configuration.'}
    </p>
  </div>

  {#if !recipe}
    <div class="empty-state">Select a recipe to configure and start a run.</div>
  {:else if fields.length === 0}
    <div class="empty-state">
      This recipe does not require launch-time configuration.
    </div>
  {:else}
    <div class="space-y-4">
      {#each fields as [key, field]}
        <label class="field">
          <div class="field-copy">
            <div class="flex items-center gap-3">
              <span class="field-label">{key}</span>
              {#if field.required}
                <span class="pill required">Required</span>
              {/if}
              {#if field.secret}
                <span class="pill secret">
                  {credentialPresence[key]?.present ? 'Saved in Settings' : 'Missing in Settings'}
                </span>
              {/if}
            </div>
            {#if field.description}
              <p class="field-description">{field.description}</p>
            {/if}
          </div>

          {#if field.secret}
            <a class="settings-link" href="/settings">Manage this credential in Settings</a>
          {:else if isCsvPathField(key, field)}
            <div class="picker-row">
              <input
                type="text"
                value={String(valueFor(key, field))}
                on:input={(event) => handleValueChange(key, field, event)}
                placeholder="Select a CSV file or paste a path"
              />
              <button
                type="button"
                class="picker-button"
                disabled={pickingKey === key}
                on:click={() => handlePickCsvFile(key)}
              >
                {pickingKey === key ? 'Choosing...' : 'Choose CSV'}
              </button>
            </div>
          {:else if field.type === 'boolean'}
            <input
              type="checkbox"
              checked={Boolean(valueFor(key, field))}
              on:change={(event) => handleValueChange(key, field, event)}
            />
          {:else if field.enum}
            <select value={String(valueFor(key, field))} on:change={(event) => handleValueChange(key, field, event)}>
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
            />
          {/if}
        </label>
      {/each}
    </div>
  {/if}

  <div class="mt-8 flex items-center justify-between gap-4">
    <p class="text-sm text-slate-400">
      Secret fields are injected from secure storage and never persisted with the run record.
    </p>
    <button class="launch-button" disabled={disabled} on:click={() => dispatch('submit')}>
      {starting ? 'Starting...' : 'Start Run'}
    </button>
  </div>
</section>

<style>
  .panel {
    border-radius: 2rem;
    border: 1px solid rgba(255, 255, 255, 0.08);
    background: rgba(255, 255, 255, 0.05);
    padding: 1.5rem;
  }

  .eyebrow {
    font-size: 0.72rem;
    letter-spacing: 0.24em;
    text-transform: uppercase;
    color: rgba(148, 163, 184, 0.84);
  }

  .empty-state {
    border-radius: 1.5rem;
    border: 1px dashed rgba(148, 163, 184, 0.28);
    background: rgba(2, 6, 23, 0.35);
    padding: 1rem 1.1rem;
    color: rgba(203, 213, 225, 0.88);
  }

  .field {
    display: grid;
    gap: 0.9rem;
    border-radius: 1.5rem;
    border: 1px solid rgba(255, 255, 255, 0.08);
    background: rgba(2, 6, 23, 0.4);
    padding: 1rem 1.1rem;
  }

  .field-label {
    font-size: 0.95rem;
    font-weight: 600;
    color: #f8fafc;
  }

  .field-description {
    margin-top: 0.4rem;
    color: #94a3b8;
    line-height: 1.5;
  }

  .pill {
    border-radius: 9999px;
    padding: 0.2rem 0.6rem;
    font-size: 0.68rem;
    letter-spacing: 0.16em;
    text-transform: uppercase;
  }

  .pill.required {
    background: rgba(56, 189, 248, 0.16);
    color: #bae6fd;
  }

  .pill.secret {
    background: rgba(45, 212, 191, 0.16);
    color: #99f6e4;
  }

  input,
  select {
    width: 100%;
    border-radius: 1rem;
    border: 1px solid rgba(255, 255, 255, 0.08);
    background: rgba(15, 23, 42, 0.92);
    padding: 0.8rem 0.9rem;
    color: #f8fafc;
  }

  .picker-row {
    display: grid;
    gap: 0.75rem;
  }

  .picker-button {
    border-radius: 9999px;
    border: 1px solid rgba(125, 211, 252, 0.25);
    background: rgba(14, 116, 144, 0.24);
    padding: 0.75rem 1rem;
    color: #bae6fd;
    font-weight: 600;
  }

  .picker-button:disabled {
    cursor: not-allowed;
    opacity: 0.65;
  }

  @media (min-width: 768px) {
    .picker-row {
      grid-template-columns: minmax(0, 1fr) auto;
      align-items: center;
    }
  }

  input[type='checkbox'] {
    width: 1.25rem;
    height: 1.25rem;
  }

  .settings-link {
    color: #7dd3fc;
    text-decoration: underline;
  }

  .launch-button {
    border-radius: 9999px;
    background: #2dd4bf;
    padding: 0.85rem 1.25rem;
    font-weight: 600;
    color: #082f49;
    transition: opacity 160ms ease, transform 160ms ease;
  }

  .launch-button:disabled {
    cursor: not-allowed;
    opacity: 0.55;
  }
</style>
