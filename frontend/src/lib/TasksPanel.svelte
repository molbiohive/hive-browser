<script>
	import { tasks, addTask, toggleTask, removeTask } from '$lib/stores/chat.ts';
	let newText = $state('');

	function handleAdd() {
		const text = newText.trim();
		if (!text) return;
		addTask(text);
		newText = '';
	}

	function handleKeydown(e) {
		if (e.key === 'Enter') {
			e.preventDefault();
			handleAdd();
		}
	}
</script>

{#if $tasks.length > 0}
<div class="tasks-panel">
	<div class="tasks-header">Tasks</div>
	<ul class="task-list">
		{#each $tasks as task (task.id)}
			<li class="task-item" class:done={task.done}>
				<label class="task-check">
					<input
						type="checkbox"
						checked={task.done}
						onchange={() => toggleTask(task.id)}
					/>
					<span class="task-text">{task.text}</span>
				</label>
				<button class="task-remove" onclick={() => removeTask(task.id)} aria-label="Remove task">&times;</button>
			</li>
		{/each}
	</ul>
	<div class="task-add">
		<input
			type="text"
			bind:value={newText}
			onkeydown={handleKeydown}
			placeholder="Add a task..."
		/>
		<button onclick={handleAdd} disabled={!newText.trim()}>+</button>
	</div>
</div>
{/if}

<style>
	.tasks-panel {
		margin-top: 0.5rem;
		border: 1px solid var(--border);
		border-radius: 8px;
		padding: 0.5rem 0.75rem;
		background: var(--bg-surface);
	}

	.tasks-header {
		font-size: 0.72rem;
		font-weight: 600;
		text-transform: uppercase;
		letter-spacing: 0.05em;
		color: var(--text-faint);
		margin-bottom: 0.35rem;
	}

	.task-list {
		list-style: none;
		margin: 0;
		padding: 0;
	}

	.task-item {
		display: flex;
		align-items: center;
		justify-content: space-between;
		padding: 0.2rem 0;
		font-size: 0.82rem;
	}

	.task-check {
		display: flex;
		align-items: center;
		gap: 0.4rem;
		cursor: pointer;
		flex: 1;
		min-width: 0;
	}

	.task-check input[type="checkbox"] {
		margin: 0;
		cursor: pointer;
	}

	.task-text {
		color: var(--text);
	}

	.task-item.done .task-text {
		text-decoration: line-through;
		color: var(--text-placeholder);
	}

	.task-remove {
		background: none;
		border: none;
		cursor: pointer;
		color: var(--text-placeholder);
		font-size: 1rem;
		line-height: 1;
		padding: 0 0.2rem;
		border-radius: 3px;
		flex-shrink: 0;
		visibility: hidden;
	}

	.task-item:hover .task-remove {
		visibility: visible;
	}

	.task-remove:hover {
		color: var(--color-err);
		background: rgba(220, 38, 38, 0.1);
	}

	.task-add {
		display: flex;
		gap: 0.3rem;
		margin-top: 0.35rem;
	}

	.task-add input {
		flex: 1;
		border: 1px solid var(--border);
		border-radius: 4px;
		padding: 0.25rem 0.4rem;
		font-size: 0.78rem;
		background: var(--bg-app);
		color: var(--text);
		outline: none;
	}

	.task-add input::placeholder {
		color: var(--text-placeholder);
	}

	.task-add input:focus {
		border-color: var(--color-accent);
	}

	.task-add button {
		border: 1px solid var(--border);
		border-radius: 4px;
		padding: 0.2rem 0.5rem;
		background: var(--bg-muted);
		color: var(--text-secondary);
		cursor: pointer;
		font-size: 0.82rem;
	}

	.task-add button:hover:not(:disabled) {
		background: var(--bg-hover);
	}

	.task-add button:disabled {
		opacity: 0.4;
		cursor: default;
	}
</style>
