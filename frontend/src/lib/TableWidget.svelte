<script>
	import { appConfig } from '$lib/stores/chat.ts';
	import { sendMessage } from '$lib/stores/chat.ts';

	let { data } = $props();

	let pageSize = $state(10);
	let currentPage = $state(0);
	let sortCol = $state(null);
	let sortDir = $state('asc');

	const columnLabels = {
		name: 'Name',
		size_bp: 'Size',
		topology: 'Topology',
		features: 'Features',
		score: 'Score',
		file_path: 'File',
	};

	function sortValue(row, col) {
		const val = row[col];
		if (col === 'size_bp') return val ?? 0;
		if (col === 'score') return val ?? 0;
		if (Array.isArray(val)) return val.join(', ');
		return String(val ?? '');
	}

	const sortedResults = $derived.by(() => {
		if (!data?.results) return [];
		if (!sortCol) return data.results;
		return [...data.results].sort((a, b) => {
			const va = sortValue(a, sortCol);
			const vb = sortValue(b, sortCol);
			if (typeof va === 'number' && typeof vb === 'number') {
				return sortDir === 'asc' ? va - vb : vb - va;
			}
			const cmp = String(va).localeCompare(String(vb));
			return sortDir === 'asc' ? cmp : -cmp;
		});
	});

	const totalPages = $derived(Math.max(1, Math.ceil(sortedResults.length / pageSize)));
	const pageResults = $derived(sortedResults.slice(currentPage * pageSize, (currentPage + 1) * pageSize));
	const showControls = $derived((data?.results?.length ?? 0) > 5);

	// Reset pagination when data changes (e.g. re-run)
	$effect(() => {
		const _ = data?.results;
		currentPage = 0;
		sortCol = null;
		sortDir = 'asc';
	});

	function toggleSort(col) {
		if (sortCol === col) {
			sortDir = sortDir === 'asc' ? 'desc' : 'asc';
		} else {
			sortCol = col;
			sortDir = 'asc';
		}
		currentPage = 0;
	}

	function setPageSize(size) {
		pageSize = size;
		currentPage = 0;
	}

	function formatCell(row, col) {
		const val = row[col];
		if (col === 'size_bp') return val ? `${(val / 1000).toFixed(1)}kb` : '';
		if (col === 'features') return Array.isArray(val) ? val.join(', ') : '';
		if (col === 'score') return val != null ? val.toFixed(2) : '';
		if (col === 'file_path') return val ? val.split('/').pop() : '';
		return val ?? '';
	}

	function viewProfile(name) {
		sendMessage(`//profile ${JSON.stringify({ name })}`);
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
</script>

{#if data?.results?.length}
{#if showControls}
<div class="table-controls">
	<div class="page-size">
		Show:
		{#each [5, 10, 50] as size}
			<button class:active={pageSize === size} onclick={() => setPageSize(size)}>{size}</button>
		{/each}
	</div>
	<div class="page-nav">
		<button onclick={() => currentPage = Math.max(0, currentPage - 1)} disabled={currentPage === 0}>&lt;</button>
		<span>Page {currentPage + 1} of {totalPages}</span>
		<button onclick={() => currentPage = Math.min(totalPages - 1, currentPage + 1)} disabled={currentPage >= totalPages - 1}>&gt;</button>
	</div>
</div>
{/if}
<table>
	<thead>
		<tr>
			{#each $appConfig.search_columns as col}
				<th class="sortable" onclick={() => toggleSort(col)}>
					{columnLabels[col] || col}
					{#if sortCol === col}
						<span class="sort-arrow">{sortDir === 'asc' ? '\u25B2' : '\u25BC'}</span>
					{/if}
				</th>
			{/each}
			<th></th>
		</tr>
	</thead>
	<tbody>
		{#each pageResults as row}
		<tr>
			{#each $appConfig.search_columns as col}
				<td class:name={col === 'name'}>{formatCell(row, col)}</td>
			{/each}
			<td class="actions">
				{#if row.file_path}
					<button class="action-btn" onclick={() => openInFinder(row.file_path)} title={row.file_path}>Open</button>
				{/if}
				<button class="action-btn" onclick={() => viewProfile(row.name)} title="View sequence details">Profile</button>
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
	.actions { white-space: nowrap; }
	.action-btn {
		font-size: 0.75rem;
		padding: 0.2rem 0.6rem;
		cursor: pointer;
		border: 1px solid #ddd;
		background: white;
		border-radius: 4px;
		margin-left: 0.25rem;
	}
	.action-btn:hover { background: #f0f0f0; }
	.empty { color: #aaa; font-size: 0.85rem; }

	.table-controls {
		display: flex;
		justify-content: space-between;
		align-items: center;
		margin-bottom: 0.5rem;
		font-size: 0.75rem;
		color: #888;
	}

	.page-size {
		display: flex;
		align-items: center;
		gap: 0.25rem;
	}

	.page-size button {
		padding: 0.15rem 0.5rem;
		border: 1px solid #ddd;
		background: white;
		border-radius: 3px;
		cursor: pointer;
		font-size: 0.75rem;
	}

	.page-size button.active {
		background: #333;
		color: white;
		border-color: #333;
	}

	.page-nav {
		display: flex;
		align-items: center;
		gap: 0.5rem;
	}

	.page-nav button {
		padding: 0.15rem 0.4rem;
		border: 1px solid #ddd;
		background: white;
		border-radius: 3px;
		cursor: pointer;
		font-size: 0.75rem;
	}

	.page-nav button:disabled {
		opacity: 0.3;
		cursor: default;
	}

	.sortable {
		cursor: pointer;
		user-select: none;
	}

	.sortable:hover {
		color: #333;
	}

	.sort-arrow {
		font-size: 0.6rem;
		margin-left: 0.2rem;
	}
</style>
