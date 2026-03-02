<script>
	import DataTable from '$lib/DataTable.svelte';
	import CopyableSequence from '$lib/CopyableSequence.svelte';

	let { data } = $props();

	// PID mode: data.part present; SID mode: data.parts array
	const isPidMode = $derived(!!data?.part);

	const seqPreview = $derived.by(() => {
		const s = data?.part?.sequence;
		if (!s) return '';
		return s.length > 100 ? s.slice(0, 100) + '\u2026' : s;
	});

	const instanceColumns = [
		{ key: 'sid', label: 'SID' },
		{ key: 'sequence_name', label: 'Sequence' },
		{ key: 'annotation_type', label: 'Type' },
		{ key: 'location', label: 'Location', format: (row) => `${row.start}..${row.end}` },
		{ key: 'strand', label: 'Strand', format: (row) => row.strand > 0 ? '+' : '\u2212' },
		{ key: 'file_path', label: 'File' },
	];

	const partsColumns = [
		{ key: 'pid', label: 'PID' },
		{ key: 'name', label: 'Name' },
		{ key: 'type', label: 'Type' },
		{ key: 'location', label: 'Location', format: (row) => row.start != null ? `${row.start}..${row.end}` : '' },
		{ key: 'strand', label: 'Strand', format: (row) => row.strand == null ? '' : row.strand > 0 ? '+' : '\u2212' },
		{ key: 'length', label: 'Length', format: (row) => row.length ? `${row.length} bp` : '' },
	];

	const relativeColumns = [
		{ key: 'subject', label: 'Subject' },
		{ key: 'identity', label: 'Identity %', format: (row) => row.identity.toFixed(1) },
		{ key: 'alignment_length', label: 'Align Len' },
		{ key: 'evalue', label: 'E-value', format: (row) => row.evalue.toExponential(1) },
		{ key: 'bitscore', label: 'Bitscore', format: (row) => row.bitscore.toFixed(0) },
	];
</script>

{#if isPidMode}
<div class="parts-detail">
	<div class="field"><strong>PID:</strong> {data.part.pid}</div>
	{#if data.part.names?.length}
	<div class="field"><strong>Names:</strong> {data.part.names.join(', ')}</div>
	{/if}
	<div class="field"><strong>Molecule:</strong> {data.part.molecule}</div>
	<div class="field"><strong>Length:</strong> {data.part.length} bp</div>

	{#if data.part.sequence}
	<h4>Sequence</h4>
	<CopyableSequence
		sequence={data.part.sequence}
		display={seqPreview}
		label="{data.part.length} bp -- click to copy"
	/>
	{/if}

	{#if data.instances?.length}
	<h4>Instances ({data.instances_count})</h4>
	<DataTable rows={data.instances} columns={instanceColumns} defaultPageSize={10} />
	{/if}

	{#if data.annotations?.length}
	<h4>Annotations</h4>
	<div class="annotations">
		{#each data.annotations as ann}
		<div class="ann-row"><strong>{ann.key}:</strong> {ann.value} <span class="ann-src">({ann.source})</span></div>
		{/each}
	</div>
	{/if}

	{#if data.libraries?.length}
	<h4>Libraries</h4>
	<div class="libs">
		{#each data.libraries as lib}
		<span class="lib-tag">{lib.name}</span>
		{/each}
	</div>
	{/if}

	{#if data.relatives?.length}
	<h4>Similar Parts (BLAST)</h4>
	<DataTable rows={data.relatives} columns={relativeColumns} defaultPageSize={10} />
	{/if}
</div>
{:else if data?.parts}
<div class="parts-list">
	{#if data.sequence_name}
	<div class="field"><strong>Sequence:</strong> {data.sequence_name}</div>
	{/if}
	<DataTable rows={data.parts} columns={partsColumns} defaultPageSize={15} />
</div>
{:else}
<p class="empty">No part data</p>
{/if}

<style>
	.parts-detail, .parts-list { font-size: 0.85rem; }
	.field { margin-bottom: 0.3rem; }
	h4 { margin: 0.75rem 0 0.3rem; font-size: 0.85rem; color: var(--text-muted); }
	.empty { color: var(--text-placeholder); font-size: 0.85rem; }
	.annotations { font-size: 0.82rem; }
	.ann-row { margin-bottom: 0.2rem; }
	.ann-src { color: var(--text-faint); font-size: 0.75rem; }
	.libs { display: flex; flex-wrap: wrap; gap: 0.4rem; }
	.lib-tag {
		background: var(--bg-muted);
		border: 1px solid var(--border-muted);
		border-radius: 4px;
		padding: 0.15rem 0.5rem;
		font-size: 0.78rem;
	}
</style>
