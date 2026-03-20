<script lang="ts">
  import { page } from '$app/stores';
  import { onMount } from 'svelte';

  import { Button } from '$lib/components/ui/button';
  import { resolveRecipeDbPath } from '$lib/api/tauri/data';
  import DataBrowser from '$lib/features/data/DataBrowser.svelte';

  let recipeName = '';
  let dbPath: string | null = null;
  let loading = true;
  let error = '';

  $: recipeName = $page.params.recipe ?? '';

  onMount(async () => {
    try {
      const urlDb = $page.url.searchParams.get('db');
      if (urlDb) {
        dbPath = urlDb;
      } else {
        dbPath = await resolveRecipeDbPath(recipeName);
      }
    } catch (e) {
      error = e instanceof Error ? e.message : 'Failed to resolve database path.';
    } finally {
      loading = false;
    }
  });
</script>

<svelte:head>
  <title>Data Inspector — {recipeName}</title>
</svelte:head>

<div class="flex h-screen flex-col text-slate-50">
  {#if loading}
    <div class="flex flex-1 items-center justify-center">
      <p class="text-sm text-muted-foreground">Loading...</p>
    </div>
  {:else if error}
    <div class="flex flex-1 items-center justify-center">
      <div class="text-center">
        <p class="text-sm text-rose-300">{error}</p>
        <a href="/" class="mt-4 inline-block text-sm text-sky-300 underline hover:text-sky-200">Back to launcher</a>
      </div>
    </div>
  {:else if !dbPath}
    <div class="flex flex-1 items-center justify-center">
      <div class="text-center">
        <p class="text-lg font-medium text-mist">No output database found</p>
        <p class="mt-2 text-sm text-muted-foreground">
          Run the <span class="font-mono text-sea">{recipeName}</span> recipe first to generate output data.
        </p>
        <a href="/">
          <Button variant="outline" class="mt-4">Go to Recipe Launcher</Button>
        </a>
      </div>
    </div>
  {:else}
    <DataBrowser {dbPath} {recipeName} />
  {/if}
</div>
