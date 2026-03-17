<script lang="ts">
	let {
		text = '',
		children,
	}: {
		text?: string;
		children?: import('svelte').Snippet;
	} = $props();

	let visible = $state(false);
	let x = $state(0);
	let y = $state(0);

	function handleEnter(event: MouseEvent) {
		x = event.clientX;
		y = event.clientY;
		visible = true;
	}

	function handleMove(event: MouseEvent) {
		x = event.clientX;
		y = event.clientY;
	}

	function handleLeave() {
		visible = false;
	}
</script>

<!-- svelte-ignore a11y_no_static_element_interactions -->
<span
	class="inline-flex"
	onmouseenter={handleEnter}
	onmousemove={handleMove}
	onmouseleave={handleLeave}
>
	{#if children}{@render children()}{/if}
</span>

{#if visible && text}
	<div
		class="pointer-events-none fixed z-50 max-w-xs rounded-lg border border-white/10 bg-[#0c1628] px-3 py-1.5 text-xs text-slate-200 shadow-lg"
		style="left: {x + 12}px; top: {y - 8}px;"
	>
		{text}
	</div>
{/if}
