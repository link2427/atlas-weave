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
	class={cn('rounded-xl border border-white/8 bg-white/[0.04] shadow-sm', className)}
	{...restProps}
>
	{#if children}{@render children()}{/if}
</div>
