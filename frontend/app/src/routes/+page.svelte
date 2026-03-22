<script lang="ts">
  import { goto } from '$app/navigation';
  import { onMount } from 'svelte';

  import { Button } from '$lib/components/ui/button';
  import { Badge } from '$lib/components/ui/badge';
  import { Card, CardHeader, CardTitle, CardContent } from '$lib/components/ui/card';
  import { Skeleton } from '$lib/components/ui/skeleton';
  import { getCredentials } from '$lib/api/tauri/settings';
  import { getRecipeDetail, listRecipes, type Recipe, type RecipeConfigField, type RecipeDetail } from '$lib/api/tauri/recipes';
  import { getRunHistory, startRun, type RunHistoryItem } from '$lib/api/tauri/runs';
  import RunConfig from '$lib/features/run/RunConfig.svelte';
  import SchedulePanel from '$lib/features/schedule/SchedulePanel.svelte';

  let recipes: Recipe[] = [];
  let selectedRecipe: string | null = null;
  let selectedRecipeDetail: RecipeDetail | null = null;
  let configValues: Record<string, string | number | boolean> = {};
  let credentialPresence: Record<string, { present: boolean }> = {};
  let loadingRecipes = true;
  let loadingRecipeDetail = false;
  let loadingRunHistory = false;
  let startingRun = false;
  let recentRuns: RunHistoryItem[] = [];
  let errorMessage = '';

  onMount(() => {
    void loadRecipes();
  });

  async function loadRecipes(): Promise<void> {
    loadingRecipes = true;
    errorMessage = '';

    try {
      recipes = await listRecipes();
      selectedRecipe = recipes[0]?.name ?? null;
      if (selectedRecipe) {
        await loadRecipeDetail(selectedRecipe);
      }
    } catch (error) {
      errorMessage = error instanceof Error ? error.message : 'Failed to load recipes.';
    } finally {
      loadingRecipes = false;
    }
  }

  async function loadRecipeDetail(recipeName: string): Promise<void> {
    loadingRecipeDetail = true;
    errorMessage = '';

    try {
      selectedRecipe = recipeName;
      selectedRecipeDetail = await getRecipeDetail(recipeName);
      configValues = defaultsFor(selectedRecipeDetail.configSchema);

      const secretKeys = Object.entries(selectedRecipeDetail.configSchema)
        .filter(([, field]) => field.secret)
        .map(([key]) => key);

      // Parallel API calls for credentials and run history
      const [creds] = await Promise.all([
        secretKeys.length > 0 ? getCredentials(secretKeys) : Promise.resolve({}),
        loadRecentRuns(recipeName)
      ]);
      credentialPresence = creds;
    } catch (error) {
      errorMessage = error instanceof Error ? error.message : 'Failed to load recipe details.';
      selectedRecipeDetail = null;
      credentialPresence = {};
      recentRuns = [];
    } finally {
      loadingRecipeDetail = false;
    }
  }

  async function loadRecentRuns(recipeName: string): Promise<void> {
    loadingRunHistory = true;
    try {
      const response = await getRunHistory(recipeName, 1, 5);
      recentRuns = response.items;
    } catch (error) {
      recentRuns = [];
      console.error('Failed to load run history', error);
    } finally {
      loadingRunHistory = false;
    }
  }

  function defaultsFor(
    configSchema: Record<string, RecipeConfigField>
  ): Record<string, string | number | boolean> {
    return Object.fromEntries(
      Object.entries(configSchema)
        .filter(([, field]) => !field.secret)
        .map(([key, field]) => [
          key,
          field.default ?? (field.type === 'boolean' ? false : '')
        ])
    );
  }

  function secretRequirementsSatisfied(recipe: RecipeDetail | null): boolean {
    if (!recipe) return false;
    return Object.entries(recipe.configSchema).every(([key, field]) => {
      if (!field.secret || !field.required) return true;
      return credentialPresence[key]?.present ?? false;
    });
  }

  function nonSecretRequiredSatisfied(recipe: RecipeDetail | null): boolean {
    if (!recipe) return false;
    return Object.entries(recipe.configSchema).every(([key, field]) => {
      if (field.secret || !field.required) return true;
      const value = configValues[key];
      if (field.type === 'boolean') return typeof value === 'boolean';
      return value !== '' && value !== undefined && value !== null;
    });
  }

  async function handleStartRun(): Promise<void> {
    if (!selectedRecipe || !selectedRecipeDetail || startingRun) return;
    startingRun = true;
    errorMessage = '';
    try {
      const response = await startRun(selectedRecipe, configValues);
      await goto(`/run/${response.runId}`);
    } catch (error) {
      errorMessage = error instanceof Error ? error.message : 'Failed to start run.';
    } finally {
      startingRun = false;
    }
  }

  async function openRun(runId: string): Promise<void> {
    await goto(`/run/${runId}`);
  }

  function handleKeydown(event: KeyboardEvent): void {
    if ((event.ctrlKey || event.metaKey) && event.key === 'r') {
      event.preventDefault();
      if (
        selectedRecipeDetail &&
        !startingRun &&
        !loadingRecipeDetail &&
        secretRequirementsSatisfied(selectedRecipeDetail) &&
        nonSecretRequiredSatisfied(selectedRecipeDetail)
      ) {
        void handleStartRun();
      }
    }
  }

  function statusVariant(s: string): 'running' | 'completed' | 'failed' | 'cancelled' | 'pending' {
    if (s === 'completed') return 'completed';
    if (s === 'failed') return 'failed';
    if (s === 'cancelled') return 'cancelled';
    if (s === 'running') return 'running';
    return 'pending';
  }
