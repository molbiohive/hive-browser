<script>
	import { modelList, currentModel, setModel } from '$lib/stores/chat.ts';

	let open = $state(false);
	let dropdownEl;
	let ollamaModels = $state([]);
	let fetchedOllama = $state(false);

	const shortName = $derived(
		$currentModel ? $currentModel.split('/').slice(1).join('/') : 'none'
	);

	async function toggle() {
		open = !open;
		if (open && !fetchedOllama) {
			try {
				const res = await fetch('/api/models');
				if (res.ok) {
					const data = await res.json();
					ollamaModels = data.ollama || [];
				}
			} catch (e) {
				console.warn('[models] fetch failed:', e);
			}
			fetchedOllama = true;
		}
	}

	function select(id) {
		setModel(id);
		open = false;
	}

	function handleKeydown(e) {
		if (e.key === 'Escape') open = false;
	}

	function handleClickOutside(e) {
		if (dropdownEl && !dropdownEl.contains(e.target)) {
			open = false;
		}
	}

	$effect(() => {
		if (open) {
			document.addEventListener('click', handleClickOutside, true);
			document.addEventListener('keydown', handleKeydown);
		} else {
			document.removeEventListener('click', handleClickOutside, true);
			document.removeEventListener('keydown', handleKeydown);
		}
		return () => {
			document.removeEventListener('click', handleClickOutside, true);
			document.removeEventListener('keydown', handleKeydown);
		};
	});
</script>

<div class="model-selector" bind:this={dropdownEl}>
	<button class="model-btn" onclick={toggle} class:active={open} title="Select model">
		<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
			<rect x="2" y="4" width="20" height="16" rx="2" />
			<circle cx="8" cy="12" r="1.5" fill="currentColor" stroke="none" />
			<circle cx="16" cy="12" r="1.5" fill="currentColor" stroke="none" />
			<path d="M9 16h6" />
		</svg>
		<span class="model-name">{shortName}</span>
	</button>

	{#if open}
		<div class="dropdown">
			{#if $modelList.length > 0}
				<div class="section-label">Configured</div>
				{#each $modelList as m}
					<button
						class="dropdown-item"
						class:selected={$currentModel === m.id}
						onclick={() => select(m.id)}
					>
						<span class="item-name">{m.model}</span>
						<span class="item-provider">{m.provider}</span>
					</button>
				{/each}
			{/if}

			{#if ollamaModels.length > 0}
				<div class="section-label">Ollama</div>
				{#each ollamaModels as m}
					<button
						class="dropdown-item"
						class:selected={$currentModel === m.id}
						onclick={() => select(m.id)}
					>
						<span class="item-name">{m.model}</span>
						<span class="item-provider">ollama</span>
					</button>
				{/each}
			{/if}
		</div>
	{/if}
</div>

<style>
	.model-selector {
		position: relative;
	}

	.model-btn {
		display: flex;
		align-items: center;
		gap: 0.35rem;
		background: none;
		border: none;
		cursor: pointer;
		color: var(--text-hint);
		font-size: 0.7rem;
		padding: 0.15rem 0.3rem;
		border-radius: 4px;
	}

	.model-btn:hover,
	.model-btn.active {
		color: var(--text-secondary);
		background: var(--bg-hover);
	}

	.model-name {
		max-width: 120px;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}

	.dropdown {
		position: absolute;
		bottom: 100%;
		left: 0;
		margin-bottom: 4px;
		background: var(--bg-surface);
		border: 1px solid var(--border);
		border-radius: 8px;
		box-shadow: 0 4px 16px var(--shadow);
		min-width: 200px;
		max-height: 300px;
		overflow-y: auto;
		z-index: 100;
		padding: 0.25rem;
	}

	.section-label {
		font-size: 0.65rem;
		text-transform: uppercase;
		color: var(--text-faint);
		letter-spacing: 0.05em;
		padding: 0.4rem 0.5rem 0.2rem;
	}

	.dropdown-item {
		display: flex;
		justify-content: space-between;
		align-items: center;
		width: 100%;
		padding: 0.4rem 0.5rem;
		border: none;
		background: transparent;
		border-radius: 4px;
		cursor: pointer;
		font-size: 0.78rem;
		color: var(--text);
		text-align: left;
	}

	.dropdown-item:hover {
		background: var(--bg-hover);
	}

	.dropdown-item.selected {
		background: var(--bg-active);
		font-weight: 600;
	}

	.item-provider {
		font-size: 0.65rem;
		color: var(--text-placeholder);
	}
</style>
