<script>
	let { rows = [], columns = [], actions = [], defaultPageSize = 10 } = $props();

	let pageSize = $state(10);

	$effect(() => {
		pageSize = defaultPageSize;
	});
	let currentPage = $state(0);
	let sortCol = $state(null);
	let sortDir = $state('asc');

	function sortValue(row, col) {
		const def = columns.find(c => c.key === col);
		const val = def?.value ? def.value(row) : row[col];
		if (typeof val === 'number') return val ?? 0;
		if (Array.isArray(val)) return val.join(', ');
		return String(val ?? '');
	}

	const sortedRows = $derived.by(() => {
		if (!rows?.length) return [];
		if (!sortCol) return rows;
		return [...rows].sort((a, b) => {
			const va = sortValue(a, sortCol);
			const vb = sortValue(b, sortCol);
			if (typeof va === 'number' && typeof vb === 'number') {
				return sortDir === 'asc' ? va - vb : vb - va;
			}
			const cmp = String(va).localeCompare(String(vb));
			return sortDir === 'asc' ? cmp : -cmp;
		});
	});

	const totalPages = $derived(Math.max(1, Math.ceil(sortedRows.length / pageSize)));
	const pageRows = $derived(sortedRows.slice(currentPage * pageSize, (currentPage + 1) * pageSize));
	const showControls = $derived((rows?.length ?? 0) > 5);

	$effect(() => {
		const _ = rows;
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

	function formatCell(row, colDef) {
		if (colDef.format) return colDef.format(row);
		const val = colDef.value ? colDef.value(row) : row[colDef.key];
		if (Array.isArray(val)) return val.join(', ');
		return val ?? '';
	}

	function visibleActions(row) {
		return actions.filter(a => !a.show || a.show(row));
	}
</script>

{#if rows?.length}
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
			{#each columns as col}
				<th class="sortable" onclick={() => toggleSort(col.key)}>
					{col.label}
					{#if sortCol === col.key}
						<span class="sort-arrow">{sortDir === 'asc' ? '\u25B2' : '\u25BC'}</span>
					{/if}
				</th>
			{/each}
			{#if actions.length}
				<th></th>
			{/if}
		</tr>
	</thead>
	<tbody>
		{#each pageRows as row}
		<tr>
			{#each columns as col}
				<td class={col.class || ''}>{formatCell(row, col)}</td>
			{/each}
			{#if actions.length}
				<td class="actions">
					{#each visibleActions(row) as action}
						<button class="action-btn" onclick={() => action.onClick(row)} title={action.title?.(row) || action.label}>{action.label}</button>
					{/each}
				</td>
			{/if}
		</tr>
		{/each}
	</tbody>
</table>
{:else}
<p class="empty">No data</p>
{/if}

<style>
	table { width: 100%; border-collapse: collapse; font-size: 0.82rem; table-layout: fixed; }
	th, td { padding: 0.4rem 0.6rem; text-align: left; border-bottom: 1px solid var(--border-muted); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
	th { font-weight: 600; color: var(--text-faint); font-size: 0.75rem; text-transform: uppercase; }
	.actions { white-space: nowrap; }
	.action-btn {
		font-size: 0.75rem;
		padding: 0.2rem 0.6rem;
		cursor: pointer;
		border: 1px solid var(--border);
		background: var(--bg-surface);
		border-radius: 4px;
		margin-left: 0.25rem;
		color: var(--text);
	}
	.action-btn:hover { background: var(--bg-muted); }
	.empty { color: var(--text-placeholder); font-size: 0.85rem; }

	.table-controls {
		display: flex;
		justify-content: space-between;
		align-items: center;
		margin-bottom: 0.5rem;
		font-size: 0.75rem;
		color: var(--text-faint);
	}

	.page-size {
		display: flex;
		align-items: center;
		gap: 0.25rem;
	}

	.page-size button {
		padding: 0.15rem 0.5rem;
		border: 1px solid var(--border);
		background: var(--bg-surface);
		border-radius: 3px;
		cursor: pointer;
		font-size: 0.75rem;
		color: var(--text);
	}

	.page-size button.active {
		background: var(--btn-bg);
		color: var(--btn-fg);
		border-color: var(--btn-bg);
	}

	.page-nav {
		display: flex;
		align-items: center;
		gap: 0.5rem;
	}

	.page-nav button {
		padding: 0.15rem 0.4rem;
		border: 1px solid var(--border);
		background: var(--bg-surface);
		border-radius: 3px;
		cursor: pointer;
		font-size: 0.75rem;
		color: var(--text);
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
		color: var(--text);
	}

	.sort-arrow {
		font-size: 0.6rem;
		margin-left: 0.2rem;
	}
</style>
