<script>
	import { sendMessage } from '$lib/stores/chat.ts';
	import DataTable from '$lib/DataTable.svelte';

	let { data } = $props();

	const columns = [
		{ key: 'subject', label: 'Hit', class: 'name' },
		{ key: 'identity', label: 'Identity', format: (row) => `${row.identity}%` },
		{ key: 'alignment_length', label: 'Length' },
		{ key: 'evalue', label: 'E-value' },
		{ key: 'bitscore', label: 'Bitscore' },
	];

	function viewProfile(name) {
		sendMessage(`//profile ${JSON.stringify({ name: name.replace(/_/g, ' ') })}`);
	}

	async function openInFinder(filePath) {
		try {
			await fetch('/api/open-file', {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ path: filePath }),
			});
		} catch (e) {
			console.error('Failed to open file:', e);
		}
	}

	const tableActions = [
		{
			label: 'Open',
			onClick: (row) => openInFinder(row.file_path),
			show: (row) => !!row.file_path,
			title: (row) => row.file_path,
		},
		{
			label: 'Profile',
			onClick: (row) => viewProfile(row.subject),
			title: () => 'View sequence details',
		},
	];
</script>

{#if data?.error}
<p class="error">{data.error}</p>
{:else if data?.hits?.length}
	<DataTable rows={data.hits} {columns} actions={tableActions} />
{:else}
<p class="empty">No BLAST hits found</p>
{/if}

<style>
	.empty { color: var(--text-placeholder); font-size: 0.85rem; }
	.error { color: var(--color-err); font-size: 0.85rem; }
	:global(.name) { font-weight: 500; }
</style>
