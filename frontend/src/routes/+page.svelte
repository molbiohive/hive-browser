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

		--border: #ddd;
		--border-muted: #e0e0e0;

		--text: #333;
		--text-secondary: #555;
		--text-muted: #666;
		--text-faint: #888;
		--text-placeholder: #aaa;
		--text-hint: #bbb;

		--btn-bg: #ad68f7;
		--btn-fg: white;
		--btn-hover: #9b50f0;

		--color-ok: #16a34a;
		--color-err: #dc2626;
		--color-link: #51baea;
		--color-accent: #ad68f7;
		--color-accent-light: #c99dfa;
		--color-warn: #c4a000;

		--shadow: rgba(0, 0, 0, 0.06);
	}

	:global([data-theme="dark"]) {
		--bg-app: #0f0f0f;
		--bg-sidebar: #171717;
		--bg-surface: #1c1c1c;
		--bg-muted: #222;
		--bg-hover: #2a2a2a;
		--bg-active: #333;
		--bg-code: #252525;

		--border: #333;
		--border-muted: #2a2a2a;

		--text: #ddd;
		--text-secondary: #aaa;
		--text-muted: #888;
		--text-faint: #666;
		--text-placeholder: #555;
		--text-hint: #444;

		--btn-bg: #ad68f7;
		--btn-fg: white;
		--btn-hover: #c99dfa;

		--color-ok: #22c55e;
		--color-err: #f87171;
		--color-link: #51baea;
		--color-accent: #ad68f7;
		--color-accent-light: #c99dfa;
		--color-warn: #e2da1c;

		--shadow: rgba(0, 0, 0, 0.3);
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
