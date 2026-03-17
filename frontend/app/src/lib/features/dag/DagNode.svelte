<script lang="ts">
  import { createEventDispatcher } from 'svelte';

  import type { DagLayoutNode } from '$lib/features/dag/dag-layout';

  export let node: DagLayoutNode;
  export let selected = false;

  const dispatch = createEventDispatcher<{ select: { nodeId: string } }>();
  const radius = 36;
  const circumference = 2 * Math.PI * radius;

  $: progress = Math.max(0, Math.min(node.progress ?? 0, 1));
  $: progressOffset = circumference * (1 - progress);
  $: words = node.label.split(' ');
  $: tooltip = `${node.label}\nStatus: ${node.status}\nProgress: ${Math.round(progress * 100)}%${
    node.message ? `\n${node.message}` : ''
  }`;

  const fillByStatus = {
    pending: '#102238',
    running: '#0f3b39',
    completed: '#123f52',
    failed: '#4a1320',
    skipped: '#40321d',
    cancelled: '#4a2a11'
  } as const;

  const ringByStatus = {
    pending: 'rgba(148, 163, 184, 0.28)',
    running: '#2dd4bf',
    completed: '#38bdf8',
    failed: '#fb7185',
    skipped: '#fbbf24',
    cancelled: '#fb923c'
  } as const;

  function handleSelect(): void {
    dispatch('select', { nodeId: node.id });
  }
</script>

<g
  class:selected
  class:running={node.status === 'running'}
  class:failed={node.status === 'failed'}
  class:completed={node.status === 'completed'}
  class="dag-node cursor-pointer"
  style="will-change: transform;"
  transform={`translate(${node.centerX} ${node.centerY})`}
  role="button"
  tabindex="0"
  aria-label={`Select ${node.label}`}
  on:click={handleSelect}
  on:keydown={(event) => {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      handleSelect();
    }
  }}
>
  <title>{tooltip}</title>

  <circle r="44" fill="rgba(8, 15, 30, 0.72)" stroke="rgba(255, 255, 255, 0.06)" stroke-width="2" />
  <circle r="40" fill={fillByStatus[node.status]} stroke={selected ? '#7dd3fc' : 'rgba(255, 255, 255, 0.08)'} stroke-width={selected ? 3 : 2} />
  <circle r={radius} fill="none" stroke="rgba(255, 255, 255, 0.08)" stroke-width="6" />
  <circle
    class="progress-ring"
    r={radius}
    fill="none"
    stroke={ringByStatus[node.status]}
    stroke-width="6"
    stroke-dasharray={circumference}
    stroke-dashoffset={progressOffset}
    transform="rotate(-90)"
    stroke-linecap="round"
  />

  <text text-anchor="middle" fill="#eff6ff" class="pointer-events-none">
    {#each words.slice(0, 2) as word, index}
      <tspan x="0" dy={index === 0 ? '-0.15em' : '1.2em'} class="label-line">{word}</tspan>
    {/each}
  </text>

  <text y="29" text-anchor="middle" fill="rgba(226, 232, 240, 0.72)" class="pointer-events-none text-[9px] uppercase tracking-[0.18em]">
    {Math.round(progress * 100)}%
  </text>
</g>

<style>
  .dag-node {
    transition: opacity 160ms ease, filter 160ms ease;
  }

  .dag-node.running {
    filter: drop-shadow(0 0 14px rgba(45, 212, 191, 0.24));
  }

  .dag-node:hover,
  .dag-node.selected {
    opacity: 0.98;
    filter: drop-shadow(0 0 14px rgba(125, 211, 252, 0.18));
  }

  .dag-node.completed {
    animation: flash 520ms ease;
  }

  .dag-node.failed {
    animation: shake 420ms ease;
  }

  .progress-ring {
    transition: stroke-dashoffset 220ms ease, stroke 220ms ease;
  }

  .label-line {
    font-size: 11px;
    font-weight: 600;
  }

  @keyframes flash {
    0% {
      filter: brightness(1);
    }

    50% {
      filter: brightness(1.38);
    }

    100% {
      filter: brightness(1);
    }
  }

  @keyframes shake {
    0%,
    100% {
      transform: translateX(0);
    }

    25% {
      transform: translateX(-4px);
    }

    75% {
      transform: translateX(4px);
    }
  }
</style>
