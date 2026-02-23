<script>
	import { onMount } from 'svelte';
	import { chatStore, chatList, appConfig, statusBar, connect, sendMessage, cancelRequest, loadChat, newChat, fetchChatList, deleteChat, setPreference } from '$lib/stores/chat.ts';
	import { currentUser, needsAuth, clearToken, setToken, getUserToken } from '$lib/stores/user.ts';
	import MessageBubble from '$lib/MessageBubble.svelte';
	import CommandPalette from '$lib/CommandPalette.svelte';
	import ModelSelector from '$lib/ModelSelector.svelte';
	import WelcomeModal from '$lib/WelcomeModal.svelte';
	import UserPicker from '$lib/UserPicker.svelte';
	import FeedbackModal from '$lib/FeedbackModal.svelte';

	let inputText = $state('');
	let messagesDiv = $state(undefined);
	let showPalette = $state(false);
	let prevMsgCount = $state(0);
	let elapsed = $state(0);
	let _timerRef = null; // plain var — must not be $state to avoid retriggering $effect
	let dark = $state(false);
	let showFeedback = $state(false);
	let showAddUser = $state(false);
	let previousUserSlug = $state(null);
	const modalMode = $derived(showAddUser ? 'new' : 'return');

	const allSuggestions = [
		{ label: 'Find all GFP plasmids', cmd: 'find all GFP plasmids' },
		{ label: 'What can you do?', cmd: '/help' },
		{ label: 'Search for ampicillin resistance', cmd: 'search ampicillin' },
		{ label: 'Show all circular vectors', cmd: 'find circular plasmids' },
		{ label: 'List features on pUC19', cmd: '/features pUC19' },
		{ label: 'BLAST a sequence', cmd: '//blast' },
		{ label: 'Find kanamycin markers', cmd: 'search kanamycin' },
		{ label: 'Compare two sequences', cmd: 'how do I compare sequences?' },
		{ label: 'Show primers on a plasmid', cmd: '/primers' },
	];
	let suggestionOffset = $state(Math.floor(Math.random() * allSuggestions.length));
	const visibleSuggestions = $derived(
		Array.from({ length: 3 }, (_, i) => allSuggestions[(suggestionOffset + i) % allSuggestions.length])
	);

	const thinkingWords = [
		'Fermenting', 'Sequencing', 'Culturing', 'Incubating', 'Lysing',
		'Centrifuging', 'Eluting', 'Amplifying', 'Ligating', 'Transforming',
		'Inoculating', 'Pelleting', 'Pipetting', 'Titrating', 'Replicating',
		'Hybridizing', 'Denaturing', 'Annealing', 'Elongating', 'Purifying',
		'Dialyzing', 'Vortexing', 'Aliquoting', 'Transfecting', 'Subcloning',
		'Lyophilizing', 'Conjugating', 'Fractionating', 'Crosslinking', 'Sonifying',
		'Miniprepping', 'Autoclaving', 'Desalting', 'Electrophoresing', 'Blotting',
		'Permeabilizing', 'Quenching', 'Staining', 'Passaging', 'Cryopreserving',
	];
	let thinkingWord = $state(thinkingWords[0]);

	function pickThinkingWord() {
		thinkingWord = thinkingWords[Math.floor(Math.random() * thinkingWords.length)];
	}

	const progressWord = $derived(thinkingWord);

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
		// Apply theme from localStorage (pre-auth), will be overridden by user prefs
		dark = localStorage.getItem('theme') === 'dark';
		if (dark) document.documentElement.setAttribute('data-theme', 'dark');
	});

	// Apply user's theme preference when currentUser changes
	$effect(() => {
		const pref = $currentUser?.preferences?.theme;
		if (pref === 'dark' || pref === 'light') {
			dark = pref === 'dark';
			if (dark) {
				document.documentElement.setAttribute('data-theme', 'dark');
			} else {
				document.documentElement.removeAttribute('data-theme');
			}
			localStorage.setItem('theme', pref);
		}
	});

	function toggleTheme() {
		dark = !dark;
		const theme = dark ? 'dark' : 'light';
		if (dark) {
			document.documentElement.setAttribute('data-theme', 'dark');
		} else {
			document.documentElement.removeAttribute('data-theme');
		}
		localStorage.setItem('theme', theme);
		setPreference('theme', theme);
	}

	function handleAddUser() {
		previousUserSlug = $currentUser?.slug || null;
		showAddUser = true;
		currentUser.set(null);
	}

	function handleCancelAddUser() {
		showAddUser = false;
		if (previousUserSlug) {
			const token = getUserToken(previousUserSlug);
			if (token) {
				setToken(token);
				connect();
				fetchChatList();
			}
		}
		previousUserSlug = null;
	}

	function formatLastUpdated(ts) {
		if (!ts) return 'never synced';
		const d = new Date(ts);
		const diffMin = Math.floor((Date.now() - d.getTime()) / 60000);
		if (diffMin < 1) return 'synced just now';
		if (diffMin < 60) return `synced ${diffMin}m ago`;
		const diffHrs = Math.floor(diffMin / 60);
		if (diffHrs < 24) return `synced ${diffHrs}h ago`;
		return `synced ${d.toLocaleDateString()}`;
	}

	function handleSubmit() {
		if (!inputText.trim() || $chatStore.isWaiting) return;
		const text = inputText.trim();
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
		suggestionOffset = (suggestionOffset + 3) % allSuggestions.length;
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

{#if $needsAuth}
	<WelcomeModal mode={modalMode} onCancel={showAddUser ? handleCancelAddUser : undefined} />
{:else}
<div class="chat-layout">
	<aside class="sidebar">
		<div class="sidebar-header">
			<img src="/logo.svg" alt="Hive Browser" class="logo" />
			<h2>Hive Browser</h2>
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
		<div class="sidebar-footer">
			<UserPicker onAddUser={handleAddUser} />
			<button class="theme-btn" onclick={toggleTheme} aria-label="Toggle theme">
				{#if dark}
					<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="5"/><path d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42"/></svg>
				{:else}
					<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12.79A9 9 0 1111.21 3 7 7 0 0021 12.79z"/></svg>
				{/if}
			</button>
		</div>
	</aside>

	<div class="chat-main">
		<div class="messages" bind:this={messagesDiv}>
			{#if $chatStore.messages.length === 0}
				<div class="welcome">
					<img src="/logo.svg" alt="Hive Browser" class="welcome-logo" />
					<h2>Hive Browser</h2>
					<p>Search your lab sequences using natural language.</p>
					<div class="suggestions">
						{#each visibleSuggestions as s}
							<button onclick={() => { inputText = s.cmd; handleSubmit(); }}>
								{s.label}
							</button>
						{/each}
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
					<span class="status-items">
						<span class="status-group">
							<span class="indicator" class:ok={$statusBar.db_connected} class:err={!$statusBar.db_connected}>DB</span>
						</span>
						<span class="status-sep"></span>
						<span class="status-group">
							<span>{$statusBar.indexed_files} files</span>
							<span class="status-dot">&middot;</span>
							<span>{$statusBar.sequences} sequences</span>
							<span class="status-dot">&middot;</span>
							<span>{$statusBar.features} features</span>
						</span>
						<span class="status-sep"></span>
						<span class="status-group">
							<span>{formatLastUpdated($statusBar.last_updated)}</span>
						</span>
						<span class="status-sep"></span>
						<ModelSelector />
						<span class="status-sep"></span>
						<button class="feedback-btn" onclick={() => showFeedback = true} aria-label="Send feedback">Feedback</button>
					</span>
					<span>/ opens command palette</span>
				</div>
			</form>
		</div>
	</div>
</div>
{#if showFeedback}
	<FeedbackModal onClose={() => showFeedback = false} />
{/if}
{/if}

<style>
	.chat-layout {
		display: flex;
		width: 100%;
		height: 100%;
	}

	.sidebar {
		width: 240px;
		background: var(--bg-sidebar);
		border-right: 1px solid var(--border);
		display: flex;
		flex-direction: column;
		flex-shrink: 0;
	}

	.sidebar-header {
		padding: 1rem;
		border-bottom: 1px solid var(--border);
		display: flex;
		align-items: center;
		justify-content: center;
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

	.theme-btn {
		background: none;
		border: none;
		cursor: pointer;
		color: var(--text-faint);
		padding: 0.2rem;
		border-radius: 4px;
		display: flex;
		align-items: center;
	}

	.theme-btn:hover {
		color: var(--text);
		background: var(--bg-hover);
	}

	.sidebar-actions {
		padding: 0.5rem 0.75rem;
	}

	.new-chat-btn {
		width: 100%;
		padding: 0.45rem;
		border: 1px solid var(--border);
		background: var(--bg-surface);
		border-radius: 6px;
		cursor: pointer;
		font-size: 0.82rem;
		color: var(--text-secondary);
		transition: background 0.15s;
	}

	.new-chat-btn:hover {
		background: var(--bg-hover);
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
		color: var(--text-faint);
		letter-spacing: 0.05em;
	}

	.placeholder {
		font-size: 0.85rem;
		color: var(--text-placeholder);
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
		background: var(--bg-hover);
	}

	.chat-item.active {
		background: var(--bg-active);
		border-left: 2px solid var(--color-accent);
		padding-left: calc(0.5rem - 2px);
	}

	.chat-info {
		flex: 1;
		min-width: 0;
		display: flex;
		flex-direction: column;
	}

	.chat-title {
		font-size: 0.82rem;
		color: var(--text);
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}

	.chat-meta {
		font-size: 0.68rem;
		color: var(--text-placeholder);
	}

	.delete-btn {
		display: none;
		border: none;
		background: transparent;
		color: var(--text-placeholder);
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
		color: var(--color-err);
		background: rgba(220, 38, 38, 0.1);
	}

	.sidebar-footer {
		padding: 0.75rem 1rem;
		display: flex;
		align-items: center;
		justify-content: space-between;
	}

	.theme-btn {
		background: none;
		border: none;
		cursor: pointer;
		color: var(--text-faint);
		padding: 0.3rem;
		border-radius: 4px;
		display: flex;
		align-items: center;
	}

	.theme-btn:hover {
		color: var(--text);
		background: var(--bg-hover);
	}

	.chat-main {
		flex: 1;
		display: flex;
		flex-direction: column;
		min-width: 0;
		background: var(--bg-app);
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
		color: var(--text-muted);
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
		color: var(--text);
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
		border: 1px solid var(--border);
		background: var(--bg-surface);
		border-radius: 20px;
		cursor: pointer;
		font-size: 0.85rem;
		color: var(--text-secondary);
		transition: all 0.15s;
	}

	.suggestions button:hover {
		border-color: var(--text-faint);
		color: var(--text);
	}

	.input-area {
		padding: 0 2rem 1rem;
		background: var(--bg-app);
	}

	.input-bar {
		background: var(--bg-surface);
		border: 1px solid var(--border);
		border-radius: 16px;
		padding: 0.75rem;
		box-shadow: 0 2px 12px var(--shadow);
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
		color: var(--text);
	}

	textarea::placeholder {
		color: var(--text-placeholder);
	}

	.send-btn {
		width: 32px;
		height: 32px;
		border: none;
		background: var(--btn-bg);
		color: var(--btn-fg);
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
		background: var(--color-err);
		color: white;
	}

	.input-hint {
		display: flex;
		justify-content: space-between;
		margin-top: 0.5rem;
		font-size: 0.7rem;
		color: var(--text-hint);
		padding: 0 0.25rem;
	}

	.status-items {
		display: flex;
		gap: 0.5rem;
		align-items: center;
	}

	.status-group {
		display: flex;
		gap: 0.3rem;
		align-items: center;
	}

	.status-sep {
		width: 1px;
		height: 0.7rem;
		background: var(--border-muted);
	}

	.status-dot {
		color: var(--text-placeholder);
	}

	.indicator {
		font-weight: 600;
	}

	.indicator.ok {
		color: var(--color-ok);
	}

	.indicator.err {
		color: var(--color-err);
	}

	.feedback-btn {
		background: none;
		border: none;
		cursor: pointer;
		color: var(--text-hint);
		font-size: 0.7rem;
		padding: 0;
		font-family: inherit;
	}

	.feedback-btn:hover {
		color: var(--color-accent);
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
			var(--color-accent) 0%,
			var(--color-accent-light) 15%,
			var(--text-muted) 30%,
			var(--text-muted) 100%
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
		color: var(--text-placeholder);
		font-size: 0.75rem;
		font-variant-numeric: tabular-nums;
	}
</style>
