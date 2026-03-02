<script>
	import { sendMessage } from '$lib/stores/chat.ts';
	import { copyToClipboard } from '$lib/clipboard.ts';
	import DataTable from '$lib/DataTable.svelte';

	let { data } = $props();

	let tab = $state('sequences');

	const seqColumns = [
		{ key: 'sid', label: 'SID' },
		{ key: 'subject', label: 'Hit', class: 'name' },
		{ key: 'identity', label: 'Identity', format: (row) => `${row.identity}%` },
		{ key: 'alignment_length', label: 'Length' },
		{ key: 'evalue', label: 'E-value' },
		{ key: 'bitscore', label: 'Bitscore' },
	];

	const partColumns = [
		{ key: 'pid', label: 'PID' },
		{ key: 'subject', label: 'Hit', class: 'name' },
		{ key: 'identity', label: 'Identity', format: (row) => `${row.identity}%` },
		{ key: 'alignment_length', label: 'Length' },
		{ key: 'evalue', label: 'E-value' },
		{ key: 'bitscore', label: 'Bitscore' },
	];

	const seqActions = [
		{
			label: 'Copy path',
			onClick: (row) => copyToClipboard(row.file_path),
			show: (row) => !!row.file_path,
			title: (row) => row.file_path,
		},
		{
			label: 'Profile',
			onClick: (row) => sendMessage(`//profile ${JSON.stringify({ sid: row.sid })}`),
			show: (row) => row.sid != null,
			title: () => 'View sequence details',
		},
	];

	const partActions = [
		{
			label: 'View',
			onClick: (row) => sendMessage(`//parts ${JSON.stringify({ pid: row.pid })}`),
			title: () => 'View part details',
		},
	];

	const seqHits = $derived((data?.hits || []).filter(h => h.sid != null && h.pid == null));
	const partHits = $derived((data?.hits || []).filter(h => h.pid != null));
</script>

{#if data?.error}
<p class="error">{data.error}</p>
{:else if data?.hits?.length}
	{#if data.program}<p class="program">{data.program} -- {data.total} hit(s)</p>{/if}
	<div class="tab-bar">
		<button class="tab-btn" class:active={tab === 'sequences'} onclick={() => tab = 'sequences'}>
			Sequences ({seqHits.length})
		</button>
		<button class="tab-btn" class:active={tab === 'parts'} onclick={() => tab = 'parts'}>
			Parts ({partHits.length})
		</button>
	</div>
	{#if tab === 'sequences'}
		{#if seqHits.length > 0}
			<DataTable rows={seqHits} columns={seqColumns} actions={seqActions} />
		{:else}
			<p class="empty">No sequence hits</p>
		{/if}
	{:else}
		{#if partHits.length > 0}
			<DataTable rows={partHits} columns={partColumns} actions={partActions} />
		{:else}
			<p class="empty">No part hits</p>
		{/if}
	{/if}
{:else}
<p class="empty">No BLAST hits found</p>
{/if}

<style>
	.empty { color: var(--text-placeholder); font-size: 0.85rem; }
	.error { color: var(--color-err); font-size: 0.85rem; }
	.program { font-size: 0.8rem; color: var(--text-secondary); margin-bottom: 0.25rem; }
	:global(.name) { font-weight: 500; }

	.tab-bar {
		display: flex;
		gap: 2px;
		background: var(--bg-app);
		border-radius: 6px;
		padding: 2px;
		margin-bottom: 0.5rem;
	}

	.tab-btn {
		flex: 1;
		padding: 0.3rem 0.5rem;
		border: none;
		background: transparent;
		border-radius: 4px;
		cursor: pointer;
		font-size: 0.75rem;
		font-family: inherit;
		color: var(--text-faint);
		transition: background 0.15s, color 0.15s;
	}

	.tab-btn:hover {
		color: var(--text);
	}

	.tab-btn.active {
		background: var(--bg-surface);
		color: var(--text);
		font-weight: 600;
	}
</style>
