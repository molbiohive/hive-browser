<script>
	import { sendMessage } from '$lib/stores/chat.ts';
	import DataTable from '$lib/DataTable.svelte';

	let searchQuery = $state('');
	let blastQuery = $state('');
	let searchResults = $state(null);
	let blastResults = $state(null);
	let searchLoading = $state(false);
	let blastLoading = $state(false);
	let searchTab = $state('sequences'); // 'sequences' | 'parts'
	let _debounceTimer = null; // plain var -- must NOT be $state to avoid retriggering $effect

	// ── Search columns ──

	const seqColumns = [
		{ key: 'sid', label: 'SID' },
		{ key: 'name', label: 'Name', class: 'name' },
		{ key: 'size_bp', label: 'Length', format: (row) => row.size_bp ? `${(row.size_bp / 1000).toFixed(1)}kb` : '' },
		{ key: 'score', label: 'Score', format: (row) => row.score != null ? row.score.toFixed(2) : '' },
	];

	const partsColumns = [
		{ key: 'pid', label: 'PID' },
		{ key: 'names', label: 'Name', class: 'name', format: (row) => Array.isArray(row.names) ? row.names.join(', ') : '' },
		{ key: 'types', label: 'Type', format: (row) => Array.isArray(row.types) ? row.types.join(', ') : '' },
		{ key: 'instance_count', label: 'Inst.' },
		{ key: 'score', label: 'Score', format: (row) => row.score != null ? row.score.toFixed(2) : '' },
	];

	const seqActions = [
		{
			label: 'Profile',
			onClick: (row) => sendMessage(`//profile ${JSON.stringify({ sid: row.sid })}`),
			title: () => 'View sequence details',
		},
	];

	const partsActions = [
		{
			label: 'View',
			onClick: (row) => sendMessage(`//parts ${JSON.stringify({ pid: row.pid })}`),
			title: () => 'View part details',
		},
	];

	// ── BLAST columns ──

	let blastTab = $state('sequences'); // 'sequences' | 'parts'

	const blastSeqColumns = [
		{ key: 'sid', label: 'SID' },
		{ key: 'subject', label: 'Hit', class: 'name' },
		{ key: 'identity', label: 'Identity', format: (row) => `${row.identity}%` },
		{ key: 'alignment_length', label: 'Length' },
	];

	const blastPartColumns = [
		{ key: 'pid', label: 'PID' },
		{ key: 'subject', label: 'Hit', class: 'name' },
		{ key: 'identity', label: 'Identity', format: (row) => `${row.identity}%` },
		{ key: 'alignment_length', label: 'Length' },
	];

	const blastSeqActions = [
		{
			label: 'Profile',
			onClick: (row) => sendMessage(`//profile ${JSON.stringify({ sid: row.sid })}`),
			title: () => 'View sequence details',
		},
	];

	const blastPartActions = [
		{
			label: 'View',
			onClick: (row) => sendMessage(`//parts ${JSON.stringify({ pid: row.pid })}`),
			title: () => 'View part details',
		},
	];

	const blastSeqHits = $derived((blastResults?.hits || []).filter(h => h.sid != null && h.pid == null));
	const blastPartHits = $derived((blastResults?.hits || []).filter(h => h.pid != null));

	// ── Derived ──

	const seqRows = $derived(searchResults?.results || []);
	const partsRows = $derived(searchResults?.parts || []);
	const seqCount = $derived(searchResults?.total ?? 0);
	const partsCount = $derived(searchResults?.parts_total ?? 0);

	// ── Search logic ──

	function debounceSearch(q) {
		clearTimeout(_debounceTimer);
		if (!q.trim() || q.trim().length < 2) {
			searchResults = null;
			searchLoading = false;
			return;
		}
		searchLoading = true;
		_debounceTimer = setTimeout(() => doSearch(q), 300);
	}

	async function doSearch(q) {
		try {
			const res = await fetch(`/api/search?q=${encodeURIComponent(q)}`);
			if (res.ok) {
				searchResults = await res.json();
			} else {
				searchResults = { error: 'Search failed' };
			}
		} catch {
			searchResults = { error: 'Network error' };
		} finally {
			searchLoading = false;
		}
	}

	async function doBlast() {
		const seq = blastQuery.trim();
		if (!seq) return;
		blastLoading = true;
		blastResults = null;
		try {
			const res = await fetch('/api/blast', {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ sequence: seq }),
			});
			if (res.ok) {
				blastResults = await res.json();
			} else {
				blastResults = { error: 'BLAST failed' };
			}
		} catch {
			blastResults = { error: 'Network error' };
		} finally {
			blastLoading = false;
		}
	}

	function handleBlastKeydown(e) {
		if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
			e.preventDefault();
			doBlast();
		}
	}

	$effect(() => {
		debounceSearch(searchQuery);
	});
