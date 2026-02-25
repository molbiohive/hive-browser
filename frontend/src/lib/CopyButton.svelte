<script>
	import { copyToClipboard } from '$lib/clipboard.ts';

	let { text, label = 'Copy' } = $props();
	let copied = $state(false);

	async function copy() {
		const ok = await copyToClipboard(text);
		if (ok) {
			copied = true;
			setTimeout(() => (copied = false), 2000);
		}
	}
</script>

<button class="copy-btn" onclick={copy} title={text}>
	{#if copied}
		<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
			<polyline points="20 6 9 17 4 12" />
		</svg>
	{:else}
		{label}
	{/if}
</button>

<style>
	.copy-btn {
		background: var(--bg-hover);
		border: 1px solid var(--border-muted);
		border-radius: 4px;
		padding: 0.15rem 0.4rem;
		font-size: 0.75rem;
		color: var(--text-secondary);
		cursor: pointer;
		display: inline-flex;
		align-items: center;
		gap: 0.2rem;
		line-height: 1;
	}
	.copy-btn:hover {
		background: var(--bg-active);
		color: var(--text-primary);
	}
	.copy-btn svg {
		color: var(--color-ok);
	}
</style>
