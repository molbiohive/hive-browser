<script>
	let { visible, onSelect } = $props();

	const commands = [
		{ name: 'search', description: 'Search by name, features, resistance, metadata' },
		{ name: 'blast', description: 'Sequence similarity search (BLAST+)' },
		{ name: 'profile', description: 'Full details of a sequence' },
		{ name: 'browse', description: 'Navigate project directory tree' },
		{ name: 'status', description: 'System health and index stats' },
		{ name: 'help', description: 'Show available commands' },
	];

	function select(cmd) {
		onSelect?.(cmd.name);
	}
</script>

{#if visible}
<div class="palette">
	{#each commands as cmd}
		<button class="cmd" onclick={() => select(cmd)}>
			<span class="name">/{cmd.name}</span>
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
	.desc { color: #888; }
</style>
