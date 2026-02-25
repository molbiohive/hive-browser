<script>
	import CopyableSequence from '$lib/CopyableSequence.svelte';

	let { data } = $props();

	const strandLabel = $derived(
		data?.strand === -1 ? '\u2212' : data?.strand === 1 ? '+' : ''
	);
</script>

{#if data?.error}
<p class="error">{data.error}</p>
{:else if data?.sequence}
<div class="extract">
	<div class="meta">
		{#if data.source}<span><strong>Source:</strong> {data.source}</span>{/if}
		{#if data.name && data.name !== data.source}<span><strong>Name:</strong> {data.name}</span>{/if}
		{#if data.start != null}<span><strong>Region:</strong> {data.start}..{data.end} {strandLabel}</span>{/if}
		<span><strong>Length:</strong> {data.length} bp</span>
	</div>
	<CopyableSequence sequence={data.sequence} label="{data.length} bp -- click to copy" />
</div>
{:else}
<p class="empty">No sequence extracted</p>
{/if}

<style>
	.extract { font-size: 0.85rem; }
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
