<script>
	import { submitFeedback } from './stores/chat.ts';

	let { onClose } = $props();

	let comment = $state('');
	let priority = $state(3);
	let submitting = $state(false);

	function handleSubmit(rating) {
		submitting = true;
		submitFeedback(rating, priority, comment.trim());
		submitting = false;
		onClose();
	}
</script>

<div class="modal-overlay" role="dialog" aria-label="Feedback">
	<div class="modal-card">
		<h2>Send Feedback</h2>

		<label class="field-label">
			Comment
			<textarea
				bind:value={comment}
				placeholder="Describe your experience, issues, or suggestions..."
				rows="6"
				disabled={submitting}
			></textarea>
		</label>

		<label class="field-label">
			Priority (1 = low, 5 = critical)
			<input
				type="number"
				bind:value={priority}
				min="1"
				max="5"
				disabled={submitting}
			/>
		</label>

		<div class="actions">
			<button
				class="btn btn-good"
				onclick={() => handleSubmit('good')}
				disabled={submitting}
			>Good</button>
			<button
				class="btn btn-bad"
				onclick={() => handleSubmit('bad')}
				disabled={submitting}
			>Bad</button>
			<button
				class="btn btn-cancel"
				onclick={onClose}
				disabled={submitting}
			>Cancel</button>
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
		z-index: 1001;
	}

	.modal-card {
		background: var(--bg-surface);
		border: 1px solid var(--border);
		border-radius: 12px;
		padding: 24px;
		width: 420px;
		max-width: 90vw;
		box-shadow: 0 8px 32px var(--shadow);
	}

	h2 {
		margin: 0 0 16px;
		font-size: 1.1rem;
		color: var(--text);
	}

	.field-label {
		display: block;
		font-size: 0.85rem;
		color: var(--text-secondary);
		margin-bottom: 12px;
	}

	textarea {
		display: block;
		width: 100%;
		margin-top: 6px;
		padding: 10px;
		border: 1px solid var(--border);
		border-radius: 6px;
		background: var(--bg-muted);
		color: var(--text);
		font-family: inherit;
		font-size: 0.9rem;
		resize: vertical;
		box-sizing: border-box;
	}

	textarea:focus {
		outline: none;
		border-color: var(--color-accent);
	}

	input[type="number"] {
		display: block;
		width: 80px;
		margin-top: 6px;
		padding: 8px 10px;
		border: 1px solid var(--border);
		border-radius: 6px;
		background: var(--bg-muted);
		color: var(--text);
		font-family: inherit;
		font-size: 0.9rem;
	}

	input[type="number"]:focus {
		outline: none;
		border-color: var(--color-accent);
	}

	.actions {
		display: flex;
		gap: 8px;
		margin-top: 16px;
	}

	.btn {
		flex: 1;
		padding: 10px 16px;
		border: none;
		border-radius: 6px;
		font-size: 0.9rem;
		font-weight: 500;
		cursor: pointer;
		transition: opacity 0.15s;
	}

	.btn:disabled {
		opacity: 0.5;
		cursor: default;
	}

	.btn-good {
		background: var(--color-ok);
		color: #fff;
	}

	.btn-bad {
		background: var(--color-err);
		color: #fff;
	}

	.btn-cancel {
		background: var(--bg-hover);
		color: var(--text-secondary);
	}
</style>
