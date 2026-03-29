<script>
	import { ProteinSequenceViewer, Tooltip } from '@molbiohive/hatchlings';
	import CopyableSequence from '$lib/CopyableSequence.svelte';

	let { data } = $props();
	let containerEl = $state(undefined);
	let containerWidth = $state(600);
	let hover = $state(null);

	const proteinSeq = $derived(data?.protein || '');

	const proteinData = $derived.by(() => {
		if (!proteinSeq) return null;
		return {
			seq: proteinSeq,
			dnaSource: data?.dna_source,
			frame: data?.frame,
		};
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
{:else if proteinData}
<div class="protein-widget" bind:this={containerEl}>
	<div class="meta">
		<span><strong>Length:</strong> {data.protein_length || proteinSeq.length} aa</span>
		{#if data.complete != null}
			<span><strong>ORF:</strong> {data.complete ? 'complete' : 'partial'}</span>
		{/if}
		{#if data.stop_codons != null}
			<span><strong>Stops:</strong> {data.stop_codons}</span>
		{/if}
		{#if data.codon_table}
			<span><strong>Table:</strong> {data.codon_table}</span>
		{/if}
	</div>
	<div class="viewer-wrap">
		<ProteinSequenceViewer
			data={proteinData}
			colorResidues={true}
			showNumbers={true}
			width={Math.max(400, containerWidth - 2)}
			height={Math.min(500, 80 + Math.ceil(proteinSeq.length / 60) * 24)}
			onhoverinfo={(info) => { hover = info; }}
		/>
	</div>
	<Tooltip
		visible={hover != null}
		x={hover?.position?.x}
		y={hover?.position?.y}
		title={hover?.title}
		items={hover?.items}
	/>
	<div class="seq-copy">
		<CopyableSequence sequence={proteinSeq}
			display="{proteinSeq.slice(0, 40)}... ({proteinSeq.length} aa)"
			label="Click to copy protein sequence" />
	</div>
</div>
{:else}
<p class="empty">No protein data</p>
{/if}

<style>
	.protein-widget { font-size: 0.85rem; position: relative; }
	.meta {
		display: flex;
		flex-wrap: wrap;
		gap: 0.5rem 1rem;
		margin-bottom: 0.5rem;
		font-size: 0.8rem;
		color: var(--text-secondary);
	}
	.viewer-wrap {
		border-radius: 6px;
		overflow: hidden;
		border: 1px solid var(--border-muted);
		margin-bottom: 0.5rem;
	}
	.seq-copy { margin-top: 0.5rem; }
	.error { color: var(--color-err); font-size: 0.85rem; }
	.empty { color: var(--text-placeholder); font-size: 0.85rem; }
</style>
