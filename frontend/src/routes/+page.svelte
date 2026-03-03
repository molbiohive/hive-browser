<script>
	import Chat from '$lib/Chat.svelte';
</script>

<main>
	<Chat />
</main>

<style>
	:global(:root) {
		--bg-app: #fafafa;
		--bg-sidebar: #f0f0f0;
		--bg-surface: white;
		--bg-muted: #f8f8f8;
		--bg-hover: #e8e8e8;
		--bg-active: #ddd;
		--bg-code: #f5f5f5;

		--border: #D7D0CE;
		--border-muted: #e0ddd9;

		--text: #2F2035;
		--text-secondary: #5E4666;
		--text-muted: #97779E;
		--text-faint: #b09db5;
		--text-placeholder: #c4b8c8;
		--text-hint: #D7D0CE;

		--btn-bg: #5E4666;
		--btn-fg: white;
		--btn-hover: #9D78CE;

		--color-ok: #CB9D57;
		--color-err: #dc2626;
		--color-link: #5E4666;
		--color-accent: #9D78CE;
		--color-accent-light: #D1BBF8;
		--color-warn: #704A2F;

		--shadow: rgba(47, 32, 53, 0.08);
	}

	:global([data-theme="dark"]) {
		--bg-app: #0f0f0f;
		--bg-sidebar: #171717;
		--bg-surface: #1c1c1c;
		--bg-muted: #222;
		--bg-hover: #2a2a2a;
		--bg-active: #333;
		--bg-code: #252525;

		--border: #3B3039;
		--border-muted: #261F26;

		--text: #F8E4C5;
		--text-secondary: #c4a88a;
		--text-muted: #6E5750;
		--text-faint: #554a46;
		--text-placeholder: #4a3f3b;
		--text-hint: #3B3039;

		--btn-bg: #B8500D;
		--btn-fg: #F8E4C5;
		--btn-hover: #E9A14C;

		--color-ok: #E9A14C;
		--color-err: #f87171;
		--color-link: #E9A14C;
		--color-accent: #B8500D;
		--color-accent-light: #E9A14C;
		--color-warn: #66270A;

		--shadow: rgba(23, 18, 23, 0.4);
	}

	:global(html), :global(body) {
		margin: 0;
		padding: 0;
		height: 100%;
		overflow: hidden;
	}

	main {
		height: 100vh;
		overflow: hidden;
		display: flex;
		font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
		background: var(--bg-app);
		color: var(--text);
	}
</style>
