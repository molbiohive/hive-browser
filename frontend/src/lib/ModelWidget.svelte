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
		background: var(--bg-muted);
		border-radius: 4px;
		margin-bottom: 0.3rem;
	}
	.label { color: var(--text-faint); }
	.value { font-weight: 600; color: var(--text); }
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
	.ok { color: var(--color-ok); }
	.ok::before { background: var(--color-ok); }
	.fail { color: var(--color-err); }
	.fail::before { background: var(--color-err); }
</style>
