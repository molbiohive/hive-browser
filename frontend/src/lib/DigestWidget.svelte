<script>
	import DataTable from '$lib/DataTable.svelte';
	import { GelViewer, Tooltip } from '@molbiohive/hatchlings';

	let { data } = $props();

	const columns = [
		{ key: 'name', label: 'Enzyme' },
		{ key: 'num_cuts', label: 'Cuts' },
		{ key: 'sites', label: 'Sites', format: (row) => row.sites?.join(', ') || '' },
		{ key: 'fragments', label: 'Fragments', format: (row) => {
			const frags = row.fragments || [];
			return frags.map(f => f >= 1000 ? `${(f / 1000).toFixed(1)}kb` : `${f}bp`).join(', ');
		}},
	];

	// Merge fragment sizes into enzyme rows
	const enzymeRows = $derived.by(() => {
		if (!data?.enzymes) return [];
		const frags = data.fragments || [];
		return data.enzymes.map((e, i) => ({
			...e,
			// For single enzyme digests, all fragments belong to it
			fragments: data.enzymes.length === 1 ? frags : e.sites?.length ? frags : [],
		}));
	});

	let hover = $state(null);
</script>

{#if data}
<div class="digest-layout">
	<div class="digest-left">
		<div class="summary">
			<span><strong>Cuts:</strong> {data.total_cuts}</span>
			<span><strong>Fragments:</strong> {data.fragments?.length || 0}</span>
			<span><strong>Length:</strong> {data.sequence_length} bp</span>
			<span><strong>Topology:</strong> {data.circular ? 'circular' : 'linear'}</span>
		</div>

		{#if enzymeRows.length}
		<DataTable rows={enzymeRows} columns={columns} defaultPageSize={10} />
		{/if}

		{#if data.fragments?.length}
		<div class="frag-summary">
			{#each data.fragments as f, i}
				<span class="frag">{f >= 1000 ? `${(f / 1000).toFixed(1)} kb` : `${f} bp`}</span>
				{#if i < data.fragments.length - 1}<span class="frag-sep">+</span>{/if}
			{/each}
		</div>
		{/if}
	</div>

	{#if data.gel_data}
	<div class="digest-right">
		<GelViewer
			lanes={data.gel_data.lanes}
			gelType={data.gel_data.gelType}
			stain={data.gel_data.stain}
			showSizeLabels={false}
			onhoverinfo={(info) => { hover = info; }}
		/>
		<Tooltip
			visible={hover != null}
			x={hover?.position?.x}
			y={hover?.position?.y}
			title={hover?.title}
			items={hover?.items}
		/>
	</div>
	{/if}
</div>
{/if}

<style>
	.digest-layout {
		display: flex;
		gap: 1rem;
		font-size: 0.85rem;
	}
	.digest-left {
		flex: 1;
		min-width: 0;
	}
	.digest-right {
		flex: 0 0 240px;
		position: relative;
	}
	.summary {
		display: flex;
		flex-wrap: wrap;
		gap: 0.5rem 1rem;
		margin-bottom: 0.5rem;
		font-size: 0.82rem;
	}
	.frag-summary {
		margin-top: 0.5rem;
		font-size: 0.78rem;
		color: var(--text-muted);
		display: flex;
		flex-wrap: wrap;
		gap: 0.15rem;
		align-items: center;
	}
	.frag {
		font-family: 'SF Mono', Monaco, monospace;
		font-size: 0.75rem;
	}
	.frag-sep {
		color: var(--text-faint);
		font-size: 0.7rem;
	}

	@media (max-width: 640px) {
		.digest-layout { flex-direction: column; }
		.digest-right { flex: none; }
	}
</style>
