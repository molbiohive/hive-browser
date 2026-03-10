<script>
	import DataTable from '$lib/DataTable.svelte';
	import CopyableSequence from '$lib/CopyableSequence.svelte';
	import { mapToParts, mapToCutSites } from '$lib/hatchlings.ts';
	import { PlasmidViewer, Tooltip } from '@molbiohive/hatchlings';

	let { data } = $props();

	const featureColumns = [
		{ key: 'pid', label: 'PID' },
		{ key: 'name', label: 'Name' },
		{ key: 'type', label: 'Type' },
		{ key: 'location', label: 'Location', format: (row) => `${row.start}..${row.end}` },
		{ key: 'strand', label: 'Strand', format: (row) => row.strand > 0 ? '+' : '\u2212' },
	];

	const primerColumns = [
		{ key: 'pid', label: 'PID' },
		{ key: 'name', label: 'Name' },
		{ key: 'length', label: 'Length', format: (row) => row.length ? `${row.length} bp` : '' },
	];

	const seqPreview = $derived.by(() => {
		const s = data?.sequence?.sequence_data;
		if (!s) return '';
		return s.length > 100 ? s.slice(0, 100) + '\u2026' : s;
	});

	const parts = $derived(mapToParts(data?.features, data?.primers));
	const cutSites = $derived(mapToCutSites(data?.cut_sites));
	const showPlasmid = $derived(data?.sequence?.size_bp > 0);

	let hover = $state(null);
</script>

{#if data?.sequence}
<div class="profile-layout">
	<div class="profile-left">
		<div class="field"><strong>SID:</strong> {data.sequence.sid}</div>
		<div class="field"><strong>Name:</strong> {data.sequence.name}</div>
		<div class="field"><strong>Size:</strong> {data.sequence.size_bp} bp</div>
		<div class="field"><strong>Topology:</strong> {data.sequence.topology}</div>
		{#if data.sequence.molecule}
		<div class="field"><strong>Molecule:</strong> {data.sequence.molecule}</div>
		{/if}

		{#if data.sequence.description}
		<div class="field"><strong>Description:</strong> {data.sequence.description}</div>
		{/if}

		{#if data.sequence.sequence_data}
		<h4>Sequence</h4>
		<CopyableSequence
			sequence={data.sequence.sequence_data}
			display={seqPreview}
			label="{data.sequence.size_bp} bp -- click to copy"
		/>
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

	{#if showPlasmid}
	<div class="profile-right">
		<PlasmidViewer
			name={data.sequence.name}
			size={data.sequence.size_bp}
			{parts}
			{cutSites}
			topology={data.sequence.topology || 'circular'}
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
{:else}
<p class="empty">Sequence not found</p>
{/if}

<style>
	.profile-layout {
		display: flex;
		gap: 1rem;
		font-size: 0.85rem;
	}
	.profile-left {
		flex: 1;
		min-width: 0;
	}
	.profile-right {
		flex: 0 0 280px;
		position: relative;
	}
	.field { margin-bottom: 0.3rem; }
	h4 { margin: 0.75rem 0 0.3rem; font-size: 0.85rem; color: var(--text-muted); }
	:global(.mono) { font-family: 'SF Mono', Monaco, monospace; font-size: 0.78rem; }
	.empty { color: var(--text-placeholder); font-size: 0.85rem; }

	@media (max-width: 640px) {
		.profile-layout { flex-direction: column; }
		.profile-right { flex: none; }
	}
</style>
