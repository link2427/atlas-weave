<script lang="ts">
	import type { HTMLAttributes } from 'svelte/elements';
	import { cn } from '$lib/utils';

	let {
		class: className,
		orientation = 'horizontal',
		...restProps
	}: HTMLAttributes<HTMLDivElement> & {
		orientation?: 'horizontal' | 'vertical';
	} = $props();
</script>

<div
	class={cn(
		'shrink-0 bg-white/8',
		orientation === 'horizontal' ? 'h-px w-full' : 'h-full w-px',
		className
	)}
	role="separator"
	aria-orientation={orientation}
	{...restProps}
></div>
