<script>
	import { sendMessage } from '$lib/stores/chat.ts';
	import { copyToClipboard } from '$lib/clipboard.ts';
	import DataTable from '$lib/DataTable.svelte';

	let { data } = $props();

	const columnDefs = {
		sid: { key: 'sid', label: 'SID' },
		name: { key: 'name', label: 'Name', class: 'name' },
		size_bp: { key: 'size_bp', label: 'Size', format: (row) => row.size_bp ? `${(row.size_bp / 1000).toFixed(1)}kb` : '' },
		topology: { key: 'topology', label: 'Topology' },
		features: { key: 'features', label: 'Features', format: (row) => Array.isArray(row.features) ? row.features.join(', ') : '' },
		tags: { key: 'tags', label: 'Tags', format: (row) => Array.isArray(row.tags) ? row.tags.join(', ') : '' },
		score: { key: 'score', label: 'Score', format: (row) => row.score != null ? row.score.toFixed(2) : '' },
		file_path: { key: 'file_path', label: 'File' },
	};

	const HIDDEN_KEYS = new Set([]);

	// Auto-discover columns from data — show everything
	const columns = $derived.by(() => {
		const results = data?.results;
		if (!results?.length) return [];
		const keys = Object.keys(results[0]).filter(k => !HIDDEN_KEYS.has(k));
		return keys.map(k => columnDefs[k] || { key: k, label: k.replace(/_/g, ' ') });
	});

	function viewProfile(row) {
		sendMessage(`//profile ${JSON.stringify({ sid: row.sid })}`);
	}

	const tableActions = [
		{
			label: 'Copy path',
			onClick: (row) => copyToClipboard(row.file_path),
			show: (row) => !!row.file_path,
			title: (row) => row.file_path,
		},
		{
			label: 'Profile',
			onClick: (row) => viewProfile(row),
			title: () => 'View sequence details',
		},
	];

	// Parts columns and actions
	const partsColumns = [
		{ key: 'pid', label: 'PID' },
		{ key: 'names', label: 'Names', class: 'name', format: (row) => Array.isArray(row.names) ? row.names.join(', ') : '' },
		{ key: 'types', label: 'Type(s)', format: (row) => Array.isArray(row.types) ? row.types.join(', ') : '' },
		{ key: 'length', label: 'Length', format: (row) => row.length ? `${row.length} bp` : '' },
		{ key: 'instance_count', label: 'Instances' },
		{ key: 'score', label: 'Score', format: (row) => row.score != null ? row.score.toFixed(2) : '' },
	];

	function viewPart(row) {
		sendMessage(`//parts ${JSON.stringify({ pid: row.pid })}`);
	}

	const partsActions = [
		{
			label: 'View',
			onClick: (row) => viewPart(row),
			title: () => 'View part details',
		},
	];
</script>

{#if data?.error}
	<p class="error">{data.error}</p>
{:else if data?.results?.length}
	<DataTable rows={data.results} {columns} actions={tableActions} />
{:else if !data?.parts?.length}
	<p class="empty">No results</p>
{/if}

{#if data?.parts?.length}
	<div class="parts-section">
		<h4 class="parts-heading">Matching Parts ({data.parts_total})</h4>
		<DataTable rows={data.parts} columns={partsColumns} actions={partsActions} defaultPageSize={5} />
	</div>
{/if}

<style>
	.error { color: var(--color-err); font-size: 0.85rem; }
	.empty { color: var(--text-placeholder); font-size: 0.85rem; }
	:global(.name) { font-weight: 500; }
	.parts-section { margin-top: 1rem; }
	.parts-heading {
		font-size: 0.8rem;
		font-weight: 600;
		color: var(--text-faint);
		text-transform: uppercase;
		margin: 0 0 0.5rem 0;
	}
</style>
