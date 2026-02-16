<script>
	import { rerunTool } from '$lib/stores/chat.ts';
	import TableWidget from '$lib/TableWidget.svelte';
	import BlastWidget from '$lib/BlastWidget.svelte';
	import ProfileWidget from '$lib/ProfileWidget.svelte';
	import StatusWidget from '$lib/StatusWidget.svelte';
	import ModelWidget from '$lib/ModelWidget.svelte';
	import FormWidget from '$lib/FormWidget.svelte';

	let { widget, messageIndex = -1 } = $props();
	let expanded = $state(true);
	let loading = $state(false);

	const widgetComponents = {
		table: TableWidget,
		blast: BlastWidget,
		profile: ProfileWidget,
		status: StatusWidget,
		model: ModelWidget,
		form: FormWidget,
	};

	const isStale = $derived(widget.stale || (!widget.data && widget.type !== 'form'));

	function toggle() {
		expanded = !expanded;
	}

	function handleRerun() {
		loading = true;
		rerunTool(widget.tool, widget.params || {}, messageIndex);
	}

	$effect(() => {
		if (widget.data && !widget.stale) {
			loading = false;
		}
	});
</script>

<div class="widget" class:collapsed={!expanded}>
	<button class="widget-header" onclick={toggle}>
		<span>{widget.tool}: {widget.summary || ''}</span>
		<span>{expanded ? '\u2212' : '+'}</span>
	</button>

	{#if expanded}
		{#if isStale}
			<div class="widget-body stale">
				<button class="rerun-btn" onclick={handleRerun} disabled={loading}>
					{loading ? 'Loading...' : 'Load results'}
				</button>
			</div>
		{:else if widgetComponents[widget.type]}
			<div class="widget-body">
				<svelte:component this={widgetComponents[widget.type]} data={widget.data} {messageIndex} />
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
		padding: 0.5rem 0.75rem;
		background: #f8f8f8;
		border: none;
		cursor: pointer;
		font-size: 0.8rem;
		color: #666;
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
