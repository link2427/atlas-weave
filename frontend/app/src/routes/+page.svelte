<script lang="ts">
  import { goto } from '$app/navigation';
  import { onMount } from 'svelte';

  import { listRecipes, type Recipe } from '$lib/api/tauri/recipes';
  import { startRun } from '$lib/api/tauri/runs';

  let recipes: Recipe[] = [];
  let selectedRecipe: string | null = null;
  let loadingRecipes = true;
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
    } catch (error) {
      errorMessage = error instanceof Error ? error.message : 'Failed to load recipes.';
    } finally {
      loadingRecipes = false;
    }
  }

  async function handleStartRun(): Promise<void> {
    if (!selectedRecipe || startingRun) {
      return;
    }

    startingRun = true;
    errorMessage = '';

    try {
      const response = await startRun(selectedRecipe);
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
          Start a run and jump straight into the live execution graph.
        </p>
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
              on:click={() => (selectedRecipe = recipe.name)}
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

    <section class="flex min-h-[720px] flex-col rounded-[32px] border border-white/10 bg-ink/70 p-6 shadow-glow">
      <div class="grid gap-6 lg:grid-cols-[1.1fr,0.9fr]">
        <div class="rounded-[30px] border border-white/10 bg-gradient-to-br from-white/8 to-transparent p-6">
          <p class="text-xs uppercase tracking-[0.35em] text-flare">Phase 3</p>
          <h2 class="mt-3 text-4xl font-semibold text-mist">Real-time DAG Viewer</h2>
          <p class="mt-4 max-w-2xl text-sm leading-7 text-slate-300">
            Each run now opens into a dedicated route with node state transitions, edge pulses, and
            node-level inspection. The launcher only starts runs and hands control to the visualizer.
          </p>

          <div class="mt-8 flex flex-wrap items-center gap-4">
            <button
              class="inline-flex items-center justify-center rounded-full bg-sea px-6 py-3 text-sm font-semibold text-slate-950 transition hover:bg-teal-300 disabled:cursor-not-allowed disabled:opacity-60"
              disabled={!selectedRecipe || startingRun}
              on:click={handleStartRun}
            >
              {startingRun ? 'Starting...' : 'Start Run'}
            </button>

            <span class="rounded-full border border-white/10 bg-black/20 px-4 py-2 text-sm text-slate-300">
              {selectedRecipe ?? 'Select a recipe to begin'}
            </span>
          </div>
        </div>

        <div class="space-y-6">
          <div class="rounded-[28px] border border-white/10 bg-white/5 p-5">
            <h3 class="text-lg font-semibold text-mist">What Opens Next</h3>
            <ul class="mt-4 space-y-3 text-sm leading-6 text-slate-300">
              <li>The run route hydrates the DAG from SQLite before live events attach.</li>
              <li>Node details expose Summary and Logs today, with Tools and Data scaffolded.</li>
              <li>Edge pulses are triggered when upstream nodes complete.</li>
            </ul>
          </div>

          <div class="rounded-[28px] border border-white/10 bg-white/5 p-5">
            <h3 class="text-lg font-semibold text-mist">Current Recipes</h3>
            <div class="mt-4 space-y-3 text-sm leading-6 text-slate-300">
              <p><code>test_echo</code> remains the smoke path.</p>
              <p><code>test_pipeline</code> drives the three-node DAG visualizer.</p>
              <p>Failure-state verification still uses config-driven backend invocation during development.</p>
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
  </div>
</div>

<style>
  .selected {
    border-color: rgba(45, 212, 191, 0.85);
    background: rgba(13, 148, 136, 0.18);
  }
</style>
