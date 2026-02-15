<script>
	import { onMount } from 'svelte';
	import { chatStore, chatList, connect, sendMessage, loadChat, newChat, fetchChatList, deleteChat } from '$lib/stores/chat.ts';
	import MessageBubble from '$lib/MessageBubble.svelte';
	import CommandPalette from '$lib/CommandPalette.svelte';

	let inputText = $state('');
	let messagesDiv;
	let showPalette = $state(false);

	onMount(() => {
		connect();
		fetchChatList();
	});

	function handleSubmit() {
		if (!inputText.trim()) return;
		sendMessage(inputText.trim());
		inputText = '';
		showPalette = false;
	}

	function handleKeydown(e) {
		if (e.key === 'Enter' && !e.shiftKey) {
			e.preventDefault();
			handleSubmit();
		}
		if (e.key === 'Escape') {
			showPalette = false;
		}
	}

	function handleInput(e) {
		const val = e.target.value;
		if (val === '/') {
			showPalette = true;
		} else if (!val.startsWith('/')) {
			showPalette = false;
		}
	}

	function handlePaletteSelect(cmdName) {
		inputText = `/${cmdName} `;
		showPalette = false;
	}

	function handleLoadChat(chatId) {
		loadChat(chatId);
	}

	function handleNewChat() {
		newChat();
	}

	function handleDeleteChat(e, chatId) {
		e.stopPropagation();
		deleteChat(chatId);
	}

	$effect(() => {
		const msgs = $chatStore.messages;
		if (messagesDiv) {
			messagesDiv.scrollTop = messagesDiv.scrollHeight;
		}
	});
</script>

