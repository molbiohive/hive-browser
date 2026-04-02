<script>
	import { rerunTool } from '$lib/stores/chat.ts';
	import { copyToClipboard } from '$lib/clipboard.ts';
	import DataTable from '$lib/DataTable.svelte';
	import TabBar from '$lib/TabBar.svelte';
	import CopyableSequence from '$lib/CopyableSequence.svelte';

	import ProfileWidget from '$lib/ProfileWidget.svelte';
	import DigestWidget from '$lib/DigestWidget.svelte';
	import AlignWidget from '$lib/AlignWidget.svelte';
	import HistoryWidget from '$lib/HistoryWidget.svelte';
	import CompositionWidget from '$lib/CompositionWidget.svelte';
	import ProteinWidget from '$lib/ProteinWidget.svelte';
	import SeqLogoWidget from '$lib/SeqLogoWidget.svelte';
	import FormWidget from '$lib/FormWidget.svelte';

	let { widget, messageIndex = -1 } = $props();
	let expanded = $state(true);
	let loading = $state(false);
	let copied = $state(false);

	const isStale = $derived(widget.stale || (!widget.data && widget.type !== 'form'));

	// Data-shape detection for domain widgets
	function detectWidget(d) {
		if (!d || d.error) return null;
		if (d.sequence_data || d.sequence?.sequence_data) return ProfileWidget;
		if (d.sequence?.sid != null && d.features) return ProfileWidget;
		if (d.gel_data) return DigestWidget;
		if (d.aligned) return AlignWidget;
		if (d.root && d.steps) return HistoryWidget;
		if (d.logo_positions) return SeqLogoWidget;
		if (d.protein && d.protein_length != null) return ProteinWidget;
		if (d.gc_percent != null && d.a != null) return CompositionWidget;
		return null;
	}

	const WidgetComponent = $derived.by(() => {
		if (widget.type === 'form') return FormWidget;
		return detectWidget(widget.data);
	});

	// Decompose a data object into scalars, sequences, and tables
	const SEQ_MIN = 20;
	const SEQ_RE = /^[A-Za-z*\s]+$/;

	function decompose(data) {
		const tables = [];
		const sequences = [];
		const seqKeys = new Set();
		for (const [key, val] of Object.entries(data)) {
			if (Array.isArray(val) && val.length > 0 && typeof val[0] === 'object') {
				tables.push({
					id: key,
					label: key.replace(/_/g, ' '),
					rows: val,
					columns: Object.keys(val[0]).map(k => ({ key: k, label: k.replace(/_/g, ' ') })),
				});
			} else if (typeof val === 'string' && val.length >= SEQ_MIN && SEQ_RE.test(val)) {
				sequences.push({ key, sequence: val });
				seqKeys.add(key);
			}
		}
		const scalars = Object.entries(data).filter(
			([k, v]) => !Array.isArray(v) && typeof v !== 'object' && !seqKeys.has(k)
		);
		return { tables, sequences, scalars };
	}

	const fallback = $derived.by(() => {
		if (WidgetComponent || !widget.data || widget.data.error) return { tables: [], sequences: [], scalars: [] };
		return decompose(widget.data);
	});
	const fallbackTables = $derived(fallback.tables);
	const fallbackSequences = $derived(fallback.sequences);
	const fallbackScalars = $derived(fallback.scalars);

	// Report mode: each key in widget.data becomes a tab
	const isReport = $derived(widget.report === true && widget.data && !widget.data.error);
	const reportTabs = $derived.by(() => {
		if (!isReport) return [];
		return Object.entries(widget.data).map(([key, val]) => ({
			id: key,
			label: key.replace(/_/g, ' '),
			data: val,
		}));
	});

	let activeTab = $state('');
	let tabInitialized = false;
	$effect(() => {
		if (tabInitialized) return;
		if (isReport && reportTabs.length > 0) { activeTab = reportTabs[0].id; tabInitialized = true; }
		else if (fallbackTables.length > 0) { activeTab = fallbackTables[0].id; tabInitialized = true; }
	});

	const isForm = $derived(widget.type === 'form');
	const isSandbox = $derived(widget.tool === 'python');

	const commandText = $derived.by(() => {
		if (isForm) return `//${widget.tool}`;
		if (isSandbox) {
			return widget.params?.feedback || 'python sandbox';
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

	<div class="widget-collapse" class:open={expanded}>
		<div class="widget-collapse-inner">
		{#if isStale}
			<div class="widget-body stale">
				<button class="rerun-btn" onclick={handleRerun} disabled={loading}>
					{loading ? 'Loading...' : 'Load results'}
				</button>
			</div>
		{:else if WidgetComponent}
			<div class="widget-body">
				<WidgetComponent data={widget.data} {messageIndex} />
			</div>
		{:else if isReport && reportTabs.length > 0}
			<div class="widget-body">
				<TabBar tabs={reportTabs.map(t => ({ id: t.id, label: t.label }))}
					active={activeTab} onchange={(id) => activeTab = id} />
				{#each reportTabs as tab}
					{#if tab.id === activeTab}
						{@const tabWidget = typeof tab.data === 'object' && tab.data !== null && !Array.isArray(tab.data) ? detectWidget(tab.data) : null}
						{@const d = !tabWidget && typeof tab.data === 'object' && tab.data !== null && !Array.isArray(tab.data) ? decompose(tab.data) : null}
						{#if tabWidget}
							<svelte:component this={tabWidget} data={tab.data} {messageIndex} />
						{:else if Array.isArray(tab.data) && tab.data.length > 0 && typeof tab.data[0] === 'object'}
							<DataTable rows={tab.data}
								columns={Object.keys(tab.data[0]).map(k => ({ key: k, label: k.replace(/_/g, ' ') }))}
								defaultPageSize={10} />
						{:else if typeof tab.data === 'string' && tab.data.length >= SEQ_MIN && SEQ_RE.test(tab.data)}
							<CopyableSequence sequence={tab.data}
								label="{tab.data.length} characters — click to copy" />
						{:else if d}
							{#if d.scalars.length}
								<div class="generic-meta">
									{#each d.scalars as [key, val]}
										<span><strong>{key.replace(/_/g, ' ')}:</strong> {val}</span>
									{/each}
								</div>
							{/if}
							{#each d.sequences as { key, sequence }}
								<div class="seq-block">
									<div class="seq-label">{key.replace(/_/g, ' ')}</div>
									<CopyableSequence {sequence} label="{sequence.length} characters — click to copy" />
								</div>
							{/each}
							{#each d.tables as table}
								<DataTable rows={table.rows} columns={table.columns} defaultPageSize={10} />
							{/each}
						{:else}
							<p>{tab.data}</p>
						{/if}
					{/if}
				{/each}
			</div>
		{:else if widget.data}
			<div class="widget-body">
				{#if widget.data.error}
					<p class="generic-error">{widget.data.error}</p>
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
		</div>
	</div>
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

	.widget-collapse {
		display: grid;
		grid-template-rows: 0fr;
		transition: grid-template-rows 0.2s ease;
	}

	.widget-collapse.open {
		grid-template-rows: 1fr;
	}

	.widget-collapse-inner {
		overflow: hidden;
		min-height: 0;
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
