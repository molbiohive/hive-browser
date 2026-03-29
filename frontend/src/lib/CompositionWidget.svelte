<script>
	import { CompositionChart } from '@molbiohive/hatchlings';

	let { data } = $props();
	let containerEl = $state(undefined);
	let containerWidth = $state(400);

	const compositionData = $derived.by(() => {
		if (!data) return null;
		const counts = {};
		for (const base of ['A', 'T', 'G', 'C', 'U']) {
			const key = base.toLowerCase();
			if (data[key] != null) counts[base] = data[key];
		}
		if (!Object.keys(counts).length) return null;
		const gc = data.gc_percent != null ? data.gc_percent / 100 : undefined;
		const alphabet = counts.U != null ? 'rna' : 'dna';
		return { counts, gc, alphabet, length: data.length, name: data.name };
	});

	$effect(() => {
		if (!containerEl) return;
		const ro = new ResizeObserver(([e]) => {
			containerWidth = e.contentRect.width;
		});
		ro.observe(containerEl);
		return () => ro.disconnect();
	});
</script>

{#if data?.error}
<p class="error">{data.error}</p>
{:else if compositionData}
<div class="comp-widget" bind:this={containerEl}>
	<div class="meta">
		{#if data.gc_percent != null}
			<span><strong>GC:</strong> {data.gc_percent.toFixed(1)}%</span>
		{/if}
		{#if data.length}
			<span><strong>Length:</strong> {data.length.toLocaleString()} bp</span>
		{/if}
	</div>
	<CompositionChart data={compositionData}
		width={Math.max(300, containerWidth - 2)}
		height={200} />
</div>
{:else}
<p class="empty">No composition data</p>
{/if}

<style>
	.comp-widget { font-size: 0.85rem; }
	.meta {
		display: flex;
		flex-wrap: wrap;
		gap: 0.5rem 1rem;
		margin-bottom: 0.5rem;
		font-size: 0.8rem;
		color: var(--text-secondary);
	}
	.error { color: var(--color-err); font-size: 0.85rem; }
	.empty { color: var(--text-placeholder); font-size: 0.85rem; }
</style>
