<script>
	import { currentUser, userList, fetchUsers, switchUser, loginUser } from '$lib/stores/user.ts';
	import { reconnect } from '$lib/stores/chat.ts';

	let { onAddUser = () => {} } = $props();
	let open = $state(false);

	function togglePopup() {
		if (!open) fetchUsers();
		open = !open;
	}

	async function handleSwitch(slug) {
		if (slug === $currentUser?.slug) {
			open = false;
			return;
		}
		if (switchUser(slug)) {
			open = false;
			reconnect();
			return;
		}
		// Token not in localStorage — fetch from server
		try {
			await loginUser(slug);
			open = false;
			reconnect();
		} catch (e) {
			console.warn('[user] switch failed:', e);
		}
	}

	function handleAdd() {
		open = false;
		onAddUser();
	}

	function handleClickOutside(e) {
		if (!e.target.closest('.user-picker')) {
			open = false;
		}
	}
</script>

<svelte:window onclick={handleClickOutside} />

<div class="user-picker">
	<button class="user-btn" onclick={togglePopup}>
		{$currentUser?.username || '...'}
	</button>
	{#if open}
		<div class="popup">
			{#each $userList as user}
				<button
					class="popup-item"
					class:active={user.slug === $currentUser?.slug}
					onclick={() => handleSwitch(user.slug)}
				>
					{user.username}
				</button>
			{/each}
			<div class="popup-sep"></div>
			<button class="popup-item add" onclick={handleAdd}>+ New user</button>
		</div>
	{/if}
</div>

<style>
	.user-picker {
		position: relative;
	}

	.user-btn {
		background: none;
		border: none;
		cursor: pointer;
		color: var(--text-secondary);
		font-size: 0.8rem;
		padding: 0.25rem 0.4rem;
		border-radius: 4px;
		font-family: inherit;
		max-width: 140px;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}

	.user-btn:hover {
		color: var(--text);
		background: var(--bg-hover);
	}

	.popup {
		position: absolute;
		bottom: 100%;
		left: 0;
		margin-bottom: 4px;
		background: var(--bg-surface);
		border: 1px solid var(--border);
		border-radius: 8px;
		padding: 0.3rem;
		min-width: 160px;
		box-shadow: 0 4px 16px var(--shadow);
		z-index: 100;
	}

	.popup-item {
		display: block;
		width: 100%;
		text-align: left;
		padding: 0.4rem 0.6rem;
		border: none;
		background: none;
		border-radius: 4px;
		cursor: pointer;
		font-size: 0.82rem;
		color: var(--text);
		font-family: inherit;
	}

	.popup-item:hover {
		background: var(--bg-hover);
	}

	.popup-item.active {
		color: var(--color-accent);
		font-weight: 600;
	}

	.popup-item.add {
		color: var(--text-faint);
	}

	.popup-sep {
		height: 1px;
		background: var(--border);
		margin: 0.2rem 0.4rem;
	}
</style>
