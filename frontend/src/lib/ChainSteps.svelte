<script>
	let { chain } = $props();
	let expanded = $state(false);

	function fullCommand(step) {
		return `//${step.tool} ${JSON.stringify(step.params)}`;
	}

	function displayCommand(step) {
		const cmd = fullCommand(step);
		return cmd.length > 120 ? cmd.slice(0, 117) + '...' : cmd;
	}

	async function copyCommand(step) {
		try {
			await navigator.clipboard.writeText(fullCommand(step));
		} catch (e) {
			console.error('Clipboard copy failed:', e);
		}
	}
</script>

{#if chain?.length > 1}
<div class="chain">
	<button class="chain-toggle" onclick={() => expanded = !expanded}>
		{expanded ? 'Hide' : 'Show'} {chain.length} steps
		<span class="arrow">{expanded ? '\u25B4' : '\u25BE'}</span>
	</button>

	{#if expanded}
	<div class="chain-steps">
		{#each chain as step, i}
			<div class="step">
				<span class="step-num">{i + 1}</span>
				<div class="step-body">
					<div class="step-header">
						<span class="step-tool">{step.tool}</span>
						<span class="step-summary">{step.summary}</span>
					</div>
					<button type="button" class="step-cmd" onclick={() => copyCommand(step)} title="Click to copy full command">
						{displayCommand(step)}
					</button>
				</div>
			</div>
		{/each}
	</div>
	{/if}
</div>
{/if}

<style>
	.chain {
		margin-top: 0.5rem;
	}

	.chain-toggle {
		display: inline-flex;
		align-items: center;
		gap: 0.3rem;
		padding: 0.25rem 0.6rem;
		background: var(--bg-muted);
		border: 1px solid var(--border);
		border-radius: 4px;
		cursor: pointer;
		font-size: 0.75rem;
		color: var(--text-muted);
	}

	.chain-toggle:hover {
		background: var(--bg-hover);
	}

	.arrow {
		font-size: 0.65rem;
	}

	.chain-steps {
		margin-top: 0.4rem;
		border-left: 2px solid var(--border);
		padding-left: 0.75rem;
	}

	.step {
		display: flex;
		gap: 0.4rem;
		padding: 0.3rem 0;
	}

	.step-num {
		flex-shrink: 0;
		width: 1.2rem;
		height: 1.2rem;
		display: flex;
		align-items: center;
		justify-content: center;
		background: var(--bg-hover);
		border-radius: 50%;
		font-size: 0.65rem;
		font-weight: 600;
		color: var(--text-muted);
		margin-top: 0.1rem;
	}

	.step-body {
		flex: 1;
		min-width: 0;
	}

	.step-header {
		display: flex;
		align-items: baseline;
		gap: 0.4rem;
		font-size: 0.78rem;
		line-height: 1.4;
	}

	.step-tool {
		font-weight: 600;
		color: var(--text-secondary);
		flex-shrink: 0;
	}

	.step-summary {
		color: var(--text-faint);
	}

	.step-cmd {
		display: block;
		width: 100%;
		text-align: left;
		margin-top: 0.2rem;
		padding: 0.25rem 0.5rem;
		background: var(--bg-code);
		border: 1px solid var(--border-muted);
		border-radius: 4px;
		font-family: 'SF Mono', Monaco, monospace;
		font-size: 0.72rem;
		color: var(--text-muted);
		cursor: pointer;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}

	.step-cmd:hover {
		background: var(--bg-hover);
		border-color: var(--border);
		color: var(--text);
	}
</style>
