<script>
	import DataTable from '$lib/DataTable.svelte';
	import { GelViewer, Tooltip } from '@molbiohive/hatchlings';

	let { data } = $props();

	const columns = [
		{ key: 'name', label: 'Reaction' },
		{ key: 'total_cuts', label: 'Cuts' },
		{ key: 'fragments', label: 'Fragments', format: (row) => {
			const frags = row.fragments || [];
			return frags.map(f => f >= 1000 ? `${(f / 1000).toFixed(1)}kb` : `${f}bp`).join(', ');
		}},
	];

	const reactionRows = $derived(data?.reactions || []);

	let hover = $state(null);
</script>

{#if data?.error}
<p class="error">{data.error}</p>
{:else if data}
<div class="digest-layout">
	<div class="digest-left">
		<div class="summary">
			<span><strong>Length:</strong> {data.sequence_length} bp</span>
			<span><strong>Topology:</strong> {data.circular ? 'circular' : 'linear'}</span>
		</div>

		{#if reactionRows.length}
		<DataTable rows={reactionRows} columns={columns} defaultPageSize={10} />
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
	.error { color: var(--color-err); font-size: 0.85rem; }
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

	@media (max-width: 640px) {
		.digest-layout { flex-direction: column; }
		.digest-right { flex: none; }
	}
</style>
