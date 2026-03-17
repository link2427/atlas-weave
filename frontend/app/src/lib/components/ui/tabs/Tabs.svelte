<script lang="ts">
	import type { HTMLAttributes } from 'svelte/elements';
	import { cn } from '$lib/utils';
	import { setContext } from 'svelte';

	let {
		class: className,
		value = $bindable(''),
		onValueChange,
		children,
		...restProps
	}: HTMLAttributes<HTMLDivElement> & {
		value?: string;
		onValueChange?: (value: string) => void;
		children?: import('svelte').Snippet;
	} = $props();

	let current = $state(value);

	$effect(() => {
		current = value;
	});

	setContext('tabs', {
		get current() { return current; },
		select(id: string) {
			current = id;
			value = id;
			onValueChange?.(id);
		}
	});
</script>

<div class={cn('', className)} {...restProps}>
	{#if children}{@render children()}{/if}
</div>
