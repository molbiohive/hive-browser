<script>
	import { rerunTool } from '$lib/stores/chat.ts';
	import DataTable from '$lib/DataTable.svelte';

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

	// Generic fallback: auto-detect arrays → table rows, scalars → key-value
	const fallbackRows = $derived.by(() => {
		if (WidgetComponent || !widget.data || widget.data.error) return null;
		for (const val of Object.values(widget.data)) {
			if (Array.isArray(val) && val.length > 0 && typeof val[0] === 'object') {
				return val;
			}
		}
		return null;
	});

	const fallbackColumns = $derived.by(() => {
		if (!fallbackRows?.length) return [];
		return Object.keys(fallbackRows[0]).map((key) => ({
			key,
			label: key.replace(/_/g, ' '),
		}));
	});

	const fallbackScalars = $derived.by(() => {
		if (WidgetComponent || !widget.data) return [];
		return Object.entries(widget.data).filter(
			([, v]) => !Array.isArray(v) && typeof v !== 'object'
		);
	});

	const isForm = $derived(widget.type === 'form');

	const commandText = $derived.by(() => {
		if (isForm) return `//${widget.tool}`;
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
		try {
			await navigator.clipboard.writeText(commandText);
			copied = true;
			setTimeout(() => { copied = false; }, 1500);
		} catch (err) {
			console.error('Copy failed:', err);
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
			<button class="copy-btn" onclick={copyCommand} title="Copy command">
				{#if copied}
					<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20 6L9 17l-5-5"/></svg>
				{:else}
					<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1"/></svg>
				{/if}
			</button>
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
				<WidgetComponent data={widget.data} {messageIndex} />
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
					{#if fallbackRows}
						<DataTable rows={fallbackRows} columns={fallbackColumns} defaultPageSize={10} />
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
		font-family: 'SF Mono', Monaco, Menlo, monospace;
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
		font-family: 'SF Mono', Monaco, monospace;
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
</style>
