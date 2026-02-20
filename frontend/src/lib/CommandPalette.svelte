<script>
	import { toolList } from '$lib/stores/chat.ts';

	let { visible, filter = '', maxVisible = 5, onSelect } = $props();

	const builtins = [
		{ name: 'help', description: 'Show available commands' },
	];

	const allCommands = $derived([
		...$toolList.filter(t => !t.tags?.includes('hidden')),
		...builtins,
	]);

	function fuzzyMatch(name, query) {
		if (!query) return true;
		const q = query.toLowerCase();
		const n = name.toLowerCase();
		// Substring match first
		if (n.includes(q)) return true;
		// Fuzzy: all query chars appear in order
		let qi = 0;
		for (let i = 0; i < n.length && qi < q.length; i++) {
			if (n[i] === q[qi]) qi++;
		}
		return qi === q.length;
	}

	function matchScore(name, query) {
		if (!query) return 0;
		const q = query.toLowerCase();
		const n = name.toLowerCase();
		if (n === q) return 3;                // exact
		if (n.startsWith(q)) return 2;        // prefix
		if (n.includes(q)) return 1;          // substring
		return 0;                             // fuzzy
	}

	const commands = $derived.by(() => {
		const q = filter.toLowerCase();
		return allCommands
			.filter(cmd => fuzzyMatch(cmd.name, q))
			.sort((a, b) => matchScore(b.name, q) - matchScore(a.name, q))
			.slice(0, maxVisible);
	});

	function select(cmd) {
		onSelect?.(cmd.name);
	}
</script>

{#if visible && commands.length > 0}
<div class="palette">
	{#each commands as cmd}
		<button class="cmd" onclick={() => select(cmd)}>
			<span class="name">/{cmd.name}</span>
			{#if cmd.tags}
				{#each cmd.tags as tag}
					<span class="tag">{tag}</span>
				{/each}
			{/if}
			<span class="desc">{cmd.description}</span>
		</button>
	{/each}
</div>
{/if}

<style>
	.palette {
		position: absolute;
		bottom: 100%;
		left: 0;
		right: 0;
		background: white;
		border: 1px solid #ddd;
		border-radius: 8px;
		box-shadow: 0 -4px 16px rgba(0,0,0,0.08);
		max-height: 300px;
		overflow-y: auto;
	}
	.cmd {
		display: flex;
		gap: 1rem;
		width: 100%;
		padding: 0.6rem 0.75rem;
		border: none;
		background: none;
		cursor: pointer;
		text-align: left;
		font-size: 0.85rem;
	}
	.cmd:hover { background: #f5f5f5; }
	.name { font-weight: 600; min-width: 80px; color: #333; }
	.tag {
		font-size: 0.65rem;
		padding: 0.1rem 0.35rem;
		background: #eee;
		color: #666;
		border-radius: 3px;
		text-transform: uppercase;
		letter-spacing: 0.03em;
	}
	.desc { color: #888; }
</style>
