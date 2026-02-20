<script>
	let { data } = $props();
</script>

<div class="status-grid">
	<div class="stat">
		<span class="label">Indexed Files</span>
		<span class="value">{data?.indexed_files ?? 0}</span>
	</div>
	<div class="stat">
		<span class="label">Sequences</span>
		<span class="value">{data?.sequences ?? 0}</span>
	</div>
	<div class="stat">
		<span class="label">Features</span>
		<span class="value">{data?.features ?? 0}</span>
	</div>
	<div class="stat">
		<span class="label">Primers</span>
		<span class="value">{data?.primers ?? 0}</span>
	</div>
	<div class="stat">
		<span class="label">Database</span>
		<span class="indicator" class:ok={data?.database_connected} class:fail={!data?.database_connected}>
			{data?.database_connected ? 'Connected' : 'Disconnected'}
		</span>
	</div>
	<div class="stat">
		<span class="label">LLM</span>
		<span class="indicator" class:ok={data?.llm_available} class:fail={!data?.llm_available}>
			{data?.llm_available ? 'Available' : 'Unavailable'}
		</span>
	</div>
</div>

<style>
	.status-grid {
		display: grid;
		grid-template-columns: 1fr 1fr;
		gap: 0.5rem;
	}

	.stat {
		display: flex;
		justify-content: space-between;
		align-items: center;
		padding: 0.35rem 0.5rem;
		background: var(--bg-muted);
		border-radius: 4px;
		font-size: 0.82rem;
	}

	.label {
		color: var(--text-faint);
	}

	.value {
		font-weight: 600;
		color: var(--text);
	}

	.indicator {
		font-weight: 500;
		font-size: 0.78rem;
	}

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
