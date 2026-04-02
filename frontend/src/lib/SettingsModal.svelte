<script>
	import { onMount } from 'svelte';
	import { currentUser } from '$lib/stores/user.ts';
	import { setPreference } from '$lib/stores/chat.ts';
	import PickerTable from '$lib/PickerTable.svelte';

	let { onClose } = $props();

	// ── State ──

	let collections = $state([]);
	let skills = $state([]);
	let loading = $state(true);

	// Create/edit mode
	let mode = $state('list'); // 'list' | 'create' | 'edit' | 'view-skill' | 'create-skill' | 'edit-skill'
	let editId = $state(null);
	let formName = $state('');
	let formType = $state('enzymes');

	// Skill form state
	let skillName = $state('');
	let skillContent = $state('');  // kept for view-skill mode
	let editSkillId = $state(null);
	let skillIssues = $state([]);

	// Structured skill fields
	let skillWhen = $state('');
	let skillWorkflow = $state('');
	let skillReport = $state('');
	let skillRules = $state('');
	let skillTools = $state(new Set());
	let availableTools = $state([]);
	let toolPickerFiltered = $state([]);

	// Item picker state
	let allItems = $state([]);
	let itemsLoading = $state(false);
	let pickerFiltered = $state([]);
	let selected = $state(new Set());
	const enzymeCollectionId = $derived($currentUser?.preferences?.enzyme_collection_id ?? null);
	const primerCollectionId = $derived($currentUser?.preferences?.primer_collection_id ?? null);

	const selectedCount = $derived(selected.size);

	onMount(() => { fetchCollections(); fetchSkills(); fetchTools(); });

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

	// ── Collection create/edit ──

	function startCreate() {
		mode = 'create';
		formName = '';
		formType = 'enzymes';
		selected = new Set();
		fetchItems('enzymes');
	}

	function startEdit(col) {
		mode = 'edit';
		editId = col.id;
		formName = col.name;
		formType = col.set_type;
		selected = new Set(col.items.map(String));
		fetchItems(col.set_type);
	}

	function cancelForm() {
		mode = 'list';
		editId = null;
		allItems = [];
	}

	function handleTypeChange(e) {
		formType = e.target.value;
		selected = new Set();
		fetchItems(formType);
	}

	function toggleItem(key) {
		const next = new Set(selected);
		if (next.has(key)) next.delete(key);
		else next.add(key);
		selected = next;
	}

	function toggleAll() {
		const allKeys = pickerFiltered.map(itemKey);
		const allSelected = allKeys.length > 0 && allKeys.every(k => selected.has(k));
		const next = new Set(selected);
		for (const k of allKeys) {
			if (allSelected) next.delete(k);
			else next.add(k);
		}
		selected = next;
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

	// ── Skills API ──

	async function fetchSkills() {
		try {
			const res = await fetch('/api/skills');
			if (res.ok) skills = await res.json();
		} catch (e) {
			console.error('Failed to fetch skills:', e);
		}
	}

	function startCreateSkill() {
		mode = 'create-skill';
		skillName = '';
		skillContent = '';
		skillWhen = '';
		skillWorkflow = '';
		skillReport = '';
		skillRules = '';
		skillTools = new Set();
		skillIssues = [];
	}

	function viewSkill(sk) {
		mode = 'view-skill';
		editSkillId = sk.id;
		skillName = sk.name;
		skillContent = sk.content;
		skillIssues = sk.issues || [];
	}

	function startEditSkill(sk) {
		mode = 'edit-skill';
		editSkillId = sk.id;
		skillName = sk.name;
		skillContent = sk.content;
		parseSkillContent(sk.content);
		skillIssues = sk.issues || [];
	}

	function cancelSkillForm() {
		mode = 'list';
		editSkillId = null;
		skillName = '';
		skillContent = '';
		skillWhen = '';
		skillWorkflow = '';
		skillReport = '';
		skillRules = '';
		skillTools = new Set();
		skillIssues = [];
	}

	async function saveSkill() {
		if (!skillName.trim()) return;
		const content = assembleSkillContent();
		try {
			let res;
			if (mode === 'create-skill') {
				res = await fetch('/api/skills', {
					method: 'POST',
					headers: { 'Content-Type': 'application/json' },
					body: JSON.stringify({ name: skillName.trim(), content }),
				});
			} else {
				res = await fetch(`/api/skills/${editSkillId}`, {
					method: 'PUT',
					headers: { 'Content-Type': 'application/json' },
					body: JSON.stringify({ name: skillName.trim(), content }),
				});
			}
			if (!res.ok) return;
			const saved = await res.json();
			if (saved.issues?.length) {
				skillIssues = saved.issues;
				editSkillId = saved.id;
				mode = 'edit-skill';
			} else {
				cancelSkillForm();
			}
			await fetchSkills();
		} catch (e) {
			console.error('Failed to save skill:', e);
		}
	}

	async function deleteSkill(id) {
		try {
			await fetch(`/api/skills/${id}`, { method: 'DELETE' });
			await fetchSkills();
		} catch (e) {
			console.error('Failed to delete skill:', e);
		}
	}

	async function fetchTools() {
		try {
			const res = await fetch('/api/tools');
			if (res.ok) availableTools = await res.json();
		} catch (e) {
			console.error('Failed to fetch tools:', e);
		}
	}

	function parseSkillContent(content) {
		skillWhen = '';
		skillWorkflow = '';
		skillReport = '';
		skillRules = '';
		skillTools = new Set();

		const sections = content.split(/^## /m).slice(1);
		for (const sec of sections) {
			const nl = sec.indexOf('\n');
			if (nl === -1) continue;
			const heading = sec.slice(0, nl).trim().toLowerCase();
			let body = sec.slice(nl + 1).trim();

			if (heading === 'when') {
				skillWhen = body;
			} else if (heading === 'tools') {
				const names = body.split('\n')
					.map(l => l.replace(/^[-*]\s*/, '').trim())
					.filter(Boolean);
				skillTools = new Set(names);
			} else if (heading === 'workflow') {
				skillWorkflow = body;
			} else if (heading === 'report') {
				body = body.replace(/^```python\n?/, '').replace(/\n?```$/, '');
				skillReport = body;
			} else if (heading === 'rules') {
				skillRules = body;
			}
		}
	}

	function assembleSkillContent() {
		const parts = [`# ${skillName.trim()}`];

		if (skillWhen.trim()) parts.push(`## When\n${skillWhen.trim()}`);

		if (skillTools.size > 0) {
			const list = [...skillTools].map(t => `- ${t}`).join('\n');
			parts.push(`## Tools\n${list}`);
		}

		if (skillWorkflow.trim()) parts.push(`## Workflow\n${skillWorkflow.trim()}`);

		if (skillReport.trim()) parts.push(`## Report\n\`\`\`python\n${skillReport.trim()}\n\`\`\``);

		if (skillRules.trim()) parts.push(`## Rules\n${skillRules.trim()}`);

		return parts.join('\n\n') + '\n';
	}

	const skillToolCount = $derived(skillTools.size);

	function toggleSkillTool(name) {
		const next = new Set(skillTools);
		if (next.has(name)) next.delete(name);
		else next.add(name);
		skillTools = next;
	}

	function toggleAllSkillTools() {
		const allNames = toolPickerFiltered.map(t => t.name);
		const allSelected = allNames.length > 0 && allNames.every(n => skillTools.has(n));
		const next = new Set(skillTools);
		for (const n of allNames) {
			if (allSelected) next.delete(n);
			else next.add(n);
		}
		skillTools = next;
	}

	function isSkillMode(m) {
		return m === 'view-skill' || m === 'create-skill' || m === 'edit-skill';
	}
</script>

<!-- svelte-ignore a11y_no_static_element_interactions -->
<div class="modal-overlay" onclick={onClose} onkeydown={(e) => { if (e.key === 'Escape') onClose(); }}>
	<!-- svelte-ignore a11y_no_static_element_interactions -->
	<div class="modal" class:wide={mode !== 'list'} onclick={(e) => e.stopPropagation()} onkeydown={() => {}}>
		<div class="modal-header">
			<h2>{
				mode === 'list' ? 'Settings'
				: mode === 'create' ? 'New Collection'
				: mode === 'edit' ? 'Edit Collection'
				: mode === 'view-skill' ? skillName
				: mode === 'create-skill' ? 'New Skill'
				: 'Edit Skill'
			}</h2>
			<button class="close-btn" onclick={
				mode === 'list' ? onClose
				: isSkillMode(mode) ? cancelSkillForm
				: cancelForm
			}>{mode === 'list' ? '\u00d7' : '\u2190'}</button>
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
						<PickerTable
							items={collections}
							searchFields={['name']}
							placeholder="Search collections..."
							onRowClick={(col) => startEdit(col)}
						>
							{#snippet head()}
								<tr>
									<th>Name</th>
									<th>Type</th>
									<th>Items</th>
									<th class="actions-col"></th>
								</tr>
							{/snippet}
							{#snippet row(col)}
								<td class="item-name">{col.name}</td>
								<td>{col.set_type}</td>
								<td>{col.items.length}</td>
								<td class="actions-col">
									{#if !col.is_default}
										<button class="icon-btn danger" onclick={(e) => { e.stopPropagation(); deleteCollection(col.id); }} title="Delete">&times;</button>
									{/if}
								</td>
							{/snippet}
						</PickerTable>
					{/if}
				</section>

				<!-- Skills table -->
				<section>
					<div class="section-header">
						<h3>Skills</h3>
						<button class="add-btn" onclick={startCreateSkill}>+ New</button>
					</div>

					{#if skills.length === 0}
						<div class="placeholder">No skills yet</div>
					{:else}
						<PickerTable
							items={skills}
							searchFields={['name']}
							placeholder="Search skills..."
							onRowClick={(sk) => sk.is_default ? viewSkill(sk) : startEditSkill(sk)}
						>
							{#snippet head()}
								<tr>
									<th>Name</th>
									<th>Type</th>
									<th class="actions-col"></th>
								</tr>
							{/snippet}
							{#snippet row(sk)}
								<td class="item-name">
									{sk.name}
									{#if sk.issues?.length}
										<span class="issue-badge" title={sk.issues.join(', ')}>{sk.issues.length}</span>
									{/if}
								</td>
								<td><span class="skill-badge" class:builtin={sk.is_default}>{sk.is_default ? 'built-in' : 'custom'}</span></td>
								<td class="actions-col">
									{#if !sk.is_default}
										<button class="icon-btn danger" onclick={(e) => { e.stopPropagation(); deleteSkill(sk.id); }} title="Delete">&times;</button>
									{/if}
								</td>
							{/snippet}
						</PickerTable>
					{/if}
				</section>

			{:else if mode === 'view-skill'}
				<!-- Read-only skill view (built-in) -->
				<pre class="skill-view">{skillContent}</pre>
				<div class="form-actions">
					<button class="btn-secondary" onclick={cancelSkillForm}>Back</button>
				</div>

			{:else if mode === 'create-skill' || mode === 'edit-skill'}
				<!-- Skill create/edit form (structured) -->
				<div class="form-top">
					<div class="form-row" style="flex:1">
						<label for="skill-name">Name</label>
						<input id="skill-name" type="text" bind:value={skillName} placeholder="full_report" />
					</div>
				</div>
				{#if skillIssues.length > 0}
					<div class="skill-issues">
						{#each skillIssues as issue}
							<div class="skill-issue">{issue}</div>
						{/each}
					</div>
				{/if}

				<div class="form-row">
					<label for="skill-when">When</label>
					<textarea id="skill-when" class="skill-field" bind:value={skillWhen} placeholder="Describe when this skill triggers..." rows="3"></textarea>
				</div>

				<div class="form-row">
					<label>Tools</label>
					{#if availableTools.length === 0}
						<div class="placeholder">Loading tools...</div>
					{:else}
						<PickerTable
							items={availableTools}
							searchFields={['name', 'description']}
							placeholder="Search tools..."
							searchThreshold={0}
							bind:filtered={toolPickerFiltered}
							onRowClick={(t) => toggleSkillTool(t.name)}
							rowClass={(t) => skillTools.has(t.name) ? 'selected' : ''}
						>
							{#snippet toolbar()}
								<span class="picker-count">{skillToolCount} selected</span>
							{/snippet}
							{#snippet head()}
								<tr>
									<th class="check-col">
										<input
											type="checkbox"
											checked={toolPickerFiltered.length > 0 && toolPickerFiltered.every(t => skillTools.has(t.name))}
											onchange={toggleAllSkillTools}
										/>
									</th>
									<th>Tool</th>
									<th>Description</th>
								</tr>
							{/snippet}
							{#snippet row(t)}
								<td class="check-col">
									<input type="checkbox" checked={skillTools.has(t.name)} onclick={(e) => e.stopPropagation()} onchange={() => toggleSkillTool(t.name)} />
								</td>
								<td class="item-name">{t.name}</td>
								<td class="tool-desc">{t.description}</td>
							{/snippet}
						</PickerTable>
					{/if}
				</div>

				<div class="form-row">
					<label for="skill-workflow">Workflow</label>
					<textarea id="skill-workflow" class="skill-field" bind:value={skillWorkflow} placeholder={"1. search() to resolve name\n2. profile(sid=...)"} rows="4"></textarea>
				</div>

				<div class="form-row">
					<label for="skill-report">Report</label>
					<textarea id="skill-report" class="skill-field mono" bind:value={skillReport} placeholder={'report["overview"] = [...]\nreport["details"] = [...]'} rows="6"></textarea>
				</div>

				<div class="form-row">
					<label for="skill-rules">Rules</label>
					<textarea id="skill-rules" class="skill-field" bind:value={skillRules} placeholder="- Batch tool calls in ONE Python call" rows="4"></textarea>
				</div>

				<div class="form-actions">
					<button class="btn-secondary" onclick={cancelSkillForm}>Cancel</button>
					<button class="btn-primary" onclick={saveSkill} disabled={!skillName.trim()}>
						{mode === 'create-skill' ? 'Create' : 'Save'}
					</button>
				</div>

			{:else}
				<!-- Collection create/edit with item picker -->
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

				{#if itemsLoading}
					<div class="placeholder">Loading...</div>
				{:else if allItems.length === 0}
					<div class="placeholder">No {formType} found</div>
				{:else}
					<PickerTable
						items={allItems}
						searchFields={formType === 'enzymes' ? ['name', 'site'] : ['name']}
						placeholder={formType === 'enzymes' ? 'Search enzymes...' : 'Search primers...'}
						searchThreshold={0}
						bind:filtered={pickerFiltered}
						onRowClick={(item) => toggleItem(itemKey(item))}
						rowClass={(item) => selected.has(itemKey(item)) ? 'selected' : ''}
					>
						{#snippet toolbar()}
							<span class="picker-count">{selectedCount} selected</span>
						{/snippet}
						{#snippet head()}
							<tr>
								<th class="check-col">
									<input
										type="checkbox"
										checked={pickerFiltered.length > 0 && pickerFiltered.every(i => selected.has(itemKey(i)))}
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
						{/snippet}
						{#snippet row(item)}
							{@const key = itemKey(item)}
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
						{/snippet}
					</PickerTable>
				{/if}

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

	.picker-count {
		font-size: 0.78rem;
		color: var(--text-faint);
		white-space: nowrap;
	}

	.check-col {
		width: 32px;
		text-align: center;
	}

	.item-name {
		font-weight: 500;
	}

	.item-site {
		font-family: var(--font-mono);
		font-size: 0.78rem;
		color: var(--text-secondary);
	}

	.actions-col {
		width: 32px;
		text-align: center;
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

	/* ── Skill styles ── */

	.skill-badge {
		font-size: 0.72rem;
		color: var(--text-faint);
	}

	.skill-badge.builtin {
		color: var(--color-accent, var(--text-faint));
	}

	.issue-badge {
		display: inline-block;
		background: var(--color-warn, #c59a00);
		color: var(--bg-surface);
		font-size: 0.65rem;
		font-weight: 600;
		border-radius: 8px;
		padding: 0 0.35rem;
		margin-left: 0.4rem;
		vertical-align: middle;
	}

	.skill-view {
		background: var(--bg-app);
		border: 1px solid var(--border);
		border-radius: 6px;
		padding: 0.75rem 1rem;
		font-size: 0.82rem;
		font-family: var(--font-mono);
		line-height: 1.5;
		white-space: pre-wrap;
		word-wrap: break-word;
		max-height: 400px;
		overflow-y: auto;
		margin: 0;
	}

	.skill-issues {
		display: flex;
		flex-direction: column;
		gap: 2px;
	}

	.skill-issue {
		font-size: 0.78rem;
		color: var(--color-warn, #c59a00);
		padding: 0.2rem 0;
	}

	.skill-field {
		width: 100%;
		padding: 0.5rem 0.6rem;
		border: 1px solid var(--border);
		border-radius: 6px;
		background: var(--bg-app);
		color: var(--text);
		font-size: 0.82rem;
		font-family: inherit;
		resize: vertical;
		outline: none;
		line-height: 1.5;
		box-sizing: border-box;
	}

	.skill-field:focus {
		border-color: var(--color-accent);
	}

	.skill-field.mono {
		font-family: var(--font-mono);
	}

	.tool-desc {
		font-size: 0.78rem;
		color: var(--text-secondary);
		max-width: 260px;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
</style>
