<script lang="ts">
  import { onMount } from 'svelte';

  import { Button } from '$lib/components/ui/button';
  import { Card, CardHeader, CardTitle, CardContent } from '$lib/components/ui/card';
  import { Badge } from '$lib/components/ui/badge';
  import { Skeleton } from '$lib/components/ui/skeleton';
  import { getRecipeDetail, listRecipes } from '$lib/api/tauri/recipes';
  import { getCredentials, saveCredentials } from '$lib/api/tauri/settings';
  import type { CredentialEntry } from '$lib/features/settings/types';

  let entries: CredentialEntry[] = [];
  let loading = true;
  let saving = false;
  let errorMessage = '';
  let drafts: Record<string, string> = {};

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
          if (!field.secret) continue;
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

  async function handleSave(key: string): Promise<void> {
    const value = drafts[key]?.trim();
    if (!value) return;
    saving = true;
    errorMessage = '';
    try {
      await saveCredentials({ [key]: value });
      drafts[key] = '';
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
      <a class="text-sm text-sky-300 underline hover:text-sky-200" href="/">Back to launcher</a>
      <span class="text-xs font-medium uppercase tracking-widest text-muted-foreground">
        {loading ? 'Loading credentials' : `${entries.length} secret keys`}
      </span>
    </div>

    <Card>
      <CardHeader>
        <p class="text-xs font-medium uppercase tracking-widest text-muted-foreground">Settings</p>
        <h1 class="mt-2 text-3xl font-semibold text-mist">Credentials</h1>
        <p class="mt-2 text-sm text-muted-foreground">
          Secrets are stored in the desktop secure store and injected into Python as environment variables at run start.
        </p>
      </CardHeader>
      <CardContent>
        {#if loading}
          <div class="space-y-4">
            <Skeleton class="h-24 w-full" />
            <Skeleton class="h-24 w-full" />
            <Skeleton class="h-24 w-full" />
          </div>
        {:else if entries.length === 0}
          <div class="rounded-lg border border-dashed border-white/10 bg-black/20 p-4 text-sm text-muted-foreground">
            No secret fields are defined by the installed recipes.
          </div>
        {:else}
          <div class="space-y-4">
            {#each entries as entry}
              <Card>
                <CardContent class="p-4">
                  <div class="flex items-start justify-between gap-4">
                    <div>
                      <div class="flex items-center gap-2">
                        <h2 class="text-lg font-semibold text-mist">{entry.key}</h2>
                        <Badge variant={entry.present ? 'completed' : 'failed'}>
                          {entry.present ? 'Saved' : 'Missing'}
                        </Badge>
                      </div>
                      <p class="mt-2 text-sm text-muted-foreground">{entry.description}</p>
                      <p class="mt-1 text-xs font-medium uppercase tracking-widest text-muted-foreground">
                        Used by {entry.recipes.join(', ')}
                      </p>
                    </div>
                  </div>

                  <div class="mt-4 grid gap-3 md:grid-cols-[1fr,auto,auto]">
                    <input
                      bind:value={drafts[entry.key]}
                      type="password"
                      placeholder={entry.present ? 'Replace saved credential' : 'Enter credential value'}
                      class="w-full rounded-lg border border-white/8 bg-slate-900/90 px-3 py-2 text-sm text-slate-50 focus:outline-none focus:ring-2 focus:ring-ring"
                    />
                    <Button disabled={saving} onclick={() => handleSave(entry.key)}>
                      Save
                    </Button>
                    <Button
                      variant="destructive"
                      disabled={saving || !entry.present}
                      onclick={() => handleRemove(entry.key)}
                    >
                      Delete
                    </Button>
                  </div>
                </CardContent>
              </Card>
            {/each}
          </div>
        {/if}
      </CardContent>
    </Card>

    {#if errorMessage}
      <div class="rounded-lg border border-rose-400/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-200">
        {errorMessage}
      </div>
    {/if}
  </div>
</div>
