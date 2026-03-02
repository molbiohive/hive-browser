<script>
	import { sendMessage } from '$lib/stores/chat.ts';

	let searchQuery = $state('');
	let blastQuery = $state('');
	let searchResults = $state(null);
	let blastResults = $state(null);
	let searchLoading = $state(false);
	let blastLoading = $state(false);
	let _debounceTimer = null; // plain var -- must NOT be $state to avoid retriggering $effect

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

	function viewProfile(sid) {
		sendMessage(`//profile ${JSON.stringify({ sid })}`);
	}

	function viewParts(pid) {
		sendMessage(`//parts ${JSON.stringify({ pid })}`);
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
		<!-- Text search -->
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

		<!-- Search results -->
		{#if searchResults && !searchResults.error}
			<div class="results-section">
				{#if searchResults.results?.length > 0}
					<div class="results-group">
						<h4>Sequences ({searchResults.total})</h4>
						{#each searchResults.results as row}
							<button class="result-row" onclick={() => viewProfile(row.sid)}>
								<span class="result-name">{row.name}</span>
								<span class="result-meta">{row.size_bp}bp {row.topology}</span>
								<span class="result-score">{row.score?.toFixed(2)}</span>
							</button>
						{/each}
					</div>
				{/if}

				{#if searchResults.parts?.length > 0}
					<div class="results-group">
						<h4>Parts ({searchResults.parts_total})</h4>
						{#each searchResults.parts as part}
							<button class="result-row" onclick={() => viewParts(part.pid)}>
								<span class="result-name">{part.names?.join(', ')}</span>
								<span class="result-meta">{part.types?.join(', ')} {part.length ? part.length + 'bp' : ''}</span>
								<span class="result-score">{part.instance_count} inst</span>
							</button>
						{/each}
					</div>
				{/if}

				{#if searchResults.total === 0 && searchResults.parts_total === 0}
					<div class="no-results">No results</div>
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
					<div class="results-group">
						<h4>BLAST Hits ({blastResults.total})</h4>
						{#each blastResults.hits as hit}
							<button
								class="result-row"
								onclick={() => { if (hit.sid) viewProfile(hit.sid); }}
							>
								<span class="result-name">{hit.subject}</span>
								<span class="result-meta">{hit.identity?.toFixed(1)}% id, {hit.alignment_length}bp</span>
								<span class="result-score">E={hit.evalue?.toExponential(1)}</span>
							</button>
						{/each}
					</div>
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
		width: 380px;
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

	.results-section {
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
	}

	.results-group h4 {
		margin: 0 0 0.25rem;
		font-size: 0.75rem;
		font-weight: 600;
		color: var(--text-muted);
	}

	.result-row {
		width: 100%;
		display: flex;
		align-items: center;
		gap: 0.5rem;
		padding: 0.4rem 0.5rem;
		border: none;
		background: transparent;
		border-radius: 4px;
		cursor: pointer;
		text-align: left;
		font-family: inherit;
		font-size: 0.8rem;
		color: var(--text);
		transition: background 0.1s;
	}

	.result-row:hover {
		background: var(--bg-hover);
	}

	.result-name {
		flex: 1;
		min-width: 0;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
		font-weight: 500;
	}

	.result-meta {
		font-size: 0.72rem;
		color: var(--text-faint);
		white-space: nowrap;
	}

	.result-score {
		font-size: 0.7rem;
		color: var(--text-placeholder);
		white-space: nowrap;
		font-variant-numeric: tabular-nums;
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
</style>
