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

		/* Hatchlings light theme -- bg matches widget surface */
		--hatch-bg: var(--bg-surface);
		--hatch-plot-bg: var(--bg-surface);
		--hatch-text: #2a2e34;
		--hatch-text-muted: #6a7080;
		--hatch-text-dim: #9aa0ac;
		--hatch-border: #d8d6d2;
		--hatch-grid-color: #e8e6e2;
		--hatch-highlight: #3a8ab0;
		--hatch-axis-color: #c8ccd4;
		--hatch-axis-text: #6a7080;
		--hatch-axis-label: #5a6070;
		--hatch-ring-color: #8a9098;
		--hatch-tick-major: #7a8088;
		--hatch-tick-minor: #b8bcc4;
		--hatch-cut-site: #c04040;
		--hatch-positive: #3a8a4a;
		--hatch-negative: #c04040;
		--hatch-warning: #b87a28;
		--hatch-controls-bg: #e8e6e2;
		--hatch-controls-border: #c8ccd4;
		--hatch-controls-color: #2a2e34;
		--hatch-controls-hover: #d8d6d2;
		--hatch-legend-color: #5a6070;
		--hatch-title-color: #2a2e34;
		--hatch-seq-bg: #f5f3f0;
		--hatch-seq-border: #d8d6d2;
		--hatch-ruler-color: #8a9098;
		--hatch-ruler-text: #6a7080;
		--hatch-line-number: #9aa0ac;
		--hatch-cutsite-color: #c04040;
		--hatch-cutsite-text: #c04040;
		--hatch-selection-fill: rgba(59, 130, 246, 0.12);
		--hatch-selection-stroke: rgba(59, 130, 246, 0.5);
		--hatch-selection-handle: rgba(59, 130, 246, 0.8);
		--hatch-selection-outline: #000000;
		--hatch-caret-color: #000000;
		--hatch-primer-color: #1a8fa8;
		--hatch-primer-text: #1a8fa8;
		--hatch-annotation-text: #ffffff;
		--hatch-annotation-stroke: #000000;
		--hatch-annotation-stroke-hover: #000000;
		--hatch-tooltip-bg: #fafaf8;
		--hatch-tooltip-border: #d8d6d2;
		--hatch-tooltip-text: #2a2e34;
		--hatch-tooltip-label: #6a7080;
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

		/* Hatchlings dark theme -- bg matches widget surface */
		--hatch-bg: var(--bg-surface);
		--hatch-plot-bg: var(--bg-surface);
		--hatch-text: #d4dce6;
		--hatch-text-muted: #8a95a5;
		--hatch-text-dim: #566070;
		--hatch-border: #2a3848;
		--hatch-grid-color: #1e2a38;
		--hatch-highlight: #6ab8e0;
		--hatch-axis-color: #3a4858;
		--hatch-axis-text: #7a8898;
		--hatch-axis-label: #95a3b3;
		--hatch-ring-color: #4a5a6a;
		--hatch-tick-major: #5a6a7a;
		--hatch-tick-minor: #3a4858;
		--hatch-cut-site: #d45858;
		--hatch-positive: #58b56a;
		--hatch-negative: #d45858;
		--hatch-warning: #d9953a;
		--hatch-controls-bg: #1e2a38;
		--hatch-controls-border: #3a4858;
		--hatch-controls-color: #d4dce6;
		--hatch-controls-hover: #2a3848;
		--hatch-legend-color: #95a3b3;
		--hatch-title-color: #d4dce6;
		--hatch-seq-bg: #0c1018;
		--hatch-seq-border: #2a3848;
		--hatch-ruler-color: #4a5a6a;
		--hatch-ruler-text: #7a8898;
		--hatch-line-number: #566070;
		--hatch-cutsite-color: #d45858;
		--hatch-cutsite-text: #d45858;
		--hatch-selection-fill: rgba(59, 130, 246, 0.15);
		--hatch-selection-stroke: rgba(59, 130, 246, 0.6);
		--hatch-selection-handle: rgba(59, 130, 246, 0.8);
		--hatch-selection-outline: #ffffff;
		--hatch-caret-color: #ffffff;
		--hatch-primer-color: #22d3ee;
		--hatch-primer-text: #22d3ee;
		--hatch-annotation-text: #ffffff;
		--hatch-annotation-stroke: #ffffff;
		--hatch-annotation-stroke-hover: #ffffff;
		--hatch-tooltip-bg: #141c26;
		--hatch-tooltip-border: #2a3848;
		--hatch-tooltip-text: #d4dce6;
		--hatch-tooltip-label: #8a95a5;
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
