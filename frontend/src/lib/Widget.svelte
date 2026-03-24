<script>
	import { rerunTool } from '$lib/stores/chat.ts';
	import { copyToClipboard } from '$lib/clipboard.ts';
	import DataTable from '$lib/DataTable.svelte';
	import TabBar from '$lib/TabBar.svelte';
	import CopyableSequence from '$lib/CopyableSequence.svelte';

	// Auto-discover widget components: FooWidget.svelte -> type "foo"
	const modules = import.meta.glob('./*Widget.svelte', { eager: true });
	const widgetComponents = {};
	for (const [path, mod] of Object.entries(modules)) {
		const match = path.match(/\.\/(\w+)Widget\.svelte$/);
		if (match) {
			const type = match[1].toLowerCase();
			widgetComponents[type] = mod.default;
		}
	}

	let { widget, messageIndex = -1 } = $props();
	let expanded = $state(true);
	let loading = $state(false);
	let copied = $state(false);

	const isStale = $derived(widget.stale || (!widget.data && widget.type !== 'form'));
	const WidgetComponent = $derived(widgetComponents[widget.type]);

	// Batch detection: router wraps fan-out results in {results: [...], count: N}
	const isBatch = $derived(
		!!(widget.data?.results && Array.isArray(widget.data.results) && widget.data.count > 0)
	);

	const batchTabs = $derived.by(() => {
		if (!isBatch) return [];
		return widget.data.results.map((r, i) => ({
			id: String(i),
			label: r._label || `#${i + 1}`,
		}));
	});

	let activeBatchIdx = $state('0');

	// Effective data: selected batch item or raw widget.data
	const activeData = $derived.by(() => {
		if (!isBatch) return widget.data;
		const idx = parseInt(activeBatchIdx) || 0;
		const item = widget.data.results[idx];
		if (!item) return widget.data.results[0] || {};
		const { _label, ...rest } = item;
		return rest;
	});

	// Detect all list[dict] values -> tabbed tables
	const fallbackTables = $derived.by(() => {
		if (WidgetComponent || !activeData || activeData.error) return [];
		const tables = [];
		for (const [key, val] of Object.entries(activeData)) {
			if (Array.isArray(val) && val.length > 0 && typeof val[0] === 'object') {
				tables.push({
					id: key,
					label: key.replace(/_/g, ' '),
					rows: val,
					columns: Object.keys(val[0]).map(k => ({
						key: k,
						label: k.replace(/_/g, ' '),
					})),
				});
			}
		}
		return tables;
	});

	// Detect long DNA/RNA/protein-like strings -> CopyableSequence
	const SEQ_MIN = 20;
	const SEQ_RE = /^[A-Za-z*\s]+$/;

	const fallbackSequences = $derived.by(() => {
		if (WidgetComponent || !activeData || activeData.error) return [];
		return Object.entries(activeData)
			.filter(([, v]) => typeof v === 'string' && v.length >= SEQ_MIN && SEQ_RE.test(v))
			.map(([key, val]) => ({ key, sequence: val }));
	});

	// Scalars -- exclude arrays, objects, and detected sequences
	const fallbackScalars = $derived.by(() => {
		if (WidgetComponent || !activeData) return [];
		const seqKeys = new Set(fallbackSequences.map(s => s.key));
		return Object.entries(activeData).filter(
			([k, v]) => !Array.isArray(v) && typeof v !== 'object' && !seqKeys.has(k)
		);
	});

	let activeTab = $state('');
	$effect(() => {
		if (fallbackTables.length > 0) activeTab = fallbackTables[0].id;
	});

	const isForm = $derived(widget.type === 'form');
	const isSandbox = $derived(widget.tool === 'python');

	const commandText = $derived.by(() => {
		if (isForm) return `//${widget.tool}`;
		if (isSandbox) {
			const code = widget.params?.code || '';
			return `python(code="${code}")`;
		}
		const params = widget.params || {};
		const hasParams = Object.keys(params).length > 0;
		return hasParams ? `//${widget.tool} ${JSON.stringify(params)}` : `//${widget.tool}`;
	});

	const headerText = $derived.by(() => {
		const maxLen = 60;
		return commandText.length > maxLen ? commandText.slice(0, maxLen) + '...' : commandText;
	});

	function toggle() {
		expanded = !expanded;
	}

	function handleRerun() {
		loading = true;
		rerunTool(widget.tool, widget.params || {}, messageIndex);
	}

	async function copyCommand(e) {
		e.stopPropagation();
		const ok = await copyToClipboard(commandText);
		if (ok) {
			copied = true;
			setTimeout(() => { copied = false; }, 1500);
		}
	}

	$effect(() => {
		if (widget.data && !widget.stale) {
			loading = false;
		}
	});
</script>

