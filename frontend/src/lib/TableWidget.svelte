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
</script>

{#if data?.results?.length}
	<DataTable rows={data.results} {columns} actions={tableActions} />
{:else}
	<p class="empty">No results</p>
{/if}

<style>
	.empty { color: var(--text-placeholder); font-size: 0.85rem; }
	:global(.name) { font-weight: 500; }
</style>
