<script>
	import { mapToParts, mapToCutSites } from '$lib/hatchlings.ts';
	import { PlasmidViewer, SequenceViewer, Tooltip, SelectionState } from '@molbiohive/hatchlings';

	let { data } = $props();

	const MAX_CUTSITES = 50;

	const parts = $derived(mapToParts(data?.features, data?.primers));

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

	const seq = $derived(data?.sequence);
	const seqData = $derived(seq?.sequence_data || '');
	const topology = $derived(seq?.topology || 'circular');

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
</script>

{#if seq}
<div class="examine">
	<div class="examine-header">
		<strong>{seq.name}</strong>
		<span class="meta">{seq.size_bp} bp, {topology}</span>
		{#if seq.molecule}<span class="meta">{seq.molecule}</span>{/if}
	</div>

	<div class="examine-panels">
		<div class="panel-plasmid" bind:clientWidth={plasmidW}>
			{#if plasmidW > 0}
			<PlasmidViewer
				name={seq.name}
				size={seq.size_bp}
				{parts}
				cutSites={cappedCutSites}
				{topology}
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
				seq={seqData}
				{parts}
				cutSites={cappedCutSites}
				{topology}
				{selectionState}
				width={seqPanelW}
				showComplement={true}
				showAnnotations={true}
				onhoverinfo={(info) => { hover = info; }}
			/>
			{/if}
		</div>
		{/if}
	</div>

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
{:else}
<p class="empty">Sequence not found</p>
{/if}

<style>
	.examine { font-size: 0.85rem; position: relative; }
	.examine-header {
		display: flex;
		align-items: baseline;
		gap: 0.5rem;
		margin-bottom: 0.5rem;
	}
	.meta { font-size: 0.78rem; color: var(--text-muted); }
	.examine-panels {
		display: flex;
		gap: 3rem;
		align-items: center;
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
	.empty { color: var(--text-placeholder); font-size: 0.85rem; }
	.cap-note { font-size: 0.72rem; color: var(--text-faint); margin: 0.2rem 0 0; text-align: center; }

	@media (max-width: 640px) {
		.examine-panels { flex-direction: column; }
		.panel-plasmid { flex: none; }
		.panel-sequence { max-height: 50vh; }
	}
</style>