<div class="widget" class:collapsed={!expanded}>
	<div class="widget-header">
		<button class="header-cmd" onclick={toggle}>{headerText}</button>
		<span class="header-actions">
			{#if !isSandbox}
				<button class="copy-btn" onclick={copyCommand} title="Copy command">
					{#if copied}
						<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20 6L9 17l-5-5"/></svg>
					{:else}
						<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1"/></svg>
					{/if}
				</button>
			{/if}
			<button class="toggle-btn" onclick={toggle}>{expanded ? '\u2212' : '+'}</button>
		</span>
	</div>

	{#if expanded}
		{#if isStale}
			<div class="widget-body stale">
				<button class="rerun-btn" onclick={handleRerun} disabled={loading}>
					{loading ? 'Loading...' : 'Load results'}
				</button>
			</div>
		{:else if WidgetComponent}
			<div class="widget-body">
				{#if isBatch}
					<TabBar tabs={batchTabs} active={activeBatchIdx}
						onchange={(id) => activeBatchIdx = id} />
				{/if}
				<WidgetComponent data={activeData} {messageIndex} />
			</div>
		{:else if widget.data}
			<div class="widget-body">
				{#if isBatch}
					<TabBar tabs={batchTabs} active={activeBatchIdx}
						onchange={(id) => activeBatchIdx = id} />
				{/if}
				{#if activeData.error}
					<p class="generic-error">{activeData.error}</p>
				{:else}
					{#if fallbackScalars.length}
						<div class="generic-meta">
							{#each fallbackScalars as [key, val]}
								<span>
									<strong>{key.replace(/_/g, ' ')}:</strong>
									{#if typeof val === 'string' && val.length > 80}
										<span class="truncated" title={val}>{val.slice(0, 80)}...</span>
									{:else}
										{val}
									{/if}
								</span>
							{/each}
						</div>
					{/if}

					{#each fallbackSequences as { key, sequence }}
						<div class="seq-block">
							<div class="seq-label">{key.replace(/_/g, ' ')}</div>
							<CopyableSequence {sequence}
								label="{sequence.length} characters — click to copy" />
						</div>
					{/each}

					{#if fallbackTables.length === 1}
						<DataTable rows={fallbackTables[0].rows}
							columns={fallbackTables[0].columns} defaultPageSize={10} />
					{:else if fallbackTables.length > 1}
						<TabBar tabs={fallbackTables.map(t => ({ id: t.id, label: t.label }))}
							active={activeTab} onchange={(id) => activeTab = id} />
						{#each fallbackTables as table}
							{#if table.id === activeTab}
								<DataTable rows={table.rows}
									columns={table.columns} defaultPageSize={10} />
							{/if}
						{/each}
					{/if}
				{/if}
			</div>
		{/if}
	{/if}
</div>

<style>
	.widget {
		margin-top: 0.5rem;
		border: 1px solid var(--border);
		border-radius: 8px;
		overflow: hidden;
	}

	.widget-header {
		width: 100%;
		display: flex;
		justify-content: space-between;
		align-items: center;
		padding: 0.5rem 0.75rem;
		background: var(--bg-muted);
		font-size: 0.8rem;
		color: var(--text-muted);
	}

	.header-cmd {
		font-family: var(--font-mono);
		font-size: 0.75rem;
		color: var(--text-faint);
		background: none;
		border: none;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
		cursor: pointer;
		flex: 1;
		text-align: left;
		padding: 0;
	}

	.toggle-btn {
		background: none;
		border: none;
		cursor: pointer;
		color: var(--text-faint);
		font-size: 0.85rem;
		padding: 0 0.15rem;
	}

	.header-actions {
		display: flex;
		align-items: center;
		gap: 0.4rem;
		flex-shrink: 0;
	}

	.copy-btn {
		display: flex;
		align-items: center;
		justify-content: center;
		background: none;
		border: none;
		cursor: pointer;
		color: var(--text-placeholder);
		padding: 0.15rem;
		border-radius: 3px;
	}

	.copy-btn:hover {
		color: var(--text-secondary);
		background: var(--bg-hover);
	}

	.widget-body {
		padding: 0.75rem;
		overflow-x: auto;
		overflow-wrap: break-word;
		word-break: break-word;
	}

	.stale {
		display: flex;
		justify-content: center;
		padding: 1rem;
	}

	.rerun-btn {
		padding: 0.4rem 1rem;
		border: 1px solid var(--border);
		background: var(--bg-surface);
		border-radius: 6px;
		cursor: pointer;
		font-size: 0.82rem;
		color: var(--text-secondary);
	}

	.rerun-btn:hover {
		background: var(--bg-hover);
	}

	.rerun-btn:disabled {
		opacity: 0.5;
		cursor: default;
	}

	.generic-error {
		color: var(--color-err);
		font-size: 0.85rem;
		margin: 0;
	}

	.truncated {
		font-family: var(--font-mono);
		font-size: 0.72rem;
		cursor: help;
	}

	.generic-meta {
		display: flex;
		flex-wrap: wrap;
		gap: 0.5rem 1rem;
		margin-bottom: 0.5rem;
		font-size: 0.78rem;
		color: var(--text-muted);
		overflow-wrap: break-word;
		word-break: break-word;
	}

	.seq-block { margin-bottom: 0.5rem; }
	.seq-label {
		font-size: 0.75rem;
		color: var(--text-faint);
		margin-bottom: 0.2rem;
		font-weight: 500;
	}
</style>
