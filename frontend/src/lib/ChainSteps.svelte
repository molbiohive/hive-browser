<script>
	let { chain } = $props();
	let expanded = $state(false);
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
				<span class="step-tool">{step.tool}</span>
				<span class="step-summary">{step.summary}</span>
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
		background: #f0f0f0;
		border: 1px solid #ddd;
		border-radius: 4px;
		cursor: pointer;
		font-size: 0.75rem;
		color: #666;
	}

	.chain-toggle:hover {
		background: #e8e8e8;
	}

	.arrow {
		font-size: 0.65rem;
	}

	.chain-steps {
		margin-top: 0.4rem;
		border-left: 2px solid #ddd;
		padding-left: 0.75rem;
	}

	.step {
		display: flex;
		align-items: baseline;
		gap: 0.4rem;
		padding: 0.25rem 0;
		font-size: 0.78rem;
		line-height: 1.4;
	}

	.step-num {
		flex-shrink: 0;
		width: 1.2rem;
		height: 1.2rem;
		display: flex;
		align-items: center;
		justify-content: center;
		background: #e8e8e8;
		border-radius: 50%;
		font-size: 0.65rem;
		font-weight: 600;
		color: #666;
	}

	.step-tool {
		font-weight: 600;
		color: #555;
		flex-shrink: 0;
	}

	.step-summary {
		color: #888;
	}
</style>
