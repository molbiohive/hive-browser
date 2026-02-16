<script>
	import { rerunTool } from '$lib/stores/chat.ts';

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

	const isForm = $derived(widget.type === 'form');

	const commandText = $derived.by(() => {
		if (isForm) return `//${widget.tool}`;
		const params = widget.params || {};
		return `//${widget.tool} ${JSON.stringify(params)}`;
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
		{/if}
	{/if}
</div>

<style>
	.widget {
		margin-top: 0.5rem;
		border: 1px solid #ddd;
		border-radius: 8px;
		overflow: hidden;
	}

	.widget-header {
		width: 100%;
		display: flex;
		justify-content: space-between;
		align-items: center;
		padding: 0.5rem 0.75rem;
		background: #f8f8f8;
		font-size: 0.8rem;
		color: #666;
	}

	.header-cmd {
		font-family: 'SF Mono', Monaco, Menlo, monospace;
		font-size: 0.75rem;
		color: #888;
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
		color: #888;
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
		color: #aaa;
		padding: 0.15rem;
		border-radius: 3px;
	}

	.copy-btn:hover {
		color: #555;
		background: #eee;
	}

	.widget-body {
		padding: 0.75rem;
	}

	.stale {
		display: flex;
		justify-content: center;
		padding: 1rem;
	}

	.rerun-btn {
		padding: 0.4rem 1rem;
		border: 1px solid #ddd;
		background: white;
		border-radius: 6px;
		cursor: pointer;
		font-size: 0.82rem;
		color: #555;
	}

	.rerun-btn:hover {
		background: #f0f0f0;
	}

	.rerun-btn:disabled {
		opacity: 0.5;
		cursor: default;
	}
</style>
