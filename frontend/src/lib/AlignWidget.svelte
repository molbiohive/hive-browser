<script>
	import { copyToClipboard } from '$lib/clipboard.ts';
	import { AlignmentViewer } from '@molbiohive/hatchlings';

	let { data } = $props();
	let copied = $state(false);
	let containerEl = $state(undefined);
	let containerWidth = $state(800);

	// Parse FASTA into AlignmentSequence[]
	const sequences = $derived.by(() => {
		if (!data?.aligned) return [];
		const lines = data.aligned.split('\n');
		const seqs = [];
		let current = null;
		for (const line of lines) {
			if (line.startsWith('>')) {
				if (current) seqs.push(current);
				const name = line.slice(1).trim();
				current = { id: name, name, sequence: '' };
			} else if (current) {
				current.sequence += line.trim();
			}
		}
		if (current) seqs.push(current);
		return seqs;
	});

	// Auto-detect alphabet from first sequence
	const alphabet = $derived.by(() => {
		if (!sequences.length) return 'dna';
		const sample = sequences[0].sequence.replace(/-/g, '').toUpperCase();
		if (/U/.test(sample) && !/[DEFHIKLMPQRSVWY]/.test(sample)) return 'rna';
		if (/[DEFHIKLMPQRSVWY]/.test(sample)) return 'protein';
		return 'dna';
	});

	const alignmentData = $derived(
		sequences.length ? { sequences, alphabet, name: data.name } : null
	);

	const alignLength = $derived(sequences.length ? sequences[0].sequence.length : 0);

	// Track container width for responsive sizing
	$effect(() => {
		if (!containerEl) return;
		const ro = new ResizeObserver(([e]) => {
			containerWidth = e.contentRect.width;
		});
		ro.observe(containerEl);
		return () => ro.disconnect();
	});

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
{:else if alignmentData}
<div class="align-widget" bind:this={containerEl}>
	<div class="meta">
		<span><strong>Sequences:</strong> {data.count || sequences.length}</span>
		<span><strong>Length:</strong> {alignLength}</span>
		<span><strong>Type:</strong> {alphabet}</span>
		<button class="copy-btn" onclick={copyAlignment}>
			{copied ? 'Copied!' : 'Copy FASTA'}
		</button>
	</div>
	<div class="viewer-wrap">
		<AlignmentViewer data={alignmentData}
			width={Math.max(400, containerWidth - 2)}
			height={Math.min(500, 60 + sequences.length * 20)}
			showConsensus={true}
			showConservation={sequences.length > 2}
			showNames={true} />
	</div>
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
	.viewer-wrap {
		border-radius: 6px;
		overflow: hidden;
		border: 1px solid var(--border-muted);
	}
	.error { color: var(--color-err); font-size: 0.85rem; }
	.empty { color: var(--text-placeholder); font-size: 0.85rem; }
</style>
