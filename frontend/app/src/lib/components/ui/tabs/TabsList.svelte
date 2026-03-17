<script lang="ts">
	import type { HTMLAttributes } from 'svelte/elements';
	import { cn } from '$lib/utils';

	let {
		class: className,
		children,
		...restProps
	}: HTMLAttributes<HTMLDivElement> & { children?: import('svelte').Snippet } = $props();
</script>

<div
	class={cn(
		'inline-flex items-center gap-1 rounded-lg bg-white/5 p-1',
		className
	)}
	role="tablist"
	{...restProps}
>
	{#if children}{@render children()}{/if}
</div>
