<script>
	import { copyToClipboard } from '$lib/clipboard.ts';

	let { sequence, display = '', label = '' } = $props();
	let copied = $state(false);

	const shown = $derived(display || sequence);

	async function copy() {
		const ok = await copyToClipboard(sequence);
		if (ok) {
			copied = true;
			setTimeout(() => (copied = false), 2000);
		}
	}
</script>

<!-- svelte-ignore a11y_click_events_have_key_events -->
<!-- svelte-ignore a11y_no_static_element_interactions -->
<div class="seq-area" onclick={copy} title="Click to copy sequence">
	<pre class="seq-text">{shown}</pre>
	{#if copied}
		<span class="flash">Copied!</span>
	{/if}
	{#if label}
		<span class="label">{label}</span>
	{/if}
</div>

<style>
	.seq-area {
		position: relative;
		background: var(--bg-code);
		border: 1px solid var(--border-muted);
		border-radius: 6px;
		padding: 0.5rem 0.7rem;
		cursor: pointer;
		transition: border-color 0.15s;
		max-height: 12rem;
		overflow-y: auto;
	}
	.seq-area:hover {
		border-color: var(--border);
		background: var(--bg-hover);
	}
	.seq-text {
		font-family: 'SF Mono', Monaco, monospace;
		font-size: 0.78rem;
		line-height: 1.5;
		margin: 0;
		word-break: break-all;
		white-space: pre-wrap;
		color: var(--text-primary);
	}
	.flash {
		position: absolute;
		top: 0.35rem;
		right: 0.5rem;
		font-size: 0.7rem;
		color: var(--color-ok);
		font-weight: 500;
	}
	.label {
		display: block;
		margin-top: 0.3rem;
		font-size: 0.7rem;
		color: var(--text-faint);
	}
</style>
