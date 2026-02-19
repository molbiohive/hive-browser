<script>
	import { toolList } from '$lib/stores/chat.ts';

	let { visible, onSelect } = $props();

	const builtins = [
		{ name: 'help', description: 'Show available commands' },
	];

	const commands = $derived([
		...$toolList.filter(t => !t.tags?.includes('hidden')),
		...builtins,
	]);

	function select(cmd) {
		onSelect?.(cmd.name);
	}
</script>

{#if visible}
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
