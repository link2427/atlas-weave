<script lang="ts">
  import type { DagLayoutEdge } from '$lib/features/dag/dag-layout';

  export let edge: DagLayoutEdge;

  const strokeByState = {
    idle: 'rgba(148, 163, 184, 0.28)',
    active: 'rgba(45, 212, 191, 0.6)',
    completed: 'rgba(56, 189, 248, 0.52)',
    failed: 'rgba(251, 113, 133, 0.58)',
    skipped: 'rgba(251, 191, 36, 0.35)',
    cancelled: 'rgba(251, 146, 60, 0.4)',
    flowing: 'rgba(56, 189, 248, 0.92)'
  } as const;

  const dashByState = {
    idle: '0',
    active: '10 8',
    completed: '0',
    failed: '12 10',
    skipped: '6 10',
    cancelled: '4 12',
    flowing: '0'
  } as const;
</script>

<g class="pointer-events-none">
  <path
    d={edge.path}
    fill="none"
    stroke={strokeByState[edge.state]}
    stroke-width={edge.pulsing ? 4 : 3}
    stroke-dasharray={dashByState[edge.state]}
    stroke-linecap="round"
  />

  {#if edge.pulsing}
    {#each [0, 0.22, 0.44] as begin}
      <circle r="4" fill="#7dd3fc">
        <animateMotion dur="1.1s" begin={`${begin}s`} path={edge.path} repeatCount="indefinite" />
      </circle>
    {/each}
  {/if}
</g>
