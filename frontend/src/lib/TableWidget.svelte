<script>
	import { appConfig } from '$lib/stores/chat.ts';
	import { sendMessage } from '$lib/stores/chat.ts';

	let { data } = $props();

	const columnLabels = {
		name: 'Name',
		size_bp: 'Size',
		topology: 'Topology',
		features: 'Features',
		score: 'Score',
		file_path: 'File',
	};

	function formatCell(row, col) {
		const val = row[col];
		if (col === 'size_bp') return val ? `${(val / 1000).toFixed(1)}kb` : '';
		if (col === 'features') return Array.isArray(val) ? val.join(', ') : '';
		if (col === 'score') return val != null ? val.toFixed(2) : '';
		return val ?? '';
	}

	function viewFile(filePath) {
		sendMessage(`//profile ${JSON.stringify({ name: filePath })}`);
	}
</script>

{#if data?.results?.length}
<table>
	<thead>
		<tr>
			{#each $appConfig.search_columns as col}
				<th>{columnLabels[col] || col}</th>
			{/each}
			<th></th>
		</tr>
	</thead>
	<tbody>
		{#each data.results as row}
		<tr>
			{#each $appConfig.search_columns as col}
				<td class:name={col === 'name'}>{formatCell(row, col)}</td>
			{/each}
			<td>
				{#if row.file_path}
					<button class="view-btn" onclick={() => viewFile(row.name)} title={row.file_path}>View</button>
				{/if}
			</td>
		</tr>
		{/each}
	</tbody>
</table>
{:else}
<p class="empty">No results</p>
{/if}

<style>
	table { width: 100%; border-collapse: collapse; font-size: 0.82rem; }
	th, td { padding: 0.4rem 0.6rem; text-align: left; border-bottom: 1px solid #f0f0f0; }
	th { font-weight: 600; color: #888; font-size: 0.75rem; text-transform: uppercase; }
	.name { font-weight: 500; }
	.view-btn {
		font-size: 0.75rem;
		padding: 0.2rem 0.6rem;
		cursor: pointer;
		border: 1px solid #ddd;
		background: white;
		border-radius: 4px;
	}
	.view-btn:hover { background: #f0f0f0; }
	.empty { color: #aaa; font-size: 0.85rem; }
</style>
