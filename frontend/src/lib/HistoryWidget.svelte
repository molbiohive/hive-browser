<script>
	import { CloningHistoryViewer, Tooltip } from '@molbiohive/hatchlings';
	let { data } = $props();
	let hoverInfo = $state(null);
</script>

{#if data?.error}
	<p class="error">{data.error}</p>
{:else if data?.root}
	<div class="history-container">
		<p class="meta">{data.sequence_name} &mdash; {data.steps} step(s), {data.sequence_size} bp</p>
		<CloningHistoryViewer
			root={data.root}
			onhoverinfo={(info) => hoverInfo = info}
		/>
		{#if hoverInfo}
			<Tooltip {...hoverInfo} />
		{/if}
	</div>
{:else}
	<p class="empty">No cloning history available</p>
{/if}

<style>
	.history-container {
		min-height: 200px;
	}

	.meta {
		font-size: 0.78rem;
		color: var(--text-muted);
		margin: 0 0 0.5rem;
	}

	.error {
		color: var(--color-err);
		font-size: 0.85rem;
		margin: 0;
	}

	.empty {
		color: var(--text-placeholder);
		font-size: 0.85rem;
		margin: 0;
	}
</style>
