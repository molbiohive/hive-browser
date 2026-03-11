<script>
	import { copyToClipboard } from '$lib/clipboard.ts';

	let { data } = $props();
	let copied = $state(false);

	const sequences = $derived.by(() => {
		if (!data?.aligned) return [];
		const lines = data.aligned.split('\n');
		const seqs = [];
		let current = null;
		for (const line of lines) {
			if (line.startsWith('>')) {
				if (current) seqs.push(current);
				current = { name: line.slice(1).trim(), seq: '' };
			} else if (current) {
				current.seq += line.trim();
			}
		}
		if (current) seqs.push(current);
		return seqs;
	});

	// Find max name length for padding
	const maxName = $derived(
		sequences.reduce((m, s) => Math.max(m, s.name.length), 0)
	);

	// Build formatted alignment lines
	const formatted = $derived(
		sequences.map(s => `${s.name.padEnd(maxName)}  ${s.seq}`).join('\n')
	);

	async function copyAlignment() {
		const ok = await copyToClipboard(data.aligned);
		if (ok) {
			copied = true;
			setTimeout(() => { copied = false; }, 1500);
		}
	}
</script>

{#if data?.error}
<p class="error">{data.error}</p>
{:else if data?.aligned}
<div class="align-widget">
	<div class="meta">
		<span><strong>Sequences:</strong> {data.count || sequences.length}</span>
		{#if sequences.length > 0}
			<span><strong>Alignment length:</strong> {sequences[0].seq.length}</span>
		{/if}
		<button class="copy-btn" onclick={copyAlignment}>
			{copied ? 'Copied!' : 'Copy FASTA'}
		</button>
	</div>
	<pre class="alignment">{formatted}</pre>
</div>
{:else}
<p class="empty">No alignment data</p>
{/if}

<style>
	.align-widget { font-size: 0.85rem; }
	.meta {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 0.5rem 1rem;
		margin-bottom: 0.5rem;
		font-size: 0.8rem;
		color: var(--text-secondary);
	}
	.copy-btn {
		margin-left: auto;
		padding: 0.2rem 0.6rem;
		border: 1px solid var(--border);
		background: var(--bg-surface);
		border-radius: 4px;
		cursor: pointer;
		font-size: 0.75rem;
		color: var(--text-secondary);
	}
	.copy-btn:hover {
		background: var(--bg-hover);
	}
	.alignment {
		font-family: var(--font-mono);
		font-size: 0.75rem;
		line-height: 1.4;
		padding: 0.75rem;
		background: var(--bg-muted);
		border-radius: 6px;
		overflow-x: auto;
		white-space: pre;
		margin: 0;
		max-height: 60vh;
		overflow-y: auto;
	}
	.error { color: var(--color-err); font-size: 0.85rem; }
	.empty { color: var(--text-placeholder); font-size: 0.85rem; }
</style>
