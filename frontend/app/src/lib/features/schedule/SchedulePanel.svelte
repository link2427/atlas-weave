<script lang="ts">
  import { onMount } from 'svelte';
  import cronstrue from 'cronstrue';

  import { Button } from '$lib/components/ui/button';
  import { Badge } from '$lib/components/ui/badge';
  import {
    getSchedules,
    createSchedule,
    updateSchedule,
    deleteSchedule,
    type Schedule,
  } from '$lib/api/tauri/schedules';

  export let recipeName: string;

  let schedule: Schedule | null = null;
  let loading = true;
  let saving = false;
  let errorMessage = '';

  // Form state
  let showForm = false;
  let cronInput = '0 * * * *';
  let editingCron = false;
  let editCronInput = '';

  $: cronDescription = describeCron(cronInput);
  $: editCronDescription = describeCron(editCronInput);

  $: if (recipeName) {
    void loadSchedule();
  }

  onMount(() => {
    void loadSchedule();
  });

  function describeCron(expression: string): string {
    try {
      return cronstrue.toString(expression, { use24HourTimeFormat: true });
    } catch {
      return 'Invalid expression';
    }
  }

  function formatNextRun(iso: string | null): string {
    if (!iso) return 'Not scheduled';
    try {
      return new Date(iso).toLocaleString();
    } catch {
      return iso;
    }
  }

  async function loadSchedule(): Promise<void> {
    loading = true;
    errorMessage = '';
    try {
      const schedules = await getSchedules(recipeName);
      schedule = schedules[0] ?? null;
      showForm = false;
      editingCron = false;
    } catch (error) {
      errorMessage = error instanceof Error ? error.message : 'Failed to load schedule.';
    } finally {
      loading = false;
    }
  }

  async function handleCreate(): Promise<void> {
    saving = true;
    errorMessage = '';
    try {
      schedule = await createSchedule(recipeName, cronInput);
      showForm = false;
    } catch (error) {
      errorMessage = error instanceof Error ? error.message : 'Failed to create schedule.';
    } finally {
      saving = false;
    }
  }

  async function handleToggle(): Promise<void> {
    if (!schedule) return;
    errorMessage = '';
    try {
      schedule = await updateSchedule(schedule.id, undefined, undefined, !schedule.enabled);
    } catch (error) {
      errorMessage = error instanceof Error ? error.message : 'Failed to update schedule.';
    }
  }

  async function handleSaveCron(): Promise<void> {
    if (!schedule) return;
    saving = true;
    errorMessage = '';
    try {
      schedule = await updateSchedule(schedule.id, editCronInput);
      editingCron = false;
    } catch (error) {
      errorMessage = error instanceof Error ? error.message : 'Invalid cron expression.';
    } finally {
      saving = false;
    }
  }

  async function handleDelete(): Promise<void> {
    if (!schedule) return;
    errorMessage = '';
    try {
      await deleteSchedule(schedule.id);
      schedule = null;
    } catch (error) {
      errorMessage = error instanceof Error ? error.message : 'Failed to delete schedule.';
    }
  }

  function startEditCron(): void {
    if (!schedule) return;
    editCronInput = schedule.cronExpression;
    editingCron = true;
  }
</script>

<section class="rounded-xl border border-white/8 bg-white/[0.04] p-6">
  <div class="mb-4">
    <p class="text-xs font-medium uppercase tracking-widest text-muted-foreground">Schedule</p>
    <p class="mt-2 text-sm text-muted-foreground">
      Automatically run this recipe on a cron interval.
    </p>
  </div>

  {#if loading}
    <div class="h-10 animate-pulse rounded-lg bg-white/5"></div>
  {:else if !schedule && !showForm}
    <Button variant="outline" onclick={() => { showForm = true; }}>
      Create Schedule
    </Button>
  {:else if showForm && !schedule}
    <div class="space-y-4">
      <div>
        <label class="mb-1 block text-sm font-medium text-slate-200" for="cron-input">
          Cron Expression (UTC)
        </label>
        <input
          id="cron-input"
          type="text"
          bind:value={cronInput}
          placeholder="*/5 * * * *"
          class="w-full rounded-lg border border-white/8 bg-slate-900/90 px-3 py-2 text-sm text-slate-50 focus:outline-none focus:ring-2 focus:ring-ring"
        />
        <p class="mt-1 text-xs text-muted-foreground">{cronDescription}</p>
      </div>
      <div class="flex gap-2">
        <Button disabled={saving} onclick={handleCreate}>
          {saving ? 'Creating...' : 'Create'}
        </Button>
        <Button variant="outline" onclick={() => { showForm = false; }}>
          Cancel
        </Button>
      </div>
    </div>
  {:else if schedule}
    <div class="space-y-4">
      <div class="flex flex-wrap items-center gap-3">
        <Badge variant={schedule.enabled ? 'completed' : 'cancelled'}>
          {schedule.enabled ? 'Enabled' : 'Disabled'}
        </Badge>

        <button
          class="text-sm text-sky-300 underline hover:text-sky-200"
          on:click={handleToggle}
        >
          {schedule.enabled ? 'Disable' : 'Enable'}
        </button>
      </div>

      <div class="rounded-lg border border-white/8 bg-black/20 p-4">
        {#if editingCron}
          <div class="space-y-2">
            <input
              type="text"
              bind:value={editCronInput}
              class="w-full rounded-lg border border-white/8 bg-slate-900/90 px-3 py-2 text-sm text-slate-50 focus:outline-none focus:ring-2 focus:ring-ring"
            />
            <p class="text-xs text-muted-foreground">{editCronDescription}</p>
            <div class="flex gap-2">
              <Button size="sm" disabled={saving} onclick={handleSaveCron}>
                {saving ? 'Saving...' : 'Save'}
              </Button>
              <Button size="sm" variant="outline" onclick={() => { editingCron = false; }}>
                Cancel
              </Button>
            </div>
          </div>
        {:else}
          <div class="flex items-start justify-between gap-3">
            <div>
              <p class="text-sm font-medium text-slate-50">
                <code class="rounded bg-white/5 px-1.5 py-0.5">{schedule.cronExpression}</code>
              </p>
              <p class="mt-1 text-sm text-muted-foreground">
                {describeCron(schedule.cronExpression)}
              </p>
            </div>
            <button
              class="text-xs text-sky-300 underline hover:text-sky-200"
              on:click={startEditCron}
            >
              Edit
            </button>
          </div>
        {/if}
      </div>

      <div class="grid gap-3 text-sm sm:grid-cols-2">
        <div>
          <p class="text-xs text-muted-foreground">Next Run</p>
          <p class="mt-0.5 text-slate-200">{formatNextRun(schedule.nextRunAt)}</p>
        </div>
        <div>
          <p class="text-xs text-muted-foreground">Last Run</p>
          {#if schedule.lastRunId}
            <a
              href="/run/{schedule.lastRunId}"
              class="mt-0.5 inline-block text-sky-300 underline hover:text-sky-200"
            >
              {schedule.lastRunId.slice(0, 8)}...
            </a>
          {:else}
            <p class="mt-0.5 text-slate-200">None</p>
          {/if}
        </div>
      </div>

      <Button variant="outline" size="sm" onclick={handleDelete}>
        Delete Schedule
      </Button>
    </div>
  {/if}

  {#if errorMessage}
    <div class="mt-3 rounded-lg border border-rose-400/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-200">
      {errorMessage}
    </div>
  {/if}
</section>
