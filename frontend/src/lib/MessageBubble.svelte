<script>
	import { marked } from 'marked';
	import Widget from '$lib/Widget.svelte';
	import ChainSteps from '$lib/ChainSteps.svelte';

	let { message, faded = false, messageIndex = -1 } = $props();

	// Configure marked for inline rendering (no wrapping <p> for short responses)
	marked.setOptions({ breaks: true, gfm: true });

	const rendered = $derived(
		message.role === 'assistant' ? marked.parse(message.content || '') : ''
	);
</script>

<div class="row {message.role}" class:faded>
	<div class="bubble {message.role}">
		{#if message.role === 'assistant'}
			<div class="content markdown">{@html rendered}</div>
		{:else}
			<div class="content">{message.content}</div>
		{/if}

		{#if message.widget}
			<Widget widget={message.widget} {messageIndex} />
			{#if message.widget.chain}
				<ChainSteps chain={message.widget.chain} />
			{/if}
		{/if}
	</div>
</div>

<style>
	.row {
		margin-bottom: 1rem;
		display: flex;
	}

	.row.faded {
		opacity: 0.35;
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
		overflow-wrap: break-word;
		word-break: break-word;
		min-width: 0;
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
		overflow-wrap: break-word;
	}

	/* Markdown styles for assistant messages */
	.markdown {
		white-space: normal;
	}

	.markdown :global(p) {
		margin: 0 0 0.5rem;
	}

	.markdown :global(p:last-child) {
		margin-bottom: 0;
	}

	.markdown :global(h1),
	.markdown :global(h2),
	.markdown :global(h3) {
		margin: 0.75rem 0 0.4rem;
		font-size: 1rem;
		font-weight: 600;
	}

	.markdown :global(h1) { font-size: 1.1rem; }

	.markdown :global(ul),
	.markdown :global(ol) {
		margin: 0.3rem 0;
		padding-left: 1.5rem;
	}

	.markdown :global(li) {
		margin-bottom: 0.15rem;
	}

	.markdown :global(code) {
		background: #f0f0f0;
		padding: 0.1rem 0.35rem;
		border-radius: 3px;
		font-family: 'SF Mono', Monaco, monospace;
		font-size: 0.82rem;
	}

	.markdown :global(pre) {
		background: #f5f5f5;
		border: 1px solid #e0e0e0;
		border-radius: 6px;
		padding: 0.6rem 0.8rem;
		overflow-x: auto;
		margin: 0.4rem 0;
	}

	.markdown :global(pre code) {
		background: none;
		padding: 0;
	}

	.markdown :global(strong) {
		font-weight: 600;
	}

	.markdown :global(a) {
		color: #2563eb;
		text-decoration: none;
	}

	.markdown :global(a:hover) {
		text-decoration: underline;
	}

	.markdown :global(blockquote) {
		border-left: 3px solid #ddd;
		margin: 0.4rem 0;
		padding: 0.2rem 0.8rem;
		color: #666;
	}

	.markdown :global(table) {
		width: 100%;
		border-collapse: collapse;
		margin: 0.4rem 0;
	}

	.markdown :global(th),
	.markdown :global(td) {
		padding: 0.3rem 0.5rem;
		text-align: left;
		border-bottom: 1px solid #e0e0e0;
	}

	.markdown :global(th) {
		font-weight: 600;
		font-size: 0.8rem;
		color: #888;
	}
</style>
