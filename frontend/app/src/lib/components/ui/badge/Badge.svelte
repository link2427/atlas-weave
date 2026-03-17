<script lang="ts">
	import type { HTMLAttributes } from 'svelte/elements';
	import { cn } from '$lib/utils';
	import { badgeVariants, type BadgeVariant } from './index';

	let {
		class: className,
		variant = 'default' as BadgeVariant,
		children,
		...restProps
	}: HTMLAttributes<HTMLDivElement> & {
		variant?: BadgeVariant;
		children?: import('svelte').Snippet;
	} = $props();
</script>

<div class={cn(badgeVariants({ variant }), className)} {...restProps}>
	{#if children}{@render children()}{/if}
</div>
