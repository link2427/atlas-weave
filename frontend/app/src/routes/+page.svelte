<script lang="ts">
  import { listen, type UnlistenFn } from '@tauri-apps/api/event';
  import { onDestroy, onMount, tick } from 'svelte';

  import { listRecipes, type Recipe } from '$lib/api/tauri/recipes';
  import { startRun } from '$lib/api/tauri/runs';
  import { eventStore, type AtlasWeaveEvent } from '$lib/stores/events';

  let recipes: Recipe[] = [];
  let selectedRecipe: string | null = null;
  let loadingRecipes = true;
  let startingRun = false;
  let errorMessage = '';
  let logContainer: HTMLDivElement | null = null;

  $: state = $eventStore;
  $: logLines = state.events.map((event) => formatEvent(event));
  $: if (logLines.length > 0) {
    void tick().then(() => {
      if (logContainer) {
        logContainer.scrollTop = logContainer.scrollHeight;
      }
    });
  }

  onMount(() => {
    let unlisten: UnlistenFn | null = null;

    void loadRecipes();
    void listen<AtlasWeaveEvent>('atlas-weave:event', (event) => {
      eventStore.push(event.payload);
    }).then((dispose) => {
      unlisten = dispose;
    });

    return () => {
      if (unlisten) {
        void unlisten();
      }
    };
  });

  onDestroy(() => {
    errorMessage = '';
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
      eventStore.reset(response.runId);
    } catch (error) {
      errorMessage = error instanceof Error ? error.message : 'Failed to start run.';
    } finally {
      startingRun = false;
    }
  }

  function formatEvent(event: AtlasWeaveEvent): string {
    const timestamp = event.timestamp
      ? new Date(event.timestamp).toLocaleTimeString()
      : new Date().toLocaleTimeString();
    const level = event.level ? event.level.toUpperCase() : event.type.toUpperCase();
    const message =
      event.message ??
      event.error ??
      (event.summary ? JSON.stringify(event.summary) : JSON.stringify(event));

    return `${timestamp} [${level}] ${message}`;
  }
</script>

<svelte:head>
  <title>Atlas Weave</title>
  <meta name="description" content="Atlas Weave desktop orchestration shell" />
</svelte:head>

<div class="min-h-screen px-6 py-8 text-slate-50 lg:px-10">
  <div class="mx-auto grid max-w-7xl gap-6 lg:grid-cols-[320px,1fr]">
    <aside class="rounded-[28px] border border-white/10 bg-white/5 p-6 shadow-glow backdrop-blur">
      <div class="mb-8">
        <p class="text-xs uppercase tracking-[0.35em] text-sea">Atlas Weave</p>
        <h1 class="mt-3 text-3xl font-semibold text-mist">Recipe Launcher</h1>
        <p class="mt-3 text-sm leading-6 text-slate-300">
          Phase 1 shell for launching a Python recipe and streaming raw events through Rust.
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
      <div class="flex flex-col gap-4 border-b border-white/10 pb-6 md:flex-row md:items-center md:justify-between">
        <div>
          <p class="text-xs uppercase tracking-[0.35em] text-flare">Live Run</p>
          <h2 class="mt-3 text-3xl font-semibold text-mist">
            {selectedRecipe ?? 'Select a recipe'}
          </h2>
          <p class="mt-3 text-sm text-slate-300">
            Status:
            <span class="font-medium text-white">{state.status}</span>
            {#if state.activeRunId}
              - Run ID <code>{state.activeRunId}</code>
            {/if}
          </p>
        </div>

        <button
          class="inline-flex items-center justify-center rounded-full bg-sea px-6 py-3 text-sm font-semibold text-slate-950 transition hover:bg-teal-300 disabled:cursor-not-allowed disabled:opacity-60"
          disabled={!selectedRecipe || startingRun}
          on:click={handleStartRun}
        >
          {startingRun ? 'Starting...' : 'Start Run'}
        </button>
      </div>

      {#if errorMessage}
        <div class="mt-4 rounded-2xl border border-rose-400/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-200">
          {errorMessage}
        </div>
      {/if}

      <div class="mt-6 grid flex-1 gap-6 lg:grid-cols-[1.1fr,0.9fr]">
        <div class="rounded-[28px] border border-white/10 bg-white/5 p-5">
          <div class="mb-4 flex items-center justify-between">
            <h3 class="text-lg font-semibold text-mist">Event Stream</h3>
            <span class="text-xs uppercase tracking-[0.3em] text-slate-400">
              {state.events.length} events
            </span>
          </div>
          <div
            bind:this={logContainer}
            class="h-[460px] overflow-y-auto rounded-2xl border border-white/10 bg-[#020713] p-4 font-mono text-sm text-slate-200"
          >
            {#if logLines.length === 0}
              <p class="text-slate-500">Waiting for a run to start.</p>
            {:else}
              {#each logLines as line}
                <div class="whitespace-pre-wrap py-1">{line}</div>
              {/each}
            {/if}
          </div>
        </div>

        <div class="space-y-6">
          <div class="rounded-[28px] border border-white/10 bg-white/5 p-5">
            <h3 class="text-lg font-semibold text-mist">Protocol Notes</h3>
            <ul class="mt-4 space-y-3 text-sm leading-6 text-slate-300">
              <li>Rust launches Python with unbuffered stdout for low-latency JSON lines.</li>
              <li>Each line is persisted to SQLite before it is emitted to the UI.</li>
              <li>stderr is treated as diagnostics and mirrored into the log stream.</li>
            </ul>
          </div>

          <div class="rounded-[28px] border border-white/10 bg-gradient-to-br from-white/8 to-transparent p-5">
            <h3 class="text-lg font-semibold text-mist">Phase 1 Acceptance</h3>
            <div class="mt-4 space-y-3 text-sm leading-6 text-slate-300">
              <p>Recipe discovery is backed by the internal SQLite database.</p>
              <p>The test recipe emits 10 timed log messages and a completion event.</p>
              <p>Real-time events flow through the shared <code>atlas-weave:event</code> channel.</p>
            </div>
          </div>
        </div>
      </div>
    </section>
  </div>
</div>

<style>
  .selected {
    border-color: rgba(45, 212, 191, 0.85);
    background: rgba(13, 148, 136, 0.18);
  }
</style>
