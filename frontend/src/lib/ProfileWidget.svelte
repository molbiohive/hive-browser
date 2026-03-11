<script>
	import DataTable from '$lib/DataTable.svelte';
	import TabBar from '$lib/TabBar.svelte';
	import CopyableSequence from '$lib/CopyableSequence.svelte';

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

	const cutSiteColumns = [
		{ key: 'enzyme', label: 'Enzyme' },
		{ key: 'num_cuts', label: 'Cuts' },
		{ key: 'position', label: 'Positions' },
		{ key: 'overhang', label: 'Overhang' },
	];

	const seqPreview = $derived.by(() => {
		const s = data?.sequence?.sequence_data;
		if (!s) return '';
		return s.length > 100 ? s.slice(0, 100) + '\u2026' : s;
	});

	const uniqueCutSites = $derived.by(() => {
		const sites = data?.cut_sites;
		if (!sites) return [];
		const byEnzyme = {};
		for (const cs of sites) {
			if (!byEnzyme[cs.enzyme]) {
				byEnzyme[cs.enzyme] = { enzyme: cs.enzyme, positions: [], overhang: cs.overhang };
			}
			byEnzyme[cs.enzyme].positions.push(cs.position);
		}
		return Object.values(byEnzyme).map(e => ({
			enzyme: e.enzyme,
			num_cuts: e.positions.length,
			position: e.positions.sort((a, b) => a - b).join(', '),
			overhang: e.overhang,
		}));
	});

	const tabs = $derived.by(() => {
		const t = [];
		if (data?.features?.length) t.push({ id: 'features', label: `Features (${data.features.length})` });
		if (data?.primers?.length) t.push({ id: 'primers', label: `Primers (${data.primers.length})` });
		if (uniqueCutSites.length) t.push({ id: 'sites', label: `Sites (${uniqueCutSites.length})` });
		return t;
	});
	let activeTab = $state('features');
	$effect(() => {
		if (tabs.length && !tabs.find(t => t.id === activeTab)) {
			activeTab = tabs[0].id;
		}
	});
</script>

{#if data?.error}
<p class="error">{data.error}</p>
{:else if data?.sequence}
<div class="profile">
	<!-- Metadata header -->
	<div class="meta">
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
	</div>

	<!-- Copyable sequence -->
	{#if data.sequence.sequence_data}
	<h4>Sequence</h4>
	<CopyableSequence
		sequence={data.sequence.sequence_data}
		display={seqPreview}
		label="{data.sequence.size_bp} bp -- click to copy"
	/>
	{/if}

	<!-- Tabbed tables -->
	{#if tabs.length}
	<TabBar {tabs} active={activeTab} onchange={(id) => activeTab = id} />
	<div class="tab-content">
		{#if activeTab === 'features' && data.features?.length}
			<DataTable rows={data.features} columns={featureColumns} defaultPageSize={10} />
		{:else if activeTab === 'primers' && data.primers?.length}
			<DataTable rows={data.primers} columns={primerColumns} defaultPageSize={10} />
		{:else if activeTab === 'sites' && uniqueCutSites.length}
			<DataTable rows={uniqueCutSites} columns={cutSiteColumns} defaultPageSize={10} />
		{/if}
	</div>
	{/if}
</div>
{:else}
<p class="empty">Sequence not found</p>
{/if}

<style>
	.profile { font-size: 0.85rem; }
	.meta { margin-bottom: 0.5rem; }
	.field { margin-bottom: 0.3rem; }
	h4 { margin: 0.75rem 0 0.3rem; font-size: 0.85rem; color: var(--text-muted); }
	.error { color: var(--color-err); font-size: 0.85rem; }
	.empty { color: var(--text-placeholder); font-size: 0.85rem; }
	.tab-content { margin-top: 0.25rem; }
</style>
