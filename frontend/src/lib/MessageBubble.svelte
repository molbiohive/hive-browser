<script>
	import Widget from '$lib/Widget.svelte';

	let { message } = $props();
</script>

<div class="row {message.role}">
	<div class="bubble {message.role}">
		<div class="content">{message.content}</div>

		{#if message.widget}
			<Widget widget={message.widget} />
		{/if}
	</div>
</div>

<style>
	.row {
		margin-bottom: 1rem;
		display: flex;
	}

	.row.user {
		justify-content: flex-end;
	}

	.row.assistant {
		justify-content: flex-start;
	}

	.bubble {
		border-radius: 12px;
		font-size: 0.9rem;
		line-height: 1.5;
	}

	.bubble.user {
		background: #e8e8e8;
		padding: 0.5rem 0.9rem;
		max-width: 60%;
		border-bottom-right-radius: 4px;
	}

	.bubble.assistant {
		max-width: 85%;
		padding: 0.75rem 1rem;
		background: white;
		border: 1px solid #e0e0e0;
		border-bottom-left-radius: 4px;
	}

	.content {
		white-space: pre-wrap;
	}
</style>
