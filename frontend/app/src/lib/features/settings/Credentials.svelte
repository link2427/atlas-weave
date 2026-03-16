<script lang="ts">
  import { createEventDispatcher } from 'svelte';

  import type { CredentialEntry } from '$lib/features/settings/types';

  export let entries: CredentialEntry[] = [];
  export let saving = false;

  const dispatch = createEventDispatcher<{
    save: { key: string; value: string };
    remove: { key: string };
  }>();

  let drafts: Record<string, string> = {};

  function saveKey(key: string): void {
    const value = drafts[key]?.trim();
    if (!value) {
      return;
    }
    dispatch('save', { key, value });
    drafts[key] = '';
  }
</script>

<section class="panel">
  <div class="mb-6">
    <p class="eyebrow">Settings</p>
    <h1 class="mt-2 text-3xl font-semibold text-mist">Credentials</h1>
    <p class="mt-3 text-sm leading-6 text-slate-300">
      Secrets are stored in the desktop secure store and injected into Python as environment variables at run start.
    </p>
  </div>

  {#if entries.length === 0}
    <div class="empty-state">No secret fields are defined by the installed recipes.</div>
  {:else}
    <div class="space-y-4">
      {#each entries as entry}
        <div class="entry">
          <div class="flex items-start justify-between gap-4">
            <div>
              <div class="flex items-center gap-3">
                <h2 class="text-lg font-semibold text-mist">{entry.key}</h2>
                <span class:present={entry.present} class="status-pill">
                  {entry.present ? 'Saved' : 'Missing'}
                </span>
              </div>
              <p class="mt-2 text-sm leading-6 text-slate-300">{entry.description}</p>
              <p class="mt-2 text-xs uppercase tracking-[0.18em] text-slate-500">
                Used by {entry.recipes.join(', ')}
              </p>
            </div>
          </div>

          <div class="mt-4 grid gap-3 md:grid-cols-[1fr,auto,auto]">
            <input
              bind:value={drafts[entry.key]}
              type="password"
              placeholder={entry.present ? 'Replace saved credential' : 'Enter credential value'}
            />
            <button class="save-button" disabled={saving} on:click={() => saveKey(entry.key)}>
              Save
            </button>
            <button
              class="delete-button"
              disabled={saving || !entry.present}
              on:click={() => dispatch('remove', { key: entry.key })}
            >
              Delete
            </button>
          </div>
        </div>
      {/each}
    </div>
  {/if}
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

  .empty-state,
  .entry {
    border-radius: 1.5rem;
    border: 1px solid rgba(255, 255, 255, 0.08);
    background: rgba(2, 6, 23, 0.4);
    padding: 1rem 1.1rem;
  }

  .status-pill {
    border-radius: 9999px;
    background: rgba(251, 191, 36, 0.16);
    padding: 0.25rem 0.65rem;
    font-size: 0.72rem;
    letter-spacing: 0.18em;
    text-transform: uppercase;
    color: #fde68a;
  }

  .status-pill.present {
    background: rgba(45, 212, 191, 0.16);
    color: #99f6e4;
  }

  input {
    width: 100%;
    border-radius: 1rem;
    border: 1px solid rgba(255, 255, 255, 0.08);
    background: rgba(15, 23, 42, 0.92);
    padding: 0.85rem 0.95rem;
    color: #f8fafc;
  }

  .save-button,
  .delete-button {
    border-radius: 9999px;
    padding: 0.8rem 1rem;
    font-weight: 600;
  }

  .save-button {
    background: #2dd4bf;
    color: #082f49;
  }

  .delete-button {
    border: 1px solid rgba(251, 113, 133, 0.32);
    background: rgba(127, 29, 29, 0.28);
    color: #fecdd3;
  }
</style>