</script>

<div class="search-panel">
	<div class="panel-header">
		<h3>Search</h3>
	</div>

	<div class="panel-body">
		<!-- Text search input -->
		<div class="search-section">
			<input
				type="text"
				bind:value={searchQuery}
				placeholder="Search sequences and parts..."
				class="search-input"
			/>
			{#if searchLoading}
				<div class="loading">Searching...</div>
			{/if}
		</div>

		<!-- Search results with tab toggle -->
		{#if searchResults && !searchResults.error}
			<div class="results-section">
				<div class="tab-bar">
					<button
						class="tab-btn"
						class:active={searchTab === 'sequences'}
						onclick={() => searchTab = 'sequences'}
					>
						Sequences ({seqCount})
					</button>
					<button
						class="tab-btn"
						class:active={searchTab === 'parts'}
						onclick={() => searchTab = 'parts'}
					>
						Parts ({partsCount})
					</button>
				</div>

				{#if searchTab === 'sequences'}
					{#if seqRows.length > 0}
						<DataTable rows={seqRows} columns={seqColumns} actions={seqActions} defaultPageSize={10} />
					{:else}
						<div class="no-results">No matching sequences</div>
					{/if}
				{:else}
					{#if partsRows.length > 0}
						<DataTable rows={partsRows} columns={partsColumns} actions={partsActions} defaultPageSize={10} />
					{:else}
						<div class="no-results">No matching parts</div>
					{/if}
				{/if}
			</div>
		{:else if searchResults?.error}
			<div class="error">{searchResults.error}</div>
		{/if}

		<!-- BLAST section -->
		<div class="blast-section">
			<h4>BLAST</h4>
			<textarea
				bind:value={blastQuery}
				onkeydown={handleBlastKeydown}
				placeholder="Paste DNA/protein sequence..."
				rows="4"
				class="blast-input"
			></textarea>
			<button
				class="blast-btn"
				onclick={doBlast}
				disabled={blastLoading || !blastQuery.trim()}
			>
				{blastLoading ? 'Running...' : 'Run BLAST'}
			</button>
		</div>

		<!-- BLAST results -->
		{#if blastResults && !blastResults.error}
			<div class="results-section">
				{#if blastResults.hits?.length > 0}
					<div class="blast-heading">{blastResults.program} -- {blastResults.total} hit(s)</div>
					<div class="tab-bar">
						<button
							class="tab-btn"
							class:active={blastTab === 'sequences'}
							onclick={() => blastTab = 'sequences'}
						>
							Sequences ({blastSeqHits.length})
						</button>
						<button
							class="tab-btn"
							class:active={blastTab === 'parts'}
							onclick={() => blastTab = 'parts'}
						>
							Parts ({blastPartHits.length})
						</button>
					</div>
					{#if blastTab === 'sequences'}
						{#if blastSeqHits.length > 0}
							<DataTable rows={blastSeqHits} columns={blastSeqColumns} actions={blastSeqActions} defaultPageSize={10} />
						{:else}
							<div class="no-results">No sequence hits</div>
						{/if}
					{:else}
						{#if blastPartHits.length > 0}
							<DataTable rows={blastPartHits} columns={blastPartColumns} actions={blastPartActions} defaultPageSize={10} />
						{:else}
							<div class="no-results">No part hits</div>
						{/if}
					{/if}
				{:else}
					<div class="no-results">No BLAST hits</div>
				{/if}
			</div>
		{:else if blastResults?.error}
			<div class="error">{blastResults.error}</div>
		{/if}
	</div>
</div>

<style>
	.search-panel {
		width: 450px;
		background: var(--bg-sidebar);
		border-left: 1px solid var(--border);
		display: flex;
		flex-direction: column;
		flex-shrink: 0;
		height: 100%;
		overflow: hidden;
	}

	.panel-header {
		padding: 0.75rem 1rem;
		border-bottom: 1px solid var(--border);
	}

	.panel-header h3 {
		margin: 0;
		font-size: 0.85rem;
		font-weight: 700;
		text-transform: uppercase;
		color: var(--text-faint);
		letter-spacing: 0.05em;
	}

	.panel-body {
		flex: 1;
		overflow-y: auto;
		padding: 0.75rem;
		display: flex;
		flex-direction: column;
		gap: 0.75rem;
	}

	.search-section {
		position: relative;
	}

	.search-input {
		width: 100%;
		padding: 0.5rem 0.75rem;
		border: 1px solid var(--border);
		background: var(--bg-surface);
		border-radius: 8px;
		font-size: 0.85rem;
		color: var(--text);
		outline: none;
		font-family: inherit;
		box-sizing: border-box;
	}

	.search-input:focus {
		border-color: var(--color-accent);
	}

	.search-input::placeholder {
		color: var(--text-placeholder);
	}

	.loading {
		font-size: 0.75rem;
		color: var(--text-faint);
		padding: 0.25rem 0;
	}

	/* Tab toggle */
	.tab-bar {
		display: flex;
		gap: 2px;
		background: var(--bg-app);
		border-radius: 6px;
		padding: 2px;
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

	.results-section {
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
	}

	.no-results {
		font-size: 0.8rem;
		color: var(--text-placeholder);
		padding: 0.5rem;
		text-align: center;
	}

	.error {
		font-size: 0.8rem;
		color: var(--color-err);
		padding: 0.5rem;
	}

	.blast-section {
		display: flex;
		flex-direction: column;
		gap: 0.4rem;
		border-top: 1px solid var(--border);
		padding-top: 0.75rem;
	}

	.blast-section h4 {
		margin: 0;
		font-size: 0.75rem;
		font-weight: 600;
		color: var(--text-muted);
	}

	.blast-heading {
		font-size: 0.75rem;
		color: var(--text-muted);
		font-weight: 600;
	}

	.blast-input {
		width: 100%;
		padding: 0.5rem 0.75rem;
		border: 1px solid var(--border);
		background: var(--bg-surface);
		border-radius: 8px;
		font-size: 0.8rem;
		font-family: monospace;
		color: var(--text);
		outline: none;
		resize: vertical;
		box-sizing: border-box;
	}

	.blast-input:focus {
		border-color: var(--color-accent);
	}

	.blast-input::placeholder {
		color: var(--text-placeholder);
	}

	.blast-btn {
		padding: 0.4rem 0.75rem;
		border: 1px solid var(--border);
		background: var(--bg-surface);
		border-radius: 6px;
		cursor: pointer;
		font-size: 0.8rem;
		color: var(--text-secondary);
		font-family: inherit;
		transition: background 0.15s;
		align-self: flex-end;
	}

	.blast-btn:hover:not(:disabled) {
		background: var(--bg-hover);
	}

	.blast-btn:disabled {
		opacity: 0.4;
		cursor: default;
	}

	/* DataTable in panel context: ensure it doesn't overflow */
	:global(.search-panel .table-scroll) {
		font-size: 0.78rem;
	}
</style>
