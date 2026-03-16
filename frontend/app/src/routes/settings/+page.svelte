<script lang="ts">
  import { onMount } from 'svelte';

  import { getRecipeDetail, listRecipes } from '$lib/api/tauri/recipes';
  import { getCredentials, saveCredentials } from '$lib/api/tauri/settings';
  import Credentials from '$lib/features/settings/Credentials.svelte';
  import type { CredentialEntry } from '$lib/features/settings/types';

  let entries: CredentialEntry[] = [];
  let loading = true;
  let saving = false;
  let errorMessage = '';

  onMount(() => {
    void loadEntries();
  });

  async function loadEntries(): Promise<void> {
    loading = true;
    errorMessage = '';

    try {
      const recipes = await listRecipes();
      const details = await Promise.all(recipes.map((recipe) => getRecipeDetail(recipe.name)));
      const metadata = new Map<string, CredentialEntry>();

      for (const detail of details) {
        for (const [key, field] of Object.entries(detail.configSchema)) {
          if (!field.secret) {
            continue;
          }

          const existing = metadata.get(key);
          if (existing) {
            existing.recipes = [...existing.recipes, detail.name];
            continue;
          }

          metadata.set(key, {
            key,
            description: field.description ?? 'Managed secret used by this recipe.',
            recipes: [detail.name],
            present: false
          });
        }
      }

      const keys = [...metadata.keys()];
      const presence = keys.length > 0 ? await getCredentials(keys) : {};
      entries = keys
        .map((key) => ({
          ...metadata.get(key)!,
          present: presence[key]?.present ?? false
        }))
        .sort((left, right) => left.key.localeCompare(right.key));
    } catch (error) {
      errorMessage = error instanceof Error ? error.message : 'Failed to load credentials.';
    } finally {
      loading = false;
    }
  }

  async function handleSave(key: string, value: string): Promise<void> {
    saving = true;
    errorMessage = '';

    try {
      await saveCredentials({ [key]: value });
      await loadEntries();
    } catch (error) {
      errorMessage = error instanceof Error ? error.message : 'Failed to save credential.';
    } finally {
      saving = false;
    }
  }

  async function handleRemove(key: string): Promise<void> {
    saving = true;
    errorMessage = '';

    try {
      await saveCredentials({ [key]: null });
      await loadEntries();
    } catch (error) {
      errorMessage = error instanceof Error ? error.message : 'Failed to delete credential.';
    } finally {
      saving = false;
    }
  }
</script>

<svelte:head>
  <title>Atlas Weave Settings</title>
  <meta name="description" content="Atlas Weave credential settings" />
</svelte:head>

<div class="min-h-screen px-6 py-8 text-slate-50 lg:px-10">
  <div class="mx-auto max-w-6xl space-y-6">
    <div class="flex items-center justify-between gap-4">
      <a class="text-sm text-sky-300 underline" href="/">Back to launcher</a>
      <span class="text-xs uppercase tracking-[0.24em] text-slate-500">
        {loading ? 'Loading credentials' : `${entries.length} secret keys`}
      </span>
    </div>

    <Credentials
      {entries}
      {saving}
      on:save={(event) => handleSave(event.detail.key, event.detail.value)}
      on:remove={(event) => handleRemove(event.detail.key)}
    />

    {#if errorMessage}
      <div class="rounded-2xl border border-rose-400/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-200">
        {errorMessage}
      </div>
    {/if}
  </div>
</div>
