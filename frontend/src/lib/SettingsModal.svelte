<script>
	import { onMount } from 'svelte';
	import { currentUser } from '$lib/stores/user.ts';
	import { setPreference } from '$lib/stores/chat.ts';

	let { onClose } = $props();

	// ── State ──

	let collections = $state([]);
	let loading = $state(true);

	// Create/edit mode
	let mode = $state('list'); // 'list' | 'create' | 'edit'
	let editId = $state(null);
	let formName = $state('');
	let formType = $state('enzymes');

	// Item picker state
	let allItems = $state([]);
	let itemsLoading = $state(false);
	let searchQuery = $state('');
	let selected = $state(new Set());
	let _debounceTimer = null;

	const enzymeCollectionId = $derived($currentUser?.preferences?.enzyme_collection_id ?? null);
	const primerCollectionId = $derived($currentUser?.preferences?.primer_collection_id ?? null);

	const filteredItems = $derived.by(() => {
		if (!searchQuery.trim()) return allItems;
		const q = searchQuery.toLowerCase();
		return allItems.filter(item => {
			const name = (item.name || '').toLowerCase();
			const site = (item.site || '').toLowerCase();
			return name.includes(q) || site.includes(q);
		});
	});

	const selectedCount = $derived(selected.size);

	onMount(fetchCollections);

	// ── API ──

	async function fetchCollections() {
		loading = true;
		try {
			const res = await fetch('/api/collections');
			if (res.ok) collections = await res.json();
		} catch (e) {
			console.error('Failed to fetch collections:', e);
		}
		loading = false;
	}

	async function fetchItems(type) {
		itemsLoading = true;
		allItems = [];
		try {
			const endpoint = type === 'enzymes' ? '/api/enzymes' : '/api/primers';
			const res = await fetch(endpoint);
			if (res.ok) allItems = await res.json();
		} catch (e) {
			console.error('Failed to fetch items:', e);
		}
		itemsLoading = false;
	}

	// ── Collection selection ──

	function enzymeCollections() {
		return collections.filter(c => c.set_type === 'enzymes');
	}

	function primerCollections() {
		return collections.filter(c => c.set_type === 'primers');
	}

	function selectEnzymeCollection(e) {
		const val = e.target.value;
		setPreference('enzyme_collection_id', val ? parseInt(val) : null);
	}

	function selectPrimerCollection(e) {
		const val = e.target.value;
		setPreference('primer_collection_id', val ? parseInt(val) : null);
	}

	// ── Create/Edit ──

	function startCreate() {
		mode = 'create';
		formName = '';
		formType = 'enzymes';
		selected = new Set();
		searchQuery = '';
		fetchItems('enzymes');
	}

	function startEdit(col) {
		mode = 'edit';
		editId = col.id;
		formName = col.name;
		formType = col.set_type;
		selected = new Set(col.items.map(String));
		searchQuery = '';
		fetchItems(col.set_type);
	}

	function cancelForm() {
		mode = 'list';
		editId = null;
		allItems = [];
		searchQuery = '';
	}

	function handleTypeChange(e) {
		formType = e.target.value;
		selected = new Set();
		searchQuery = '';
		fetchItems(formType);
	}

	function toggleItem(key) {
		const next = new Set(selected);
		if (next.has(key)) {
			next.delete(key);
		} else {
			next.add(key);
		}
		selected = next;
	}

	function toggleAll() {
		if (selected.size === filteredItems.length) {
			// Deselect all visible
			const next = new Set(selected);
			for (const item of filteredItems) {
				next.delete(itemKey(item));
			}
			selected = next;
		} else {
			// Select all visible
			const next = new Set(selected);
			for (const item of filteredItems) {
				next.add(itemKey(item));
			}
			selected = next;
		}
	}

	function itemKey(item) {
		return formType === 'enzymes' ? item.name : String(item.id);
	}

	async function saveCollection() {
		if (!formName.trim() || selected.size === 0) return;
		const items = [...selected];
		try {
			if (mode === 'create') {
				await fetch('/api/collections', {
					method: 'POST',
					headers: { 'Content-Type': 'application/json' },
					body: JSON.stringify({ name: formName, set_type: formType, items }),
				});
			} else {
				await fetch(`/api/collections/${editId}`, {
					method: 'PUT',
					headers: { 'Content-Type': 'application/json' },
					body: JSON.stringify({ name: formName, items }),
				});
			}
			cancelForm();
			await fetchCollections();
		} catch (e) {
			console.error('Failed to save collection:', e);
		}
	}

	async function deleteCollection(id) {
		try {
			await fetch(`/api/collections/${id}`, { method: 'DELETE' });
			await fetchCollections();
		} catch (e) {
			console.error('Failed to delete collection:', e);
		}
	}
