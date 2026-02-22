<script>
	import { createUser, fetchUsers } from '$lib/stores/user.ts';
	import { connect, fetchChatList } from '$lib/stores/chat.ts';

	const welcomeMessages = [
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

	const greeting = welcomeMessages[Math.floor(Math.random() * welcomeMessages.length)];
	const usernameRe = /^[a-zA-Z0-9\-_ ]+$/;

	let username = $state('');
	let error = $state('');
	let submitting = $state(false);

	const isValid = $derived(
		username.trim().length > 0 &&
		username.trim().length <= 50 &&
		usernameRe.test(username.trim())
	);

	async function handleSubmit() {
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
			handleSubmit();
		}
	}
</script>

<div class="modal-overlay">
	<div class="modal-card">
		<img src="/logo.svg" alt="Hive Browser" class="modal-logo" />
		<p class="greeting">{greeting}</p>
		<div class="form">
			<input
				type="text"
				bind:value={username}
				onkeydown={handleKeydown}
				placeholder="Enter your name"
				maxlength="50"
				autofocus
			/>
			{#if error}
				<p class="error">{error}</p>
			{/if}
			<button
				class="join-btn"
				onclick={handleSubmit}
				disabled={!isValid || submitting}
			>
				{submitting ? 'Joining...' : 'Join the Hive'}
			</button>
		</div>
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

	input {
		padding: 0.6rem 0.8rem;
		border: 1px solid var(--border);
		border-radius: 8px;
		background: var(--bg-app);
		color: var(--text);
		font-size: 0.95rem;
		outline: none;
		font-family: inherit;
	}

	input:focus {
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

	.join-btn:hover:not(:disabled) {
		background: var(--btn-hover);
	}

	.join-btn:disabled {
		opacity: 0.4;
		cursor: default;
	}
</style>
