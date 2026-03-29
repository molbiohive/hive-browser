<script>
	import { SeqLogo } from '@molbiohive/hatchlings';

	let { data } = $props();
	let containerEl = $state(undefined);
	let containerWidth = $state(600);

	const logoData = $derived.by(() => {
		if (!data?.logo_positions?.length) return null;
		return {
			positions: data.logo_positions,
			alphabet: data.alphabet || 'dna',
		};
	});

	$effect(() => {
		if (!containerEl) return;
		const ro = new ResizeObserver(([e]) => {
			containerWidth = e.contentRect.width;
		});
		ro.observe(containerEl);
		return () => ro.disconnect();
	});
</script>

{#if data?.error}
<p class="error">{data.error}</p>
{:else if logoData}
<div class="logo-widget" bind:this={containerEl}>
	<div class="meta">
		<span><strong>Sequences:</strong> {data.sequence_count}</span>
		<span><strong>Positions:</strong> {data.logo_length}</span>
		<span><strong>Type:</strong> {data.alphabet}</span>
	</div>
	<div class="viewer-wrap">
		<SeqLogo data={logoData}
			width={Math.max(400, containerWidth - 2)}
			height={180} />
	</div>
</div>
{:else}
<p class="empty">No sequence logo data</p>
{/if}

<style>
	.logo-widget { font-size: 0.85rem; }
	.meta {
		display: flex;
		flex-wrap: wrap;
		gap: 0.5rem 1rem;
		margin-bottom: 0.5rem;
		font-size: 0.8rem;
		color: var(--text-secondary);
	}
	.viewer-wrap {
		border-radius: 6px;
		overflow: hidden;
		border: 1px solid var(--border-muted);
	}
	.error { color: var(--color-err); font-size: 0.85rem; }
	.empty { color: var(--text-placeholder); font-size: 0.85rem; }
</style>
