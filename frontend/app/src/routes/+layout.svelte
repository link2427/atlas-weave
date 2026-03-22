<script lang="ts">
  import { onMount } from 'svelte';
  import '../app.css';
  import ThemeToggle from '$lib/components/ThemeToggle.svelte';
  import { theme } from '$lib/stores/theme';

  onMount(() => {
    theme.initialize();
  });
</script>

<div class="fixed right-4 top-4 z-50">
  <ThemeToggle />
</div>

<slot />
