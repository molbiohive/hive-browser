<script>
	import TableWidget from '$lib/TableWidget.svelte';
	import BlastWidget from '$lib/BlastWidget.svelte';
	import ProfileWidget from '$lib/ProfileWidget.svelte';
	import StatusWidget from '$lib/StatusWidget.svelte';
	import ModelWidget from '$lib/ModelWidget.svelte';
	import FormWidget from '$lib/FormWidget.svelte';

	let { widget, messageIndex = -1 } = $props();
	let expanded = $state(true);

	const widgetComponents = {
		table: TableWidget,
		blast: BlastWidget,
		profile: ProfileWidget,
		status: StatusWidget,
		model: ModelWidget,
		form: FormWidget,
	};

	function toggle() {
		expanded = !expanded;
	}
</script>

<div class="widget" class:collapsed={!expanded}>
	<button class="widget-header" onclick={toggle}>
		<span>{widget.tool}: {widget.summary || ''}</span>
		<span>{expanded ? '\u2212' : '+'}</span>
	</button>

	{#if expanded && widgetComponents[widget.type]}
		<div class="widget-body">
			<svelte:component this={widgetComponents[widget.type]} data={widget.data} {messageIndex} />
		</div>
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
</style>
