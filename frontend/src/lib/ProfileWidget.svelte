<script>
	import DataTable from '$lib/DataTable.svelte';
	import TabBar from '$lib/TabBar.svelte';
	import CopyableSequence from '$lib/CopyableSequence.svelte';
	import { mapToParts, mapToCutSites } from '$lib/hatchlings.ts';
	import { PlasmidViewer, Tooltip } from '@molbiohive/hatchlings';

	let { data } = $props();

	const MAX_CUTSITES = 50;

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

	const parts = $derived(mapToParts(data?.features, data?.primers));

	// Deduplicate cut sites by enzyme for the table
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

	// Cap displayed cut sites on the plasmid map (unique cutters first)
	const cappedCutSites = $derived.by(() => {
		const sites = data?.cut_sites;
		if (!sites || sites.length <= MAX_CUTSITES) return mapToCutSites(sites);
		const byEnzyme = {};
		for (const cs of sites) {
			if (!byEnzyme[cs.enzyme]) byEnzyme[cs.enzyme] = [];
			byEnzyme[cs.enzyme].push(cs);
		}
		const sorted = Object.values(byEnzyme).sort((a, b) => a.length - b.length);
		const result = [];
		for (const group of sorted) {
			if (result.length + group.length > MAX_CUTSITES) break;
			result.push(...group);
		}
		return mapToCutSites(result);
	});

	const showPlasmid = $derived(data?.sequence?.size_bp > 0);

	// Tab state
	const tabs = $derived.by(() => {
		const t = [];
		if (data?.features?.length) t.push({ id: 'features', label: `Features (${data.features.length})` });
		if (data?.primers?.length) t.push({ id: 'primers', label: `Primers (${data.primers.length})` });
		if (uniqueCutSites.length) t.push({ id: 'sites', label: `Sites (${uniqueCutSites.length})` });
		return t;
	});
	let activeTab = $state('features');
	// Reset to first available tab when data changes
	$effect(() => {
		if (tabs.length && !tabs.find(t => t.id === activeTab)) {
			activeTab = tabs[0].id;
		}
	});

	let hover = $state(null);
</script>

{#if data?.sequence}
<div class="profile">
	<!-- Top row: metadata left, plasmid right -->
	<div class="top-row">
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

		{#if showPlasmid}
		<div class="plasmid-col">
			<PlasmidViewer
				name={data.sequence.name}
				size={data.sequence.size_bp}
				{parts}
				cutSites={cappedCutSites}
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
			{#if data.cut_sites?.length > MAX_CUTSITES}
			<p class="cap-note">Showing {cappedCutSites.length} of {data.cut_sites.length} cut sites</p>
			{/if}
		</div>
		{/if}
	</div>

	<!-- Full-width sections below -->
	{#if data.sequence.sequence_data}
	<h4>Sequence</h4>
	<CopyableSequence
		sequence={data.sequence.sequence_data}
		display={seqPreview}
		label="{data.sequence.size_bp} bp -- click to copy"
	/>
	{/if}

	<!-- Tabbed table section -->
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
	.top-row {
		display: flex;
		gap: 1rem;
	}
	.meta {
		flex: 1;
		min-width: 0;
	}
	.plasmid-col {
		flex: 0 0 280px;
		position: relative;
	}
	.field { margin-bottom: 0.3rem; }
	h4 { margin: 0.75rem 0 0.3rem; font-size: 0.85rem; color: var(--text-muted); }
	:global(.mono) { font-family: 'SF Mono', Monaco, monospace; font-size: 0.78rem; }
	.empty { color: var(--text-placeholder); font-size: 0.85rem; }
	.cap-note { font-size: 0.72rem; color: var(--text-faint); margin: 0.2rem 0 0; text-align: center; }

	.tab-content { margin-top: 0.25rem; }

	@media (max-width: 640px) {
		.top-row { flex-direction: column; }
		.plasmid-col { flex: none; }
	}
</style>
