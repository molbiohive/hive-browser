<script>
	import { mapToParts, mapToCutSites, mapToTranslations } from '$lib/hatchlings.ts';
	import { PlasmidViewer, SequenceViewer, ProteinSequenceViewer, Tooltip, SelectionState } from '@molbiohive/hatchlings';
	import DataTable from '$lib/DataTable.svelte';
	import TabBar from '$lib/TabBar.svelte';
	import CopyableSequence from '$lib/CopyableSequence.svelte';

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
		{ key: 'location', label: 'Location', format: (row) => `${row.start}..${row.end}` },
		{ key: 'strand', label: 'Strand', format: (row) => row.strand > 0 ? '+' : '\u2212' },
		{ key: 'length', label: 'Length', format: (row) => row.length ? `${row.length} bp` : '' },
		{ key: 'tm', label: 'Tm', format: (row) => row.tm != null ? `${row.tm.toFixed(1)}` : '' },
	];

	const cutSiteColumns = [
		{ key: 'enzyme', label: 'Enzyme' },
		{ key: 'num_cuts', label: 'Cuts' },
		{ key: 'position', label: 'Positions' },
		{ key: 'overhang', label: 'Overhang' },
	];

	const translationColumns = [
		{ key: 'name', label: 'Name' },
		{ key: 'location', label: 'Location', format: (row) => `${row.start}..${row.end}` },
		{ key: 'strand', label: 'Strand', format: (row) => row.strand > 0 ? '+' : '\u2212' },
		{ key: 'frame', label: 'Frame' },
		{ key: 'aa_len', label: 'AA' },
	];

	const infoColumns = [
		{ key: 'field', label: 'Field' },
		{ key: 'value', label: 'Value' },
	];

	const seq = $derived(data?.sequence);
	const seqData = $derived(seq?.sequence_data || '');
	const topology = $derived(seq?.topology || 'circular');
	const isProtein = $derived(
		seq?.molecule === 'protein' || seq?.molecule === 'AA'
	);

	const parts = $derived(mapToParts(data?.features, data?.primers));
	const translations = $derived(mapToTranslations(data?.translations));

	const translationRows = $derived.by(() => {
		if (!data?.translations || !data?.features) return [];
		return data.translations.map((t, i) => {
			const feat = data.features.find(f => f.start === t.start && f.end === t.end && f.strand === t.strand);
			return {
				name: feat?.name || `CDS ${i + 1}`,
				start: t.start,
				end: t.end,
				strand: t.strand,
				frame: t.frame,
				aa_len: t.aminoAcids?.length || 0,
			};
		});
	});

	const infoRows = $derived.by(() => {
		if (!seq) return [];
		const rows = [
			{ field: 'SID', value: seq.sid },
			{ field: 'Name', value: seq.name },
			{ field: 'Size', value: `${seq.size_bp?.toLocaleString()} bp` },
			{ field: 'Topology', value: topology },
		];
		if (seq.molecule) rows.push({ field: 'Molecule', value: seq.molecule });
		if (seq.description) rows.push({ field: 'Description', value: seq.description });
		if (data?.file?.path) rows.push({ field: 'File', value: data.file.path });
		if (data?.file?.format) rows.push({ field: 'Format', value: data.file.format });
		if (data?.file?.indexed_at) rows.push({ field: 'Indexed', value: data.file.indexed_at });
		return rows;
	});

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

	let selectionState = $state(null);
	let lastSize = $state(0);
	$effect(() => {
		const size = seq?.size_bp || 0;
		if (size > 0 && size !== lastSize) {
			lastSize = size;
			selectionState = new SelectionState(size);
		}
	});

	let hover = $state(null);
	let plasmidW = $state(0);
	let seqPanelW = $state(0);
	const seqHeight = $derived(Math.max(plasmidW, 500));

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
		const t = [{ id: 'info', label: 'Info' }];
		if (data?.features?.length) t.push({ id: 'features', label: `Features (${data.features.length})` });
		if (data?.primers?.length) t.push({ id: 'primers', label: `Primers (${data.primers.length})` });
		if (translationRows.length) t.push({ id: 'translations', label: `Translations (${translationRows.length})` });
		if (uniqueCutSites.length) t.push({ id: 'sites', label: `Sites (${uniqueCutSites.length})` });
		return t;
	});
	let activeTab = $state('info');
	$effect(() => {
		if (tabs.length && !tabs.find(t => t.id === activeTab)) {
			activeTab = tabs[0].id;
		}
	});

