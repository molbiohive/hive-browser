<script>
	import { onMount } from 'svelte';
	import { chatStore, chatList, appConfig, statusBar, connect, sendMessage, cancelRequest, toggleStatusBar, loadChat, newChat, fetchChatList, deleteChat } from '$lib/stores/chat.ts';
	import MessageBubble from '$lib/MessageBubble.svelte';
	import CommandPalette from '$lib/CommandPalette.svelte';

	let inputText = $state('');
	let messagesDiv;
	let showPalette = $state(false);
	let prevMsgCount = $state(0);
	let elapsed = $state(0);
	let _timerRef = null; // plain var — must not be $state to avoid retriggering $effect

	const thinkingWords = ['Spawning', 'Hatching', 'Evolving', 'Multiplying', 'Spreading'];
	const toolWords = {
		search: 'Scouring',
		extract: 'Extracting',
		blast: 'Launching',
		digest: 'Devouring',
		translate: 'Mutating',
		features: 'Scanning',
		primers: 'Detecting',
		gc: 'Analyzing',
		revcomp: 'Inverting',
		transcribe: 'Transcribing',
		profile: 'Profiling',
	};
	let thinkingWord = $state(thinkingWords[0]);

	function pickThinkingWord() {
		thinkingWord = thinkingWords[Math.floor(Math.random() * thinkingWords.length)];
	}

	const progressWord = $derived.by(() => {
		const p = $chatStore.progress;
		if (!p) return thinkingWord;
		if (p.phase === 'tool' && p.tool) return toolWords[p.tool] || 'Consuming';
		return thinkingWord;
	});

	const progressMeta = $derived.by(() => {
		const p = $chatStore.progress;
		const parts = [];
		if (p && p.tools_used > 0) parts.push(`${p.tools_used} tool${p.tools_used > 1 ? 's' : ''}`);
		if (p && (p.tokens.in > 0 || p.tokens.out > 0)) parts.push(`${p.tokens.in}\u2192${p.tokens.out} tok`);
		parts.push(`${elapsed.toFixed(1)}s`);
		return parts.join(' \u00b7 ');
	});

	$effect(() => {
		if ($chatStore.isWaiting) {
			if (!_timerRef) {
				elapsed = 0;
				pickThinkingWord();
				_timerRef = setInterval(() => { elapsed += 0.1; }, 100);
			}
		} else {
			if (_timerRef) { clearInterval(_timerRef); _timerRef = null; }
		}
	});

	onMount(() => {
		connect();
		fetchChatList();
	});

	function handleSubmit() {
		if (!inputText.trim() || $chatStore.isWaiting) return;
		const text = inputText.trim();
		if (text === '/status') {
			toggleStatusBar();
			inputText = '';
			showPalette = false;
			return;
		}
		sendMessage(text);
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

	let paletteFilter = $state('');

	function handleInput(e) {
		const val = e.target.value;
		if (val.startsWith('//')) {
			showPalette = true;
			paletteFilter = val.slice(2).split(' ')[0];
		} else if (val.startsWith('/')) {
			showPalette = true;
			paletteFilter = val.slice(1).split(' ')[0];
		} else {
			showPalette = false;
			paletteFilter = '';
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

	function timeAgo(iso) {
		const d = new Date(iso);
		const diff = Date.now() - d.getTime();
		const mins = Math.floor(diff / 60000);
		if (mins < 1) return 'just now';
		if (mins < 60) return `${mins}m ago`;
		const hrs = Math.floor(mins / 60);
		if (hrs < 24) return `${hrs}h ago`;
		const days = Math.floor(hrs / 24);
		if (days < 7) return `${days}d ago`;
		const y = d.getFullYear();
		const m = String(d.getMonth() + 1).padStart(2, '0');
		const dd = String(d.getDate()).padStart(2, '0');
		return `${y}.${m}.${dd}`;
	}

	$effect(() => {
		const count = $chatStore.messages.length;
		if (count > prevMsgCount && messagesDiv) {
			messagesDiv.scrollTop = messagesDiv.scrollHeight;
		}
		prevMsgCount = count;
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
							onkeydown={(e) => { if (e.key === "Enter") handleLoadChat(chat.id); }}
							role="button"
							tabindex="0"
						>
							<div class="chat-info">
								<span class="chat-title">{chat.title || 'Untitled'}</span>
								<span class="chat-meta">{timeAgo(chat.created)} · {chat.message_count} msg</span>
							</div>
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
						<button onclick={() => { inputText = '//status'; handleSubmit(); }}>
							Show system status
						</button>
						<button onclick={() => { inputText = '/help'; handleSubmit(); }}>
							What can you do?
						</button>
					</div>
				</div>
			{:else}
				{#each $chatStore.messages as message, i}
					{@const contextStart = Math.max(0, $chatStore.messages.length - $appConfig.max_history_pairs * 2)}
					<MessageBubble {message} faded={i < contextStart} messageIndex={i} />
				{/each}
				{#if $chatStore.isWaiting && $chatStore.messages.at(-1)?.widget?.type !== 'form'}
					<div class="progress-indicator">
						<span class="progress-word">{progressWord}...</span>
						<span class="progress-meta">{progressMeta}</span>
					</div>
				{/if}
			{/if}
		</div>

		<div class="input-area">
			<form class="input-bar" onsubmit={(e) => { e.preventDefault(); handleSubmit(); }}>
				<div class="input-wrapper">
					<CommandPalette visible={showPalette} filter={paletteFilter} onSelect={handlePaletteSelect} />
					<textarea
						bind:value={inputText}
						onkeydown={handleKeydown}
						oninput={handleInput}
						placeholder="Type message or /command..."
						rows="2"
					></textarea>
					{#if $chatStore.isWaiting}
					<button type="button" class="send-btn cancel" onclick={cancelRequest} aria-label="Cancel request">
						<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
							<path d="M18 6L6 18M6 6l12 12"/>
						</svg>
					</button>
					{:else}
					<button type="submit" class="send-btn" disabled={!inputText.trim()} aria-label="Send message">
						<svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
							<path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z"/>
						</svg>
					</button>
					{/if}
				</div>
				<div class="input-hint">
					{#if $statusBar.visible}
						<span class="status-items">
							<span class="indicator" class:ok={$statusBar.db_connected} class:err={!$statusBar.db_connected}>DB</span>
							<span>{$statusBar.indexed_files} files</span>
							<span>{$statusBar.sequences} seq</span>
							<span class="indicator" class:ok={$statusBar.llm_available} class:err={!$statusBar.llm_available}>LLM</span>
						</span>
					{/if}
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
		display: block;
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

	.chat-info {
		flex: 1;
		min-width: 0;
		display: flex;
		flex-direction: column;
	}

	.chat-title {
		font-size: 0.82rem;
		color: #333;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}

	.chat-meta {
		font-size: 0.68rem;
		color: #aaa;
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

	.send-btn.cancel {
		background: #dc2626;
	}

	.input-hint {
		display: flex;
		justify-content: space-between;
		margin-top: 0.5rem;
		font-size: 0.7rem;
		color: #bbb;
		padding: 0 0.25rem;
	}

	.status-items {
		display: flex;
		gap: 0.6rem;
		align-items: center;
	}

	.indicator {
		font-weight: 600;
	}

	.indicator.ok {
		color: #6b6;
	}

	.indicator.err {
		color: #c66;
	}

	.progress-indicator {
		display: flex;
		align-items: baseline;
		gap: 0.5rem;
		padding: 0.6rem 1rem;
		margin: 0.5rem 0;
		font-size: 0.85rem;
	}

	.progress-word {
		font-weight: 600;
		background: linear-gradient(
			90deg,
			#8b5cf6 0%,
			#a78bfa 15%,
			#666 30%,
			#666 100%
		);
		background-size: 300% 100%;
		background-clip: text;
		-webkit-background-clip: text;
		-webkit-text-fill-color: transparent;
		animation: violet-sweep 1.5s ease-in-out infinite;
	}

	@keyframes violet-sweep {
		0% { background-position: 100% 0; }
		100% { background-position: -100% 0; }
	}

	.progress-meta {
		color: #aaa;
		font-size: 0.75rem;
		font-variant-numeric: tabular-nums;
	}
</style>
