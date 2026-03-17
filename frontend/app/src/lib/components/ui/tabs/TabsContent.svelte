<script lang="ts">
	import type { HTMLAttributes } from 'svelte/elements';
	import { cn } from '$lib/utils';
	import { getContext } from 'svelte';

	let {
		class: className,
		value,
		children,
		...restProps
	}: HTMLAttributes<HTMLDivElement> & {
		value: string;
		children?: import('svelte').Snippet;
	} = $props();

	const tabs: { current: string } = getContext('tabs');
	let active = $derived(tabs.current === value);
</script>

{#if active}
	<div
		class={cn('mt-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring', className)}
		role="tabpanel"
		{...restProps}
	>
		{#if children}{@render children()}{/if}
	</div>
{/if}
