<script lang="ts">
	import type { HTMLButtonAttributes } from 'svelte/elements';
	import { cn } from '$lib/utils';
	import { getContext } from 'svelte';

	let {
		class: className,
		value,
		children,
		...restProps
	}: HTMLButtonAttributes & {
		value: string;
		children?: import('svelte').Snippet;
	} = $props();

	const tabs: { current: string; select: (id: string) => void } = getContext('tabs');
	let active = $derived(tabs.current === value);
</script>

<button
	class={cn(
		'inline-flex items-center justify-center whitespace-nowrap rounded-md px-3 py-1.5 text-sm font-medium transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
		active
			? 'bg-white/10 text-foreground shadow-sm'
			: 'text-muted-foreground hover:bg-white/5 hover:text-foreground',
		className
	)}
	role="tab"
	aria-selected={active}
	onclick={() => tabs.select(value)}
	{...restProps}
>
	{#if children}{@render children()}{/if}
</button>
