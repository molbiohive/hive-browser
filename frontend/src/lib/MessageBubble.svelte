<script>
	import { marked } from 'marked';
	import DOMPurify from 'dompurify';
	import Widget from '$lib/Widget.svelte';
	import ChainSteps from '$lib/ChainSteps.svelte';

	let { message, messageIndex = -1 } = $props();
	let thinkingExpanded = $state(false);

	// Configure marked for inline rendering (no wrapping <p> for short responses)
	marked.setOptions({ breaks: true, gfm: true });

	const rendered = $derived(
		message.role === 'assistant' ? DOMPurify.sanitize(marked.parse(message.content || '')) : ''
	);

	function formatTime(iso) {
		if (!iso) return '';
		const d = new Date(iso);
		return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: false });
	}

	function compactNum(n) {
		if (n == null) return '';
		if (n >= 1000) return (n / 1000).toFixed(1) + 'k';
		return String(n);
	}
</script>

<div class="row {message.role}">
	<div class="msg-wrapper">
		<div class="bubble {message.role}" class:has-widget={!!message.widget}>
			{#if message.role === 'assistant'}
				{#if message.thinking}
					<div class="thinking-block">
						<button class="thinking-toggle" onclick={() => thinkingExpanded = !thinkingExpanded}>
							Thinking
							<span class="arrow">{thinkingExpanded ? '\u25B4' : '\u25BE'}</span>
						</button>
						{#if thinkingExpanded}
							<pre class="thinking-content">{message.thinking}</pre>
						{/if}
					</div>
				{/if}
				<div class="content markdown">{@html rendered}</div>
			{:else}
				<div class="content">{message.content}</div>
			{/if}

			{#if message.widget}
				<Widget widget={message.widget} {messageIndex} />
			{/if}
			{#if message.widget?.chain || message.chain}
				<ChainSteps chain={message.widget?.chain || message.chain} />
			{/if}
		</div>

		<div class="meta-row">
			{#if message.ts}
				<span class="meta-item">{formatTime(message.ts)}</span>
			{/if}
			{#if message.role === 'assistant' && message.tokens}
				<span class="meta-item tokens">
					<svg class="arrow up" width="10" height="10" viewBox="0 0 10 10"><path d="M5 2 L8 6 H2Z" fill="currentColor"/></svg>{compactNum(message.tokens.in)}
				</span>
				<span class="meta-item tokens">
					<svg class="arrow down" width="10" height="10" viewBox="0 0 10 10"><path d="M5 8 L8 4 H2Z" fill="currentColor"/></svg>{compactNum(message.tokens.out)}
				</span>
				{#if message.model}
					<span class="meta-item model">{message.model}</span>
				{/if}
			{/if}
		</div>
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

	.msg-wrapper {
		display: flex;
		flex-direction: column;
		min-width: 0;
	}

	.row.user .msg-wrapper { align-items: flex-end; }
	.row.assistant .msg-wrapper { align-items: flex-start; width: 100%; }

	.bubble {
		border-radius: 12px;
		font-size: 0.9rem;
		line-height: 1.5;
		overflow-wrap: break-word;
		word-break: break-word;
		min-width: 0;
	}

	.bubble.user {
		background: var(--bg-hover);
		padding: 0.5rem 0.9rem;
		max-width: 60%;
		border-bottom-right-radius: 4px;
	}

	.bubble.assistant {
		max-width: 85%;
		padding: 0.75rem 1rem;
		background: var(--bg-surface);
		border: 1px solid var(--border-muted);
		border-bottom-left-radius: 4px;
	}

	.bubble.assistant.has-widget {
		width: 85%;
	}

	.content {
		white-space: pre-wrap;
		overflow-wrap: break-word;
	}

	/* Metadata row — visible on hover */
	.meta-row {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		margin-top: 0.3rem;
		font-size: 0.7rem;
		color: var(--text-faint);
		opacity: 0;
		transition: opacity 0.15s;
		height: 1rem;
	}

	.msg-wrapper:hover .meta-row {
		opacity: 1;
	}

	.meta-item {
		display: inline-flex;
		align-items: center;
		gap: 0.15rem;
	}

	.tokens {
		font-family: 'SF Mono', Monaco, monospace;
		font-size: 0.65rem;
	}

	.arrow {
		opacity: 0.7;
	}

	.model {
		opacity: 0.6;
	}

	/* Thinking block — collapsible reasoning */
	.thinking-block {
		margin-bottom: 0.5rem;
	}

	.thinking-toggle {
		display: inline-flex;
		align-items: center;
		gap: 0.3rem;
		padding: 0.2rem 0.5rem;
		background: var(--bg-muted);
		border: 1px solid var(--border);
		border-radius: 4px;
		cursor: pointer;
		font-size: 0.75rem;
		color: var(--text-muted);
	}

	.thinking-toggle:hover {
		background: var(--bg-hover);
	}

	.thinking-content {
		margin: 0.4rem 0 0;
		padding: 0.5rem 0.75rem;
		background: var(--bg-muted);
		border-left: 3px solid var(--border);
		border-radius: 0 4px 4px 0;
		font-family: 'SF Mono', Monaco, monospace;
		font-size: 0.78rem;
		line-height: 1.5;
		color: var(--text-muted);
		white-space: pre-wrap;
		overflow-x: auto;
		max-height: 20rem;
		overflow-y: auto;
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
		background: var(--bg-code);
		padding: 0.1rem 0.35rem;
		border-radius: 3px;
		font-family: 'SF Mono', Monaco, monospace;
		font-size: 0.82rem;
	}

	.markdown :global(pre) {
		background: var(--bg-code);
		border: 1px solid var(--border-muted);
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
		color: var(--color-link);
		text-decoration: none;
	}

	.markdown :global(a:hover) {
		text-decoration: underline;
	}

	.markdown :global(blockquote) {
		border-left: 3px solid var(--border);
		margin: 0.4rem 0;
		padding: 0.2rem 0.8rem;
		color: var(--text-muted);
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
		border-bottom: 1px solid var(--border-muted);
	}

	.markdown :global(th) {
		font-weight: 600;
		font-size: 0.8rem;
		color: var(--text-faint);
	}
</style>
