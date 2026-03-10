<script>
	/**
	 * Reusable tab bar component.
	 * @param tabs - Array of { id: string, label: string }
	 * @param active - Currently active tab id
	 * @param onchange - Callback when tab is selected
	 * @param variant - Visual style: "underline" (default) or "pill"
	 */
	let { tabs = [], active = '', onchange = () => {}, variant = 'underline' } = $props();
</script>

{#if tabs.length > 1}
<div class="tab-bar" class:pill={variant === 'pill'}>
	{#each tabs as tab}
		<button
			class="tab-btn"
			class:active={active === tab.id}
			onclick={() => onchange(tab.id)}
		>{tab.label}</button>
	{/each}
</div>
{/if}

<style>
	/* Underline variant (default) */
	.tab-bar {
		display: flex;
		gap: 0;
		border-bottom: 1px solid var(--border-muted);
	}
	.tab-btn {
		padding: 0.4rem 0.75rem;
		background: none;
		border: none;
		border-bottom: 2px solid transparent;
		cursor: pointer;
		font-size: 0.78rem;
		color: var(--text-faint);
		font-weight: 500;
		font-family: inherit;
	}
	.tab-btn:hover { color: var(--text-muted); }
	.tab-btn.active {
		color: var(--text-secondary);
		border-bottom-color: var(--color-accent);
	}

	/* Pill variant */
	.tab-bar.pill {
		gap: 2px;
		background: var(--bg-app);
		border-radius: 6px;
		padding: 2px;
		border-bottom: none;
		margin-bottom: 0.5rem;
	}
	.pill .tab-btn {
		flex: 1;
		padding: 0.3rem 0.5rem;
		border-bottom: none;
		border-radius: 4px;
		font-size: 0.75rem;
		transition: background 0.15s, color 0.15s;
	}
	.pill .tab-btn:hover { color: var(--text); }
	.pill .tab-btn.active {
		background: var(--bg-surface);
		color: var(--text);
		font-weight: 600;
		border-bottom-color: transparent;
	}
</style>
