<script lang="ts">
  import { goto } from '$app/navigation';
  import { onMount } from 'svelte';

  import { getCredentials } from '$lib/api/tauri/settings';
  import { getRecipeDetail, listRecipes, type Recipe, type RecipeConfigField, type RecipeDetail } from '$lib/api/tauri/recipes';
  import { startRun } from '$lib/api/tauri/runs';
  import RunConfig from '$lib/features/run/RunConfig.svelte';

  let recipes: Recipe[] = [];
  let selectedRecipe: string | null = null;
  let selectedRecipeDetail: RecipeDetail | null = null;
  let configValues: Record<string, string | number | boolean> = {};
  let credentialPresence: Record<string, { present: boolean }> = {};
  let loadingRecipes = true;
  let loadingRecipeDetail = false;
  let startingRun = false;
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
      credentialPresence = secretKeys.length > 0 ? await getCredentials(secretKeys) : {};
    } catch (error) {
      errorMessage = error instanceof Error ? error.message : 'Failed to load recipe details.';
      selectedRecipeDetail = null;
      credentialPresence = {};
    } finally {
      loadingRecipeDetail = false;
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
    if (!recipe) {
      return false;
    }

    return Object.entries(recipe.configSchema).every(([key, field]) => {
      if (!field.secret || !field.required) {
        return true;
      }
      return credentialPresence[key]?.present ?? false;
    });
  }

  function nonSecretRequiredSatisfied(recipe: RecipeDetail | null): boolean {
    if (!recipe) {
      return false;
    }

    return Object.entries(recipe.configSchema).every(([key, field]) => {
      if (field.secret || !field.required) {
        return true;
      }

      const value = configValues[key];
      if (field.type === 'boolean') {
        return typeof value === 'boolean';
      }
      return value !== '' && value !== undefined && value !== null;
    });
  }

  async function handleStartRun(): Promise<void> {
    if (!selectedRecipe || !selectedRecipeDetail || startingRun) {
      return;
    }

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
</script>

<svelte:head>
  <title>Atlas Weave</title>
  <meta name="description" content="Atlas Weave orchestration launcher" />
</svelte:head>

<div class="min-h-screen px-6 py-8 text-slate-50 lg:px-10">
  <div class="mx-auto grid max-w-7xl gap-6 lg:grid-cols-[340px,1fr]">
    <aside class="rounded-[28px] border border-white/10 bg-white/5 p-6 shadow-glow backdrop-blur">
      <div class="mb-8">
        <p class="text-xs uppercase tracking-[0.35em] text-sea">Atlas Weave</p>
        <h1 class="mt-3 text-3xl font-semibold text-mist">Recipe Launcher</h1>
        <p class="mt-3 text-sm leading-6 text-slate-300">
          Configure a run, validate any secret requirements, and jump straight into the live execution graph.
        </p>
        <a class="mt-4 inline-flex text-sm text-sky-300 underline" href="/settings">Open Settings</a>
      </div>

      <div class="space-y-3">
        {#if loadingRecipes}
          <div class="rounded-2xl border border-white/10 bg-black/20 px-4 py-3 text-sm text-slate-300">
            Loading recipes...
          </div>
        {:else if recipes.length === 0}
          <div class="rounded-2xl border border-dashed border-white/10 bg-black/20 px-4 py-6 text-sm text-slate-300">
            No recipes discovered under <code>python/recipes</code>.
          </div>
        {:else}
          {#each recipes as recipe}
            <button
              class:selected={selectedRecipe === recipe.name}
              class="w-full rounded-2xl border border-white/10 bg-black/20 px-4 py-4 text-left transition hover:border-sea/60 hover:bg-white/10"
              on:click={() => loadRecipeDetail(recipe.name)}
            >
              <div class="flex items-start justify-between gap-4">
                <div>
                  <h2 class="text-base font-medium text-mist">{recipe.name}</h2>
                  <p class="mt-2 text-sm leading-6 text-slate-300">{recipe.description}</p>
                </div>
                <span class="rounded-full bg-white/10 px-2 py-1 text-xs text-slate-300">
                  v{recipe.version}
                </span>
              </div>
            </button>
          {/each}
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

      <section class="rounded-[32px] border border-white/10 bg-ink/70 p-6 shadow-glow">
        <div class="grid gap-6 lg:grid-cols-[1.1fr,0.9fr]">
          <div class="rounded-[30px] border border-white/10 bg-gradient-to-br from-white/8 to-transparent p-6">
            <p class="text-xs uppercase tracking-[0.35em] text-flare">Phase 4</p>
            <h2 class="mt-3 text-4xl font-semibold text-mist">Run Management</h2>
            <p class="mt-4 max-w-2xl text-sm leading-7 text-slate-300">
              Launch configs are now generated from recipe metadata, secret fields are validated against Settings, and runs stay cancellable while the live DAG is active.
            </p>
          </div>

          <div class="space-y-6">
            <div class="rounded-[28px] border border-white/10 bg-white/5 p-5">
              <h3 class="text-lg font-semibold text-mist">What Opens Next</h3>
              <ul class="mt-4 space-y-3 text-sm leading-6 text-slate-300">
                <li>The run route loads persisted DAG state, run summary, and same-recipe history.</li>
                <li>Run logs page in from SQLite and continue streaming live while the run is active.</li>
                <li>Cancel requests go through Rust to the Python sidecar over stdin.</li>
              </ul>
            </div>

            <div class="rounded-[28px] border border-white/10 bg-white/5 p-5">
              <h3 class="text-lg font-semibold text-mist">Current Recipes</h3>
              <div class="mt-4 space-y-3 text-sm leading-6 text-slate-300">
                <p><code>test_echo</code> remains the smoke path for cancel and log streaming.</p>
                <p><code>test_pipeline</code> still drives the three-node DAG visualizer and failure-state checks.</p>
              </div>
            </div>
          </div>
        </div>

        {#if errorMessage}
          <div class="mt-6 rounded-2xl border border-rose-400/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-200">
            {errorMessage}
          </div>
        {/if}
      </section>
    </section>
  </div>
</div>

<style>
  .selected {
    border-color: rgba(45, 212, 191, 0.85);
    background: rgba(13, 148, 136, 0.18);
  }
</style>
