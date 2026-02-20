<script>
	import DataTable from '$lib/DataTable.svelte';

	let { data } = $props();

	const featureColumns = [
		{ key: 'name', label: 'Name' },
		{ key: 'type', label: 'Type' },
		{ key: 'location', label: 'Location', format: (row) => `${row.start}..${row.end}` },
		{ key: 'strand', label: 'Strand', format: (row) => row.strand > 0 ? '+' : '\u2212' },
	];

	const primerColumns = [
		{ key: 'name', label: 'Name' },
		{ key: 'sequence', label: 'Sequence', class: 'mono' },
		{ key: 'tm', label: 'Tm', format: (row) => row.tm ? row.tm.toFixed(1) + '\u00B0C' : '\u2014' },
	];
</script>

{#if data?.sequence}
<div class="profile">
	<div class="field"><strong>Name:</strong> {data.sequence.name}</div>
	<div class="field"><strong>Size:</strong> {data.sequence.size_bp} bp</div>
	<div class="field"><strong>Topology:</strong> {data.sequence.topology}</div>

	{#if data.sequence.description}
	<div class="field"><strong>Description:</strong> {data.sequence.description}</div>
	{/if}

	{#if data.features?.length}
	<h4>Features</h4>
	<DataTable rows={data.features} columns={featureColumns} defaultPageSize={10} />
	{/if}

	{#if data.primers?.length}
	<h4>Primers</h4>
	<DataTable rows={data.primers} columns={primerColumns} defaultPageSize={10} />
	{/if}
</div>
{:else}
<p class="empty">Sequence not found</p>
{/if}

<style>
	.profile { font-size: 0.85rem; }
	.field { margin-bottom: 0.3rem; }
	h4 { margin: 0.75rem 0 0.3rem; font-size: 0.85rem; color: var(--text-muted); }
	:global(.mono) { font-family: 'SF Mono', Monaco, monospace; font-size: 0.78rem; }
	.empty { color: var(--text-placeholder); font-size: 0.85rem; }
</style>
