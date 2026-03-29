<script>
	import { sendMessage } from '$lib/stores/chat.ts';
	import CopyableSequence from '$lib/CopyableSequence.svelte';

	let { rows = [], columns = [], actions = [], defaultPageSize = 10 } = $props();

	let pageSize = $state(10);

	$effect(() => {
		pageSize = defaultPageSize;
	});
	let currentPage = $state(0);
	let sortCol = $state(null);
	let sortDir = $state('asc');
	let colWidths = $state([]); // pixel widths per column (0 = auto)
	let tableEl = $state(undefined);
	let fitted = $state(true); // true = fixed layout (fit screen), false = auto (scrollable)
	let gradientMode = $state(0); // 0=off, 1=red-white-green, 2=green-white-red

	// Reset column widths when columns change
	$effect(() => {
		if (columns.length) {
			colWidths = columns.map(() => 0);
		}
	});

	function rawValue(row, col) {
		const def = columns.find(c => c.key === col);
		return def?.value ? def.value(row) : row[col];
	}

	function sortValue(row, col) {
		const val = rawValue(row, col);
		if (typeof val === 'number') return val ?? 0;
		if (Array.isArray(val)) return val.join(', ');
		return String(val ?? '');
	}

	function colType(colKey) {
		if (!rows?.length) return null;
		for (let i = 0; i < Math.min(rows.length, 20); i++) {
			const v = rawValue(rows[i], colKey);
			if (v == null) continue;
			if (typeof v === 'boolean') return 'bool';
			if (typeof v === 'number') return 'num';
			return null;
		}
		return null;
	}

	function isNumericCol(colKey) {
		return colType(colKey) != null;
	}

	// Per-column gradient rank maps: colKey -> { map: Map<rowIndex, normalizedRank 0..1>, bool: boolean }
	const gradientRanks = $derived.by(() => {
		if (gradientMode === 0 || !rows?.length) return {};
		const ranks = {};
		for (const col of columns) {
			const ct = colType(col.key);
			if (!ct) continue;
			const isBool = ct === 'bool';
			const vals = rows.map((r, i) => {
				const v = rawValue(r, col.key);
				const n = typeof v === 'boolean' ? (v ? 1 : 0) : (typeof v === 'number' ? v : null);
				return { idx: i, val: n };
			}).filter(x => x.val != null);
			if (vals.length < 2) continue;
			// Skip if all values identical
			const first = vals[0].val;
			if (vals.every(x => x.val === first)) continue;
			vals.sort((a, b) => a.val - b.val);
			const map = new Map();
			for (let i = 0; i < vals.length; i++) {
				map.set(vals[i].idx, i / (vals.length - 1));
			}
			ranks[col.key] = { map, bool: isBool };
		}
		return ranks;
	});

	function cellBg(row, colKey) {
		if (gradientMode === 0) return '';
		const info = gradientRanks[colKey];
		if (!info) return '';
		const rowIdx = rows.indexOf(row);
		const rank = info.map.get(rowIdx);
		if (rank == null) return '';

		if (info.bool) {
			// Binary: true=green, false=red (mode 2 swaps)
			const isTrue = rank > 0.5;
			const green = gradientMode === 1 ? isTrue : !isTrue;
			return green ? 'rgba(80, 225, 80, 0.3)' : 'rgba(220, 80, 80, 0.3)';
		}

		// Numeric gradient: rank 0=lowest, 1=highest
		// mode 1: low=red, mid=white, high=green
		// mode 2: low=green, mid=white, high=red
		let r, g, b;
		const t = gradientMode === 1 ? rank : 1 - rank;
		if (t < 0.5) {
			// red → white (t: 0→0.5)
			const p = t * 2;
			r = 220 + Math.round(35 * p);
			g = 80 + Math.round(175 * p);
			b = 80 + Math.round(175 * p);
		} else {
			// white → green (t: 0.5→1)
			const p = (t - 0.5) * 2;
			r = 255 - Math.round(175 * p);
			g = 255 - Math.round(30 * p);
			b = 255 - Math.round(175 * p);
		}
		return `rgba(${r}, ${g}, ${b}, 0.35)`;
	}

	function cycleGradient() {
		gradientMode = (gradientMode + 1) % 3;
	}

	const hasNumericCols = $derived(columns.some(c => isNumericCol(c.key)));

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

	function cellText(row, colDef) {
		const val = formatCell(row, colDef);
		return String(val);
	}

	// Auto-detect SID/PID columns for View button
	const hasSid = $derived(columns.some(c => c.key === 'sid'));
	const hasPid = $derived(columns.some(c => c.key === 'pid'));

	const allActions = $derived.by(() => {
		const result = [...actions];
		const hasView = actions.some(a => a.label === 'View' || a.label === 'Profile');
		if (!hasView) {
			if (hasSid) {
				result.push({
					label: 'View',
					onClick: (row) => sendMessage(`//profile ${JSON.stringify({ sid: row.sid })}`),
					title: () => 'View sequence details',
				});
			} else if (hasPid) {
				result.push({
					label: 'View',
					onClick: (row) => sendMessage(`//parts ${JSON.stringify({ pid: row.pid })}`),
					title: () => 'View part details',
				});
			}
		}
		return result;
	});

	function visibleActions(row) {
		return allActions.filter(a => !a.show || a.show(row));
	}

	// Column resize via drag
	function startResize(e, colIndex) {
		e.preventDefault();
		e.stopPropagation();

		const th = e.target.closest('th');
		if (!th) return;

		// If no explicit widths yet, snapshot current widths
		if (colWidths.every(w => w === 0) && tableEl) {
			const ths = tableEl.querySelectorAll('thead th');
			const totalCols = columns.length + (allActions.length ? 1 : 0);
			const newWidths = columns.map((_, i) => i < ths.length ? ths[i].offsetWidth : 80);
			colWidths = newWidths;
		}

		const startX = e.clientX;
		const startWidth = colWidths[colIndex] || th.offsetWidth;

		function onMouseMove(ev) {
			const diff = ev.clientX - startX;
			const newWidth = Math.max(40, startWidth + diff);
			colWidths = colWidths.map((w, i) => i === colIndex ? newWidth : w);
		}

		function onMouseUp() {
			document.removeEventListener('mousemove', onMouseMove);
			document.removeEventListener('mouseup', onMouseUp);
			document.body.style.cursor = '';
			document.body.style.userSelect = '';
		}

		document.body.style.cursor = 'col-resize';
		document.body.style.userSelect = 'none';
		document.addEventListener('mousemove', onMouseMove);
		document.addEventListener('mouseup', onMouseUp);
	}

	function toggleFit() {
		fitted = !fitted;
		// Reset widths when toggling
		colWidths = columns.map(() => 0);
	}

	const hasCustomWidths = $derived(colWidths.some(w => w > 0));

	// Sequence detection: DNA/RNA (ATGCURYSWKMBDHVN) or amino acid (uppercase letters)
	const _SEQ_RE = /^[ATGCURYSWKMBDHVN*-]+$/i;
	const _AA_RE = /^[ACDEFGHIKLMNPQRSTVWY*-]+$/i;

	function isSequence(val) {
		if (typeof val !== 'string' || val.length < 20) return false;
		return _SEQ_RE.test(val) || _AA_RE.test(val);
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
		<span class="control-sep"></span>
		<button class:active={fitted} onclick={toggleFit} title={fitted ? 'Switch to scrollable layout' : 'Fit table to screen'}>
			{fitted ? 'Fitted' : 'Scroll'}
		</button>
		{#if hasNumericCols}
			<button class="gradient-btn" onclick={cycleGradient} title={gradientMode === 0 ? 'Enable gradient coloring' : gradientMode === 1 ? 'Reverse gradient' : 'Disable gradient'}>
				<span class="gradient-swatch" class:mode1={gradientMode === 1} class:mode2={gradientMode === 2}></span>
			</button>
		{/if}
	</div>
	<div class="page-nav">
		<button onclick={() => currentPage = Math.max(0, currentPage - 1)} disabled={currentPage === 0}>&lt;</button>
		<span>Page {currentPage + 1} of {totalPages}</span>
		<button onclick={() => currentPage = Math.min(totalPages - 1, currentPage + 1)} disabled={currentPage >= totalPages - 1}>&gt;</button>
	</div>
</div>
{/if}
<div class="table-scroll" class:fitted>
<table bind:this={tableEl} class:fixed-layout={fitted || hasCustomWidths}>
	{#if hasCustomWidths}
	<colgroup>
		{#each columns as _, i}
			<col style={colWidths[i] ? `width: ${colWidths[i]}px` : ''} />
		{/each}
		{#if allActions.length}
			<col />
		{/if}
	</colgroup>
	{/if}
	<thead>
		<tr>
			{#each columns as col, i}
				<th
					class="sortable"
					onclick={() => toggleSort(col.key)}
					style={colWidths[i] ? `width: ${colWidths[i]}px` : ''}
				>
					<span class="th-content">
						{col.label}
						{#if sortCol === col.key}
							<span class="sort-arrow">{sortDir === 'asc' ? '\u25B2' : '\u25BC'}</span>
						{/if}
					</span>
					<!-- svelte-ignore a11y_no_static_element_interactions -->
					<span
						class="resize-handle"
						onmousedown={(e) => startResize(e, i)}
					></span>
				</th>
			{/each}
			{#if allActions.length}
				<th class="actions-th"></th>
			{/if}
		</tr>
	</thead>
	<tbody>
		{#each pageRows as row}
		<tr>
			{#each columns as col}
				{@const cellVal = formatCell(row, col)}
				{#if isSequence(cellVal)}
					<td class="seq-cell {col.class || ''}"
						style={cellBg(row, col.key) ? `background: ${cellBg(row, col.key)}` : ''}
					>
						<CopyableSequence sequence={cellVal} display="{cellVal.slice(0, 30)}... ({cellVal.length})" />
					</td>
				{:else}
					<td class={col.class || ''} title={cellText(row, col)}
						style={cellBg(row, col.key) ? `background: ${cellBg(row, col.key)}` : ''}
					>{cellVal}</td>
				{/if}
			{/each}
			{#if allActions.length}
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
</div>
{:else}
<p class="empty">No data</p>
{/if}

<style>
	.table-scroll { overflow-x: auto; }
	.table-scroll.fitted { overflow-x: hidden; }
	table { width: 100%; border-collapse: collapse; font-size: 0.82rem; }
	table.fixed-layout { table-layout: fixed; }

	th, td {
		padding: 0.4rem 0.6rem;
		text-align: left;
		border-bottom: 1px solid var(--border-muted);
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	th {
		font-weight: 600;
		color: var(--text-faint);
		font-size: 0.75rem;
		text-transform: uppercase;
		position: relative;
	}
	.th-content {
		display: inline;
		pointer-events: none;
	}
	.actions { white-space: nowrap; position: sticky; right: 0; background: var(--bg-surface); }
	.actions-th { width: auto; position: sticky; right: 0; background: var(--bg-muted); }
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

	.control-sep {
		width: 1px;
		height: 0.9rem;
		background: var(--border-muted);
		margin: 0 0.25rem;
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

	.gradient-btn {
		padding: 0.15rem 0.35rem;
		display: flex;
		align-items: center;
	}

	.gradient-swatch {
		display: inline-block;
		width: 10px;
		height: 16px;
		border-radius: 2px;
		border: 1px solid var(--border);
		background: var(--bg-surface);
	}
	.gradient-swatch.mode1 {
		background: linear-gradient(to bottom, rgba(220, 80, 80, 0.5), rgba(255, 255, 255, 0.5), rgba(80, 225, 80, 0.5));
		border-color: var(--text-faint);
	}
	.gradient-swatch.mode2 {
		background: linear-gradient(to bottom, rgba(80, 225, 80, 0.5), rgba(255, 255, 255, 0.5), rgba(220, 80, 80, 0.5));
		border-color: var(--text-faint);
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

	/* Column resize handle */
	.resize-handle {
		position: absolute;
		right: 0;
		top: 0;
		bottom: 0;
		width: 5px;
		cursor: col-resize;
		pointer-events: auto;
		z-index: 1;
	}
	.resize-handle:hover {
		background: var(--color-accent-light);
		opacity: 0.4;
	}

	/* Compact CopyableSequence inside table cells */
	.seq-cell { white-space: normal; padding: 0.2rem 0.4rem; }
	.seq-cell :global(.seq-area) {
		padding: 0.2rem 0.4rem;
		max-height: 2.5rem;
		border-radius: 3px;
	}
	.seq-cell :global(.seq-text) { font-size: 0.72rem; }
	.seq-cell :global(.label) { display: none; }
</style>