</script>

<!-- svelte-ignore a11y_no_static_element_interactions -->
<div class="modal-overlay" onclick={onClose} onkeydown={(e) => { if (e.key === 'Escape') onClose(); }}>
	<!-- svelte-ignore a11y_no_static_element_interactions -->
	<div class="modal" class:wide={mode !== 'list'} onclick={(e) => e.stopPropagation()} onkeydown={() => {}}>
		<div class="modal-header">
			<h2>{mode === 'list' ? 'Settings' : mode === 'create' ? 'New Collection' : 'Edit Collection'}</h2>
			<button class="close-btn" onclick={mode === 'list' ? onClose : cancelForm}>{mode === 'list' ? '\u00d7' : '\u2190'}</button>
		</div>

		<div class="modal-body">
			{#if mode === 'list'}
				<!-- Active collection dropdowns -->
				<section>
					<h3>Active Collections</h3>
					<div class="pref-row">
						<label for="enzyme-col">Enzyme Collection</label>
						<select id="enzyme-col" onchange={selectEnzymeCollection}>
							<option value="">All enzymes</option>
							{#each enzymeCollections() as col}
								<option value={col.id} selected={enzymeCollectionId === col.id}>{col.name} ({col.items.length})</option>
							{/each}
						</select>
					</div>
					<div class="pref-row">
						<label for="primer-col">Primer Collection</label>
						<select id="primer-col" onchange={selectPrimerCollection}>
							<option value="">All primers</option>
							{#each primerCollections() as col}
								<option value={col.id} selected={primerCollectionId === col.id}>{col.name} ({col.items.length})</option>
							{/each}
						</select>
					</div>
				</section>

				<!-- Collection list -->
				<section>
					<div class="section-header">
						<h3>Manage Collections</h3>
						<button class="add-btn" onclick={startCreate}>+ New</button>
					</div>

					{#if loading}
						<div class="placeholder">Loading...</div>
					{:else if collections.length === 0}
						<div class="placeholder">No collections yet</div>
					{:else}
						<div class="collection-list">
							{#each collections as col}
								<div class="collection-item">
									<div class="col-info">
										<span class="col-name">{col.name}</span>
										<span class="col-meta">{col.set_type} &middot; {col.items.length} items{col.is_default ? ' &middot; default' : ''}</span>
									</div>
									<div class="col-actions">
										<button class="icon-btn" onclick={() => startEdit(col)} title="Edit">
											<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M11 4H4a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 013 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>
										</button>
										{#if !col.is_default}
											<button class="icon-btn danger" onclick={() => deleteCollection(col.id)} title="Delete">&times;</button>
										{/if}
									</div>
								</div>
							{/each}
						</div>
					{/if}
				</section>

			{:else}
				<!-- Create / Edit form with table picker -->
				<div class="form-top">
					<div class="form-row">
						<label for="col-name">Name</label>
						<input id="col-name" type="text" bind:value={formName} placeholder="Collection name" />
					</div>
					{#if mode === 'create'}
						<div class="form-row">
							<label for="col-type">Type</label>
							<select id="col-type" value={formType} onchange={handleTypeChange}>
								<option value="enzymes">Enzymes</option>
								<option value="primers">Primers</option>
							</select>
						</div>
					{/if}
				</div>

				<!-- Search + count -->
				<div class="picker-toolbar">
					<input
						type="text"
						class="picker-search"
						bind:value={searchQuery}
						placeholder={formType === 'enzymes' ? 'Search enzymes...' : 'Search primers...'}
					/>
					<span class="picker-count">{selectedCount} selected</span>
				</div>

				<!-- Item table -->
				<div class="picker-table-wrap">
					{#if itemsLoading}
						<div class="placeholder">Loading...</div>
					{:else if allItems.length === 0}
						<div class="placeholder">No {formType} found</div>
					{:else}
						<table class="picker-table">
							<thead>
								<tr>
									<th class="check-col">
										<input
											type="checkbox"
											checked={filteredItems.length > 0 && filteredItems.every(i => selected.has(itemKey(i)))}
											onchange={toggleAll}
										/>
									</th>
									{#if formType === 'enzymes'}
										<th>Name</th>
										<th>Site</th>
										<th>Length</th>
									{:else}
										<th>ID</th>
										<th>Name</th>
										<th>Length</th>
									{/if}
								</tr>
							</thead>
							<tbody>
								{#each filteredItems as item}
									{@const key = itemKey(item)}
									<tr class:selected={selected.has(key)} onclick={() => toggleItem(key)}>
										<td class="check-col">
											<input type="checkbox" checked={selected.has(key)} onclick={(e) => e.stopPropagation()} onchange={() => toggleItem(key)} />
										</td>
										{#if formType === 'enzymes'}
											<td class="item-name">{item.name}</td>
											<td class="item-site">{item.site}</td>
											<td>{item.length}</td>
										{:else}
											<td>{item.id}</td>
											<td class="item-name">{item.name}</td>
											<td>{item.length}</td>
										{/if}
									</tr>
								{/each}
							</tbody>
						</table>
					{/if}
				</div>

				<div class="form-actions">
					<button class="btn-secondary" onclick={cancelForm}>Cancel</button>
					<button class="btn-primary" onclick={saveCollection} disabled={!formName.trim() || selected.size === 0}>
						{mode === 'create' ? 'Create' : 'Save'} ({selectedCount})
					</button>
				</div>
			{/if}
		</div>
	</div>
</div>

<style>
	.modal-overlay {
		position: fixed;
		inset: 0;
		background: rgba(0, 0, 0, 0.5);
		display: flex;
		align-items: center;
		justify-content: center;
		z-index: 1000;
	}

	.modal {
		background: var(--bg-surface);
		border: 1px solid var(--border);
		border-radius: 12px;
		width: 480px;
		max-height: 80vh;
		display: flex;
		flex-direction: column;
		box-shadow: 0 8px 32px var(--shadow);
		transition: width 0.2s;
	}

	.modal.wide {
		width: 560px;
	}

	.modal-header {
		display: flex;
		justify-content: space-between;
		align-items: center;
		padding: 1rem 1.25rem;
		border-bottom: 1px solid var(--border);
	}

	.modal-header h2 {
		margin: 0;
		font-size: 1rem;
		font-weight: 600;
	}

	.close-btn {
		background: none;
		border: none;
		font-size: 1.4rem;
		cursor: pointer;
		color: var(--text-faint);
		padding: 0;
		line-height: 1;
	}

	.close-btn:hover {
		color: var(--text);
	}

	.modal-body {
		padding: 1.25rem;
		overflow-y: auto;
		display: flex;
		flex-direction: column;
		gap: 1rem;
	}

	section h3 {
		margin: 0 0 0.75rem;
		font-size: 0.82rem;
		text-transform: uppercase;
		color: var(--text-faint);
		letter-spacing: 0.05em;
	}

	.section-header {
		display: flex;
		justify-content: space-between;
		align-items: center;
		margin-bottom: 0.75rem;
	}

	.section-header h3 {
		margin: 0;
	}

	.pref-row {
		display: flex;
		justify-content: space-between;
		align-items: center;
		margin-bottom: 0.5rem;
	}

	.pref-row label {
		font-size: 0.85rem;
		color: var(--text-secondary);
	}

	.pref-row select {
		padding: 0.3rem 0.5rem;
		border: 1px solid var(--border);
		border-radius: 6px;
		background: var(--bg-app);
		color: var(--text);
		font-size: 0.82rem;
		min-width: 180px;
	}

	.add-btn {
		background: none;
		border: 1px solid var(--border);
		border-radius: 6px;
		padding: 0.25rem 0.6rem;
		font-size: 0.78rem;
		cursor: pointer;
		color: var(--text-secondary);
	}

	.add-btn:hover {
		background: var(--bg-hover);
	}

	.placeholder {
		font-size: 0.85rem;
		color: var(--text-placeholder);
		padding: 1rem 0;
		text-align: center;
	}

	.collection-list {
		display: flex;
		flex-direction: column;
		gap: 4px;
	}

	.collection-item {
		display: flex;
		justify-content: space-between;
		align-items: center;
		padding: 0.5rem;
		border-radius: 6px;
		transition: background 0.1s;
	}

	.collection-item:hover {
		background: var(--bg-hover);
	}

	.col-info {
		display: flex;
		flex-direction: column;
		gap: 2px;
	}

	.col-name {
		font-size: 0.85rem;
		color: var(--text);
	}

	.col-meta {
		font-size: 0.72rem;
		color: var(--text-placeholder);
	}

	.col-actions {
		display: flex;
		gap: 4px;
	}

	.icon-btn {
		background: none;
		border: none;
		cursor: pointer;
		color: var(--text-faint);
		padding: 0.2rem;
		border-radius: 4px;
		display: flex;
		align-items: center;
	}

	.icon-btn:hover {
		color: var(--text);
		background: var(--bg-hover);
	}

	.icon-btn.danger:hover {
		color: var(--color-err);
	}

	/* ── Create/Edit form ── */

	.form-top {
		display: flex;
		gap: 0.75rem;
	}

	.form-row {
		display: flex;
		flex-direction: column;
		gap: 0.25rem;
		flex: 1;
	}

	.form-row label {
		font-size: 0.75rem;
		color: var(--text-faint);
		text-transform: uppercase;
		letter-spacing: 0.05em;
	}

	.form-row input, .form-row select {
		padding: 0.4rem 0.5rem;
		border: 1px solid var(--border);
		border-radius: 6px;
		background: var(--bg-app);
		color: var(--text);
		font-size: 0.85rem;
		font-family: inherit;
	}

	.picker-toolbar {
		display: flex;
		align-items: center;
		gap: 0.75rem;
	}

	.picker-search {
		flex: 1;
		padding: 0.45rem 0.75rem;
		border: 1px solid var(--border);
		border-radius: 8px;
		background: var(--bg-app);
		color: var(--text);
		font-size: 0.85rem;
		font-family: inherit;
		outline: none;
	}

	.picker-search:focus {
		border-color: var(--color-accent);
	}

	.picker-count {
		font-size: 0.78rem;
		color: var(--text-faint);
		white-space: nowrap;
	}

	.picker-table-wrap {
		max-height: 320px;
		overflow-y: auto;
		border: 1px solid var(--border);
		border-radius: 8px;
	}

	.picker-table {
		width: 100%;
		border-collapse: collapse;
		font-size: 0.82rem;
	}

	.picker-table thead {
		position: sticky;
		top: 0;
		background: var(--bg-surface);
		z-index: 1;
	}

	.picker-table th {
		text-align: left;
		padding: 0.4rem 0.6rem;
		font-weight: 600;
		color: var(--text-faint);
		font-size: 0.75rem;
		text-transform: uppercase;
		letter-spacing: 0.03em;
		border-bottom: 1px solid var(--border);
	}

	.picker-table td {
		padding: 0.35rem 0.6rem;
		color: var(--text);
		border-bottom: 1px solid var(--border-muted, var(--border));
	}

	.picker-table tbody tr {
		cursor: pointer;
		transition: background 0.1s;
	}

	.picker-table tbody tr:hover {
		background: var(--bg-hover);
	}

	.picker-table tbody tr.selected {
		background: var(--bg-active);
	}

	.check-col {
		width: 32px;
		text-align: center;
	}

	.item-name {
		font-weight: 500;
	}

	.item-site {
		font-family: 'SF Mono', 'Menlo', 'Monaco', monospace;
		font-size: 0.78rem;
		color: var(--text-secondary);
	}

	.form-actions {
		display: flex;
		gap: 0.5rem;
		justify-content: flex-end;
		padding-top: 0.25rem;
	}

	.btn-primary, .btn-secondary {
		padding: 0.4rem 0.85rem;
		border-radius: 6px;
		font-size: 0.82rem;
		cursor: pointer;
		border: 1px solid var(--border);
		font-family: inherit;
	}

	.btn-primary {
		background: var(--btn-bg);
		color: var(--btn-fg);
		border-color: transparent;
	}

	.btn-primary:disabled {
		opacity: 0.4;
		cursor: default;
	}

	.btn-secondary {
		background: var(--bg-surface);
		color: var(--text-secondary);
	}

	.btn-primary:hover:not(:disabled) {
		opacity: 0.9;
	}

	.btn-secondary:hover {
		background: var(--bg-hover);
	}
</style>
