<script>
	import { sendMessage } from '$lib/stores/chat.ts';
	import { copyToClipboard } from '$lib/clipboard.ts';
	import DataTable from '$lib/DataTable.svelte';

	let { data } = $props();

	const columns = [
		{ key: 'sid', label: 'SID' },
		{ key: 'subject', label: 'Hit', class: 'name' },
		{ key: 'identity', label: 'Identity', format: (row) => `${row.identity}%` },
		{ key: 'alignment_length', label: 'Length' },
		{ key: 'evalue', label: 'E-value' },
		{ key: 'bitscore', label: 'Bitscore' },
	];

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
			show: (row) => row.sid != null,
			title: () => 'View sequence details',
		},
	];
</script>

{#if data?.error}
<p class="error">{data.error}</p>
{:else if data?.hits?.length}
	{#if data.program}<p class="program">{data.program} — {data.total} hit(s)</p>{/if}
	<DataTable rows={data.hits} {columns} actions={tableActions} />
{:else}
<p class="empty">No BLAST hits found</p>
{/if}

<style>
	.empty { color: var(--text-placeholder); font-size: 0.85rem; }
	.error { color: var(--color-err); font-size: 0.85rem; }
	.program { font-size: 0.8rem; color: var(--text-secondary); margin-bottom: 0.25rem; }
	:global(.name) { font-weight: 500; }
</style>