</script>

{#if data?.error}
<p class="error">{data.error}</p>
{:else if seq}
<div class="profile">
	{#if seqData}
	<div class="seq-oneline">
	<CopyableSequence sequence={seqData} label="{seq.size_bp?.toLocaleString()} bp — click to copy" />
	</div>
	{/if}

	<!-- Visual viewers -->
	{#if isProtein}
	<div class="panel-protein" bind:clientWidth={seqPanelW}>
		{#if seqPanelW > 0 && seqData}
		<ProteinSequenceViewer
			data={{ seq: seqData }}
			colorResidues={true}
			showNumbers={true}
			width={seqPanelW}
			height={Math.min(500, 80 + Math.ceil(seqData.length / 60) * 24)}
			onhoverinfo={(info) => { hover = info; }}
		/>
		{/if}
	</div>
	{:else}
	<div class="viewers">
		<div class="panel-plasmid" bind:clientWidth={plasmidW}>
			{#if plasmidW > 0}
			<PlasmidViewer
				data={{ name: seq.name, size: seq.size_bp, parts, cutSites: cappedCutSites, topology }}
				{selectionState}
				width={plasmidW}
				height={plasmidW}
				onhoverinfo={(info) => { hover = info; }}
			/>
			{/if}
		</div>

		{#if seqData}
		<div class="panel-sequence" bind:clientWidth={seqPanelW}>
			{#if seqPanelW > 0}
			<SequenceViewer
				data={{ seq: seqData, parts, cutSites: cappedCutSites, translations, topology }}
				{selectionState}
				width={seqPanelW}
				height={seqHeight}
				showComplement={true}
				showAnnotations={true}
				showTranslations={translations.length > 0}
				onhoverinfo={(info) => { hover = info; }}
			/>
			{/if}
		</div>
		{/if}
	</div>
	{/if}

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

	<!-- Tabbed tables -->
	{#if tabs.length}
	<TabBar {tabs} active={activeTab} onchange={(id) => activeTab = id} />
	<div class="tab-content">
		{#if activeTab === 'info'}
			<DataTable rows={infoRows} columns={infoColumns} defaultPageSize={20} />
		{:else if activeTab === 'features' && data.features?.length}
			<DataTable rows={data.features} columns={featureColumns} defaultPageSize={10} />
		{:else if activeTab === 'primers' && data.primers?.length}
			<DataTable rows={data.primers} columns={primerColumns} defaultPageSize={10} />
		{:else if activeTab === 'translations' && translationRows.length}
			<DataTable rows={translationRows} columns={translationColumns} defaultPageSize={10} />
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
	.profile { font-size: 0.85rem; position: relative; }
	.viewers {
		display: flex;
		gap: 3rem;
		align-items: stretch;
		margin-bottom: 0.75rem;
	}
	.panel-plasmid {
		flex: 0 0 40%;
		min-width: 0;
	}
	.panel-sequence {
		flex: 1;
		min-width: 0;
		max-height: 70vh;
		overflow: auto;
	}
	.error { color: var(--color-err); font-size: 0.85rem; }
	.empty { color: var(--text-placeholder); font-size: 0.85rem; }
	.tab-content { margin-top: 0.25rem; }
	.seq-oneline :global(.seq-text) {
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
	}
	.cap-note { font-size: 0.72rem; color: var(--text-faint); margin: 0.2rem 0 0; text-align: center; }

	@media (max-width: 640px) {
		.viewers { flex-direction: column; }
		.panel-plasmid { flex: none; }
		.panel-sequence { max-height: 50vh; }
	}
</style>