</script>

<svelte:window on:keydown={handleKeydown} />

<svelte:head>
  <title>Atlas Weave</title>
  <meta name="description" content="Atlas Weave orchestration launcher" />
</svelte:head>

<div class="min-h-screen px-6 py-8 text-slate-50 lg:px-10">
  <div class="mx-auto grid max-w-7xl gap-6 lg:grid-cols-[340px,1fr]">
    <aside class="rounded-xl border border-white/10 bg-white/5 p-6 shadow-glow backdrop-blur">
      <div class="mb-8">
        <p class="text-xs font-medium uppercase tracking-widest text-sea">Atlas Weave</p>
        <h1 class="mt-3 text-3xl font-semibold text-mist">Recipe Launcher</h1>
        <p class="mt-3 text-sm leading-6 text-muted-foreground">
          Configure a run, validate any secret requirements, and jump straight into the live execution graph.
        </p>
        <a class="mt-4 inline-flex text-sm text-sky-300 underline hover:text-sky-200" href="/settings">Open Settings</a>
      </div>

      <div class="space-y-3">
        {#if loadingRecipes}
          <Skeleton class="h-20 w-full" />
          <Skeleton class="h-20 w-full" />
        {:else if recipes.length === 0}
          <div class="rounded-lg border border-dashed border-white/10 bg-black/20 p-6 text-sm text-muted-foreground">
            <p class="font-medium text-foreground">Welcome to Atlas Weave</p>
            <p class="mt-2">Add recipes under <code class="text-sea">python/recipes/</code> to get started.</p>
          </div>
        {:else}
          {#each recipes as recipe}
            <button
              class="w-full rounded-lg border bg-black/20 p-4 text-left transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sea {selectedRecipe === recipe.name ? 'border-sea/80 bg-sea/10' : 'border-white/10 hover:border-sea/60 hover:bg-white/10'}"
              on:click={() => loadRecipeDetail(recipe.name)}
            >
              <div class="flex items-start justify-between gap-4">
                <div>
                  <h2 class="text-base font-medium text-mist">{recipe.name}</h2>
                  <p class="mt-2 text-sm leading-6 text-muted-foreground">{recipe.description}</p>
                </div>
                <div class="flex items-center gap-2">
                  <a
                    href="/data/{recipe.name}"
                    class="text-xs text-sky-300 underline hover:text-sky-200"
                    on:click|stopPropagation
                  >View Data</a>
                  <Badge variant="outline">v{recipe.version}</Badge>
                </div>
              </div>
            </button>
          {/each}
        {/if}
      </div>

      <div class="mt-8 border-t border-white/10 pt-6">
        <div class="mb-4 flex items-center justify-between gap-3">
          <div>
            <p class="text-xs font-medium uppercase tracking-widest text-sea">Existing Runs</p>
            <p class="mt-2 text-sm text-muted-foreground">
              Reopen a recent run for the selected recipe.
            </p>
          </div>

          {#if recentRuns[0]}
            <Button variant="outline" size="sm" onclick={() => openRun(recentRuns[0].id)}>
              Open Latest
            </Button>
          {/if}
        </div>

        {#if loadingRunHistory}
          <div class="space-y-3">
            <Skeleton class="h-14 w-full" />
            <Skeleton class="h-14 w-full" />
          </div>
        {:else if recentRuns.length === 0}
          <div class="rounded-lg border border-dashed border-white/10 bg-black/20 p-4 text-sm text-muted-foreground">
            No recorded runs for this recipe yet.
          </div>
        {:else}
          <div class="space-y-2">
            {#each recentRuns as run}
              <button
                class="w-full rounded-lg border border-white/10 bg-black/20 p-3 text-left transition hover:border-sky-300/40 hover:bg-white/10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                on:click={() => openRun(run.id)}
              >
                <div class="flex items-center justify-between gap-3">
                  <div class="min-w-0">
                    <Badge variant={statusVariant(run.status)}>{run.status}</Badge>
                    <p class="mt-1.5 truncate text-xs text-muted-foreground">
                      {run.startedAt ? new Date(run.startedAt).toLocaleString() : 'Unknown start'}
                    </p>
                  </div>
                  <span class="text-xs text-muted-foreground">
                    {run.completedNodes + run.failedNodes + run.skippedNodes + run.cancelledNodes + run.runningNodes + run.pendingNodes} nodes
                  </span>
                </div>
              </button>
            {/each}
          </div>
        {/if}
      </div>
    </aside>

    <section class="space-y-6">
      <RunConfig
        recipe={selectedRecipeDetail}
        values={configValues}
        {credentialPresence}
        starting={startingRun}
        disabled={
          !selectedRecipeDetail ||
          loadingRecipeDetail ||
          startingRun ||
          !secretRequirementsSatisfied(selectedRecipeDetail) ||
          !nonSecretRequiredSatisfied(selectedRecipeDetail)
        }
        on:change={(event) => {
          configValues = { ...configValues, [event.detail.key]: event.detail.value };
        }}
        on:submit={handleStartRun}
      />

      {#if selectedRecipe}
        <SchedulePanel recipeName={selectedRecipe} />
      {/if}

      {#if errorMessage}
        <div class="rounded-lg border border-rose-400/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-200">
          {errorMessage}
        </div>
      {/if}
    </section>
  </div>
</div>
