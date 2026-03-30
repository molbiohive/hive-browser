<script>
	let {
		items = [],
		searchFields = [],
		placeholder = 'Search...',
		searchThreshold = 8,
		onRowClick = null,
		rowClass = null,
		head: headSnippet,
		row: rowSnippet,
		toolbar: toolbarSnippet = null,
		filtered = $bindable([]),
	} = $props();

	let search = $state('');

	$effect(() => {
		if (!search.trim()) {
			filtered = items;
		} else {
			const q = search.toLowerCase();
			filtered = items.filter(item =>
				searchFields.some(f => String(item[f] || '').toLowerCase().includes(q))
			);
		}
	});
</script>

<div class="picker-wrapper">
	{#if toolbarSnippet}
		<div class="picker-toolbar">
			{#if items.length > searchThreshold}
				<input type="text" class="picker-search" bind:value={search} {placeholder} />
			{/if}
			{@render toolbarSnippet()}
		</div>
	{:else if items.length > searchThreshold}
		<input type="text" class="picker-search" bind:value={search} {placeholder} />
	{/if}

	<div class="picker-table-wrap">
		<table class="picker-table">
			<thead>
				{@render headSnippet()}
			</thead>
			<tbody>
				{#each filtered as item}
					<!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
					<tr
						class="{onRowClick ? 'clickable' : ''} {rowClass ? rowClass(item) : ''}"
						onclick={() => onRowClick?.(item)}
						onkeydown={() => {}}
					>
						{@render rowSnippet(item)}
					</tr>
				{/each}
			</tbody>
		</table>
	</div>
</div>

<style>
	.picker-toolbar {
		display: flex;
		align-items: center;
		gap: 0.75rem;
		margin-bottom: 0.5rem;
	}

	.picker-search {
		flex: 1;
		padding: 0.45rem 0.75rem;
		border: 1px solid var(--border);
		border-radius: 8px;
		background: var(--bg-app);
		color: var(--text);
		font-size: 0.85rem;
		font-family: inherit;
		outline: none;
		box-sizing: border-box;
	}

	.picker-search:not(.picker-toolbar .picker-search) {
		width: 100%;
		margin-bottom: 0.5rem;
	}

	.picker-search:focus {
		border-color: var(--color-accent);
	}

	.picker-table-wrap {
		max-height: 320px;
		overflow-y: auto;
		border: 1px solid var(--border);
		border-radius: 8px;
	}

	.picker-table {
		width: 100%;
		border-collapse: collapse;
		font-size: 0.82rem;
	}

	.picker-table thead {
		position: sticky;
		top: 0;
		background: var(--bg-surface);
		z-index: 1;
	}

	.picker-table :global(th) {
		text-align: left;
		padding: 0.4rem 0.6rem;
		font-weight: 600;
		color: var(--text-faint);
		font-size: 0.75rem;
		text-transform: uppercase;
		letter-spacing: 0.03em;
		border-bottom: 1px solid var(--border);
	}

	.picker-table :global(td) {
		padding: 0.35rem 0.6rem;
		color: var(--text);
		border-bottom: 1px solid var(--border-muted, var(--border));
	}

	.picker-table tbody :global(tr.clickable) {
		cursor: pointer;
		transition: background 0.1s;
	}

	.picker-table tbody :global(tr.clickable:hover) {
		background: var(--bg-hover);
	}

	.picker-table tbody :global(tr.selected) {
		background: var(--bg-active);
	}
</style>
