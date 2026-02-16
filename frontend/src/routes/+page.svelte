<script>
	import Chat from '$lib/Chat.svelte';
</script>

<main>
	<Chat />
</main>

<style>
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
		background: #fafafa;
	}
</style>
