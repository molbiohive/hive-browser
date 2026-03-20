<script>
	import { CloningHistoryViewer, Tooltip } from '@molbiohive/hatchlings';
	let { data } = $props();
	let hoverInfo = $state(null);
	let containerW = $state(0);

	/** Measure tree depth and width to size the viewer */
	function treeDims(node) {
		if (!node?.source?.inputs?.length) return { depth: 1, width: 1 };
		const kids = node.source.inputs.map(i => treeDims(i.node));
		const maxD = Math.max(...kids.map(k => k.depth));
		const totalW = kids.reduce((s, k) => s + k.width, 0);
		return { depth: maxD + 1, width: Math.max(1, totalW) };
	}

	const dims = $derived(data?.root ? treeDims(data.root) : { depth: 1, width: 1 });
	const viewerW = $derived(Math.max(containerW, dims.width * 220));
	const viewerH = $derived(dims.depth * 230);
</script>

{#if data?.error}
	<p class="error">{data.error}</p>
{:else if data?.root}
	<div class="history-container" bind:clientWidth={containerW}>
		<p class="meta">{data.sequence_name} &mdash; {data.steps} step(s), {data.sequence_size} bp</p>
		<div class="history-scroll">
			<CloningHistoryViewer
				root={data.root}
				width={viewerW}
				height={viewerH}
				onhoverinfo={(info) => hoverInfo = info}
			/>
		</div>
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
		position: relative;
	}

	.history-scroll {
		overflow: auto;
		max-height: 80vh;
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
