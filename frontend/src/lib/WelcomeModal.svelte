<script>
	import { onMount } from 'svelte';
	import { createUser, loginUser, fetchUsers, userList } from '$lib/stores/user.ts';
	import { connect, fetchChatList } from '$lib/stores/chat.ts';

	let { mode = 'return', onCancel = undefined } = $props();

	const returnMessages = [
		'The Hive is waiting for you!',
		'Welcome back, busy bee!',
		'Your colony missed you.',
		'Back to the hive, excellent!',
		'The swarm reconnects.',
	];

	const newMessages = [
		'Oh, a new one! Ready to join the Hive?',
		'Welcome, worker bee. The colony awaits.',
		'Another mind for the swarm. Excellent.',
		'The hive grows stronger with each new member.',
		'Bzz... fresh talent detected.',
		'Your cell in the hive is ready.',
		'The queen welcomes you to the colony.',
		'New bee orientation: step one, pick a name.',
		'Pollen collected. Now, who are you?',
		'The waggle dance of registration begins.',
	];

	const isReturn = $derived(mode === 'return');
	const pool = $derived(isReturn ? returnMessages : newMessages);
	// Pick greeting once on mount (not reactive — intentional)
	let greeting = $state(newMessages[0]);
	const usernameRe = /^[a-zA-Z0-9\-_ ]+$/;

	let username = $state('');
	let error = $state('');
	let submitting = $state(false);
	let selectedSlug = $state('');

	const isValid = $derived(
		username.trim().length > 0 &&
		username.trim().length <= 50 &&
		usernameRe.test(username.trim())
	);

	onMount(() => {
		greeting = pool[Math.floor(Math.random() * pool.length)];
		if (isReturn) fetchUsers();
	});

	async function handleLogin() {
		if (!selectedSlug || submitting) return;
		submitting = true;
		error = '';
		try {
			await loginUser(selectedSlug);
			connect();
			fetchChatList();
		} catch (e) {
			error = e instanceof Error ? e.message : 'Login failed';
		} finally {
			submitting = false;
		}
	}

	async function handleCreate() {
		if (!isValid || submitting) return;
		submitting = true;
		error = '';
		try {
			await createUser(username.trim());
			await fetchUsers();
			connect();
			fetchChatList();
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to create user';
		} finally {
			submitting = false;
		}
	}

	function handleKeydown(e) {
		if (e.key === 'Enter') {
			e.preventDefault();
			if (isReturn && selectedSlug) {
				handleLogin();
			} else if (isValid) {
				handleCreate();
			}
		}
	}
</script>

<div class="modal-overlay">
	<div class="modal-card">
		<img src="/logo.svg" alt="Hive Browser" class="modal-logo" />
		<p class="greeting">{greeting}</p>

		{#if isReturn}
			<div class="form">
				{#if $userList.length > 0}
					<select
						class="user-select"
						bind:value={selectedSlug}
					>
						<option value="" disabled>Select your name</option>
						{#each $userList as user}
							<option value={user.slug}>{user.username}</option>
						{/each}
					</select>
					<button
						class="join-btn"
						onclick={handleLogin}
						disabled={!selectedSlug || submitting}
					>
						{submitting ? 'Joining...' : 'Return to Hive'}
					</button>
				{/if}
				{#if error}
					<p class="error">{error}</p>
				{/if}
				<p class="hint">New here? Type a username to join.</p>
				<input
					type="text"
					bind:value={username}
					onkeydown={handleKeydown}
					placeholder="Enter a new username"
					maxlength="50"
				/>
				<button
					class="join-btn secondary"
					onclick={handleCreate}
					disabled={!isValid || submitting}
				>
					{submitting ? 'Creating...' : 'Join the Hive'}
				</button>
			</div>
		{:else}
			<div class="form">
				<input
					type="text"
					bind:value={username}
					onkeydown={handleKeydown}
					placeholder="Enter your name"
					maxlength="50"
				/>
				{#if error}
					<p class="error">{error}</p>
				{/if}
				<button
					class="join-btn"
					onclick={handleCreate}
					disabled={!isValid || submitting}
				>
					{submitting ? 'Joining...' : 'Join the Hive'}
				</button>
				{#if onCancel}
					<button class="cancel-btn" onclick={onCancel}>
						Cancel
					</button>
				{/if}
			</div>
		{/if}
	</div>
</div>

<style>
	.modal-overlay {
		position: fixed;
		inset: 0;
		background: rgba(0, 0, 0, 0.5);
		display: flex;
		align-items: center;
		justify-content: center;
		z-index: 1000;
	}

	.modal-card {
		background: var(--bg-surface);
		border: 1px solid var(--border);
		border-radius: 16px;
		padding: 2.5rem 2rem;
		max-width: 380px;
		width: 90%;
		text-align: center;
		box-shadow: 0 8px 32px var(--shadow);
	}

	.modal-logo {
		width: 64px;
		height: 64px;
		margin-bottom: 1rem;
		opacity: 0.8;
	}

	.greeting {
		font-size: 1.1rem;
		color: var(--text);
		margin: 0 0 1.5rem;
		line-height: 1.4;
	}

	.form {
		display: flex;
		flex-direction: column;
		gap: 0.75rem;
	}

	input, .user-select {
		padding: 0.6rem 0.8rem;
		border: 1px solid var(--border);
		border-radius: 8px;
		background: var(--bg-app);
		color: var(--text);
		font-size: 0.95rem;
		outline: none;
		font-family: inherit;
	}

	.user-select {
		cursor: pointer;
		appearance: none;
		background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 24 24' fill='none' stroke='%23888' stroke-width='2'%3E%3Cpath d='M6 9l6 6 6-6'/%3E%3C/svg%3E");
		background-repeat: no-repeat;
		background-position: right 0.8rem center;
		padding-right: 2rem;
	}

	input:focus, .user-select:focus {
		border-color: var(--color-accent);
	}

	input::placeholder {
		color: var(--text-placeholder);
	}

	.error {
		color: var(--color-err);
		font-size: 0.8rem;
		margin: 0;
	}

	.hint {
		color: var(--text-faint);
		font-size: 0.8rem;
		margin: 0.5rem 0 0;
	}

	.join-btn {
		padding: 0.6rem 1rem;
		background: var(--btn-bg);
		color: var(--btn-fg);
		border: none;
		border-radius: 8px;
		font-size: 0.95rem;
		cursor: pointer;
		font-family: inherit;
		transition: background 0.15s;
	}

	.join-btn.secondary {
		background: var(--bg-hover);
		color: var(--text-secondary);
	}

	.join-btn.secondary:hover:not(:disabled) {
		background: var(--border);
	}

	.join-btn:hover:not(:disabled) {
		background: var(--btn-hover);
	}

	.join-btn:disabled {
		opacity: 0.4;
		cursor: default;
	}

	.cancel-btn {
		padding: 0.5rem 1rem;
		background: none;
		border: none;
		color: var(--text-faint);
		font-size: 0.85rem;
		cursor: pointer;
		font-family: inherit;
	}

	.cancel-btn:hover {
		color: var(--text);
	}
</style>
