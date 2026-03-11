<script>
	import { onMount } from 'svelte';
	import { currentUser } from '$lib/stores/user.ts';
	import { setPreference } from '$lib/stores/chat.ts';

	let { onClose } = $props();

	let collections = $state([]);
	let loading = $state(true);
	let editingId = $state(null);
	let editName = $state('');
	let editItems = $state('');
	let creating = $state(false);
	let newName = $state('');
	let newType = $state('enzymes');
	let newItems = $state('');

	const enzymeCollectionId = $derived($currentUser?.preferences?.enzyme_collection_id ?? null);
	const primerCollectionId = $derived($currentUser?.preferences?.primer_collection_id ?? null);

	onMount(fetchCollections);

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

	function startEdit(col) {
		editingId = col.id;
		editName = col.name;
		editItems = col.items.join(', ');
	}

	function cancelEdit() {
		editingId = null;
	}

	async function saveEdit(id) {
		const items = editItems.split(',').map(s => s.trim()).filter(Boolean);
		try {
			const res = await fetch(`/api/collections/${id}`, {
				method: 'PUT',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ name: editName, items }),
			});
			if (res.ok) {
				editingId = null;
				await fetchCollections();
			}
		} catch (e) {
			console.error('Failed to update collection:', e);
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

	async function createCollection() {
		const items = newItems.split(',').map(s => s.trim()).filter(Boolean);
		if (!newName.trim()) return;
		try {
			const res = await fetch('/api/collections', {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ name: newName, set_type: newType, items }),
			});
			if (res.ok) {
				creating = false;
				newName = '';
				newItems = '';
				await fetchCollections();
			}
		} catch (e) {
			console.error('Failed to create collection:', e);
		}
	}
</script>

<!-- svelte-ignore a11y_no_static_element_interactions -->
<div class="modal-overlay" onclick={onClose} onkeydown={(e) => { if (e.key === 'Escape') onClose(); }}>
	<!-- svelte-ignore a11y_no_static_element_interactions -->
	<div class="modal" onclick={(e) => e.stopPropagation()} onkeydown={() => {}}>
		<div class="modal-header">
			<h2>Settings</h2>
			<button class="close-btn" onclick={onClose}>&times;</button>
		</div>

		<div class="modal-body">
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

			<section>
				<div class="section-header">
					<h3>Manage Collections</h3>
					<button class="add-btn" onclick={() => creating = true}>+ New</button>
				</div>

				{#if creating}
					<div class="create-form">
						<input type="text" bind:value={newName} placeholder="Collection name" />
						<select bind:value={newType}>
							<option value="enzymes">Enzymes</option>
							<option value="primers">Primers</option>
						</select>
						<textarea bind:value={newItems} placeholder="Items (comma-separated)" rows="2"></textarea>
						<div class="form-actions">
							<button class="btn-secondary" onclick={() => creating = false}>Cancel</button>
							<button class="btn-primary" onclick={createCollection}>Create</button>
						</div>
					</div>
				{/if}

				{#if loading}
					<div class="placeholder">Loading...</div>
				{:else if collections.length === 0}
					<div class="placeholder">No collections yet</div>
				{:else}
					<div class="collection-list">
						{#each collections as col}
							<div class="collection-item">
								{#if editingId === col.id}
									<div class="edit-form">
										<input type="text" bind:value={editName} />
										<textarea bind:value={editItems} rows="2"></textarea>
										<div class="form-actions">
											<button class="btn-secondary" onclick={cancelEdit}>Cancel</button>
											<button class="btn-primary" onclick={() => saveEdit(col.id)}>Save</button>
										</div>
									</div>
								{:else}
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
								{/if}
							</div>
						{/each}
					</div>
				{/if}
			</section>
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
		gap: 1.5rem;
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

	.create-form, .edit-form {
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
		margin-bottom: 0.75rem;
		padding: 0.75rem;
		border: 1px solid var(--border);
		border-radius: 8px;
		background: var(--bg-app);
	}

	.create-form input, .create-form textarea, .create-form select,
	.edit-form input, .edit-form textarea {
		padding: 0.4rem 0.5rem;
		border: 1px solid var(--border);
		border-radius: 6px;
		background: var(--bg-surface);
		color: var(--text);
		font-size: 0.82rem;
		font-family: inherit;
	}

	.create-form textarea, .edit-form textarea {
		resize: vertical;
	}

	.form-actions {
		display: flex;
		gap: 0.5rem;
		justify-content: flex-end;
	}

	.btn-primary, .btn-secondary {
		padding: 0.35rem 0.75rem;
		border-radius: 6px;
		font-size: 0.8rem;
		cursor: pointer;
		border: 1px solid var(--border);
	}

	.btn-primary {
		background: var(--btn-bg);
		color: var(--btn-fg);
		border-color: transparent;
	}

	.btn-secondary {
		background: var(--bg-surface);
		color: var(--text-secondary);
	}

	.btn-primary:hover {
		opacity: 0.9;
	}

	.btn-secondary:hover {
		background: var(--bg-hover);
	}
</style>