<div class="chat-layout">
	<aside class="sidebar">
		<div class="sidebar-header">
			<img src="/logo.svg" alt="Zerg Browser" class="logo" />
			<h2>Zerg Browser</h2>
		</div>
		<div class="sidebar-actions">
			<button class="new-chat-btn" onclick={handleNewChat}>+ New Chat</button>
		</div>
		<div class="sidebar-section">
			<h3>Chat History</h3>
			{#if $chatList.length === 0}
				<div class="placeholder">No previous chats</div>
			{:else}
				<div class="chat-list">
					{#each $chatList as chat}
						<div
							class="chat-item"
							class:active={$chatStore.chatId === chat.id}
							onclick={() => handleLoadChat(chat.id)}
							role="button"
							tabindex="0"
						>
							<span class="chat-title">{chat.title || 'Untitled'}</span>
							<button
								class="delete-btn"
								onclick={(e) => handleDeleteChat(e, chat.id)}
								aria-label="Delete chat"
							>&times;</button>
						</div>
					{/each}
				</div>
			{/if}
		</div>
	</aside>

	<div class="chat-main">
		<div class="messages" bind:this={messagesDiv}>
			{#if $chatStore.messages.length === 0}
				<div class="welcome">
					<img src="/logo.svg" alt="Zerg Browser" class="welcome-logo" />
					<h2>Zerg Browser</h2>
					<p>Search your lab sequences using natural language.</p>
					<div class="suggestions">
						<button onclick={() => { inputText = 'find all GFP plasmids'; handleSubmit(); }}>
							Find all GFP plasmids
						</button>
						<button onclick={() => { inputText = '/status'; handleSubmit(); }}>
							Show system status
						</button>
						<button onclick={() => { inputText = '/help'; handleSubmit(); }}>
							What can you do?
						</button>
					</div>
				</div>
			{:else}
				{#each $chatStore.messages as message}
					<MessageBubble {message} />
				{/each}
			{/if}
		</div>

		<div class="input-area">
			<form class="input-bar" onsubmit={(e) => { e.preventDefault(); handleSubmit(); }}>
				<div class="input-wrapper">
					<CommandPalette visible={showPalette} onSelect={handlePaletteSelect} />
					<textarea
						bind:value={inputText}
						onkeydown={handleKeydown}
						oninput={handleInput}
						placeholder="Type message or /command..."
						rows="2"
					></textarea>
					<button type="submit" class="send-btn" disabled={!inputText.trim()} aria-label="Send message">
						<svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
							<path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z"/>
						</svg>
					</button>
				</div>
				<div class="input-hint">
					<span class="status" class:disconnected={!$chatStore.connected}>
						{$chatStore.connected ? 'Connected' : 'Disconnected'}
					</span>
					<span>/ opens command palette</span>
				</div>
			</form>
		</div>
	</div>
</div>

<style>
	.chat-layout {
		display: flex;
		width: 100%;
		height: 100%;
	}

	.sidebar {
		width: 240px;
		background: #f0f0f0;
		border-right: 1px solid #ddd;
		display: flex;
		flex-direction: column;
		flex-shrink: 0;
	}

	.sidebar-header {
		padding: 1rem;
		border-bottom: 1px solid #ddd;
		display: flex;
		align-items: center;
		gap: 0.6rem;
	}

	.sidebar-header h2 {
		margin: 0;
		font-size: 1rem;
		font-weight: 700;
	}

	.logo {
		width: 28px;
		height: 28px;
	}

	.sidebar-actions {
		padding: 0.5rem 0.75rem;
	}

	.new-chat-btn {
		width: 100%;
		padding: 0.45rem;
		border: 1px solid #ccc;
		background: white;
		border-radius: 6px;
		cursor: pointer;
		font-size: 0.82rem;
		color: #555;
		transition: background 0.15s;
	}

	.new-chat-btn:hover {
		background: #e8e8e8;
	}

	.sidebar-section {
		padding: 0.5rem 0.75rem;
		flex: 1;
		overflow-y: auto;
	}

	.sidebar-section h3 {
		margin: 0 0 0.5rem;
		font-size: 0.75rem;
		text-transform: uppercase;
		color: #888;
		letter-spacing: 0.05em;
	}

	.placeholder {
		font-size: 0.85rem;
		color: #aaa;
	}

	.chat-list {
		display: flex;
		flex-direction: column;
		gap: 2px;
	}

	.chat-item {
		width: 100%;
		text-align: left;
		padding: 0.45rem 0.5rem;
		border: none;
		background: transparent;
		border-radius: 4px;
		cursor: pointer;
		display: flex;
		justify-content: space-between;
		align-items: center;
		gap: 0.5rem;
		transition: background 0.15s;
	}

	.chat-item:hover {
		background: #e4e4e4;
	}

	.chat-item.active {
		background: #ddd;
	}

	.chat-title {
		font-size: 0.82rem;
		color: #333;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
		flex: 1;
	}

	.delete-btn {
		display: none;
		border: none;
		background: transparent;
		color: #aaa;
		cursor: pointer;
		font-size: 1rem;
		line-height: 1;
		padding: 0 0.2rem;
		border-radius: 3px;
		flex-shrink: 0;
	}

	.chat-item:hover .delete-btn {
		display: block;
	}

	.delete-btn:hover {
		color: #dc2626;
		background: rgba(220, 38, 38, 0.1);
	}

	.chat-main {
		flex: 1;
		display: flex;
		flex-direction: column;
		min-width: 0;
		background: #fafafa;
	}

	.messages {
		flex: 1;
		overflow-y: auto;
		padding: 1.5rem 2rem 1rem;
	}

	.welcome {
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		height: 100%;
		text-align: center;
		color: #666;
	}

	.welcome-logo {
		width: 96px;
		height: 96px;
		margin-bottom: 1rem;
		opacity: 0.7;
	}

	.welcome h2 {
		margin: 0 0 0.5rem;
		font-size: 1.5rem;
		color: #333;
	}

	.welcome p {
		margin: 0 0 1.5rem;
		font-size: 0.95rem;
	}

	.suggestions {
		display: flex;
		gap: 0.5rem;
		flex-wrap: wrap;
		justify-content: center;
	}

	.suggestions button {
		padding: 0.5rem 1rem;
		border: 1px solid #ddd;
		background: white;
		border-radius: 20px;
		cursor: pointer;
		font-size: 0.85rem;
		color: #555;
		transition: all 0.15s;
	}

	.suggestions button:hover {
		border-color: #999;
		color: #333;
	}

	.input-area {
		padding: 0 2rem 1rem;
		background: #fafafa;
	}

	.input-bar {
		background: white;
		border: 1px solid #ddd;
		border-radius: 16px;
		padding: 0.75rem;
		box-shadow: 0 2px 12px rgba(0, 0, 0, 0.06);
	}

	.input-wrapper {
		display: flex;
		align-items: flex-end;
		gap: 0.5rem;
		position: relative;
	}

	textarea {
		flex: 1;
		resize: none;
		border: none;
		background: transparent;
		font-family: inherit;
		font-size: 0.9rem;
		line-height: 1.5;
		padding: 0.25rem 0;
		outline: none;
		min-height: 2.5rem;
	}

	.send-btn {
		width: 32px;
		height: 32px;
		border: none;
		background: #333;
		color: white;
		border-radius: 8px;
		cursor: pointer;
		display: flex;
		align-items: center;
		justify-content: center;
		flex-shrink: 0;
		transition: opacity 0.15s;
	}

	.send-btn:disabled {
		opacity: 0.3;
		cursor: default;
	}

	.input-hint {
		display: flex;
		justify-content: space-between;
		margin-top: 0.5rem;
		font-size: 0.7rem;
		color: #bbb;
		padding: 0 0.25rem;
	}

	.status {
		color: #6b6;
	}

	.disconnected {
		color: #c66;
	}
</style>
