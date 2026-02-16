<script>
	let { data } = $props();
</script>

<div class="model-info">
	<div class="field">
		<span class="label">Provider</span>
		<span class="value mono">{data?.provider ?? 'unknown'}</span>
	</div>
	<div class="field">
		<span class="label">Model</span>
		<span class="value mono">{data?.model ?? 'unknown'}</span>
	</div>
	<div class="field">
		<span class="label">Endpoint</span>
		<span class="value mono">{data?.base_url ?? 'unknown'}</span>
	</div>
	<div class="field">
		<span class="label">Status</span>
		<span class="indicator" class:ok={data?.connected} class:fail={!data?.connected}>
			{data?.connected ? 'Connected' : 'Disconnected'}
		</span>
	</div>
</div>

<style>
	.model-info { font-size: 0.85rem; }
	.field {
		display: flex;
		justify-content: space-between;
		padding: 0.35rem 0.5rem;
		background: #fafafa;
		border-radius: 4px;
		margin-bottom: 0.3rem;
	}
	.label { color: #888; }
	.value { font-weight: 600; color: #333; }
	.mono { font-family: 'SF Mono', Monaco, monospace; font-size: 0.8rem; }
	.indicator { font-weight: 500; font-size: 0.78rem; }
	.indicator::before {
		content: '';
		display: inline-block;
		width: 6px;
		height: 6px;
		border-radius: 50%;
		margin-right: 0.35rem;
		vertical-align: middle;
	}
	.ok { color: #16a34a; }
	.ok::before { background: #16a34a; }
	.fail { color: #dc2626; }
	.fail::before { background: #dc2626; }
</style>
