<script lang="ts">
	import type { HTMLAttributes } from 'svelte/elements';
	import { cn } from '$lib/utils';

	let {
		class: className,
		children,
		...restProps
	}: HTMLAttributes<HTMLHeadingElement> & { children?: import('svelte').Snippet } = $props();
</script>

<h3 class={cn('text-sm font-medium uppercase tracking-widest text-muted-foreground', className)} {...restProps}>
	{#if children}{@render children()}{/if}
</h3>
