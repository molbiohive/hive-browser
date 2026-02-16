/**
 * Chat store — manages WebSocket connection, messages, and chat state.
 */

import { writable } from 'svelte/store';

interface Message {
	role: 'user' | 'assistant';
	content: string;
	widget?: {
		type: string;
		tool: string;
		params: Record<string, unknown>;
		data?: unknown;
		stale?: boolean;
	};
	ts: string;
}

interface ChatMeta {
	id: string;
	title: string | null;
	created: string;
	message_count: number;
}

interface AppConfig {
	search_columns: string[];
	max_history_pairs: number;
}

interface ToolMeta {
	name: string;
	description: string;
	widget_type: string;
	use_llm: boolean;
}

interface ChatState {
	messages: Message[];
	connected: boolean;
	isWaiting: boolean;
	chatId: string | null;
	chatTitle: string | null;
}

const initialState: ChatState = {
	messages: [],
	connected: false,
	isWaiting: false,
	chatId: null,
	chatTitle: null,
};

const defaultConfig: AppConfig = {
	search_columns: ['name', 'size_bp', 'topology', 'features'],
	max_history_pairs: 20,
};

interface StatusBar {
	indexed_files: number;
	sequences: number;
	db_connected: boolean;
	llm_available: boolean;
	visible: boolean;
}

export const chatStore = writable<ChatState>(initialState);
export const chatList = writable<ChatMeta[]>([]);
export const appConfig = writable<AppConfig>(defaultConfig);
export const toolList = writable<ToolMeta[]>([]);
export const statusBar = writable<StatusBar>({
	indexed_files: 0,
	sequences: 0,
	db_connected: false,
	llm_available: false,
	visible: true,
});

let ws: WebSocket | null = null;
let reconnectTimer: ReturnType<typeof setTimeout> | null = null;

export function connect() {
	if (reconnectTimer) {
		clearTimeout(reconnectTimer);
		reconnectTimer = null;
	}

	const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
	ws = new WebSocket(`${protocol}//${location.host}/ws`);

	ws.onopen = () => {
		console.log('[ws] connected');
		chatStore.update(s => ({ ...s, connected: true }));
	};

	ws.onclose = () => {
		console.log('[ws] disconnected, reconnecting in 3s...');
		chatStore.update(s => ({ ...s, connected: false, isWaiting: false }));
		reconnectTimer = setTimeout(connect, 3000);
	};

	ws.onerror = (e) => {
		console.error('[ws] error:', e);
	};

	ws.onmessage = (event) => {
		const data = JSON.parse(event.data);
		console.log('[ws] received:', data);

		if (data.type === 'init') {
			appConfig.set(data.config);
			if (data.tools) {
				toolList.set(data.tools);
			}
			if (data.status) {
				statusBar.update(s => ({ ...s, ...data.status }));
			}
		} else if (data.type === 'status_update') {
			if (data.status) {
				statusBar.update(s => ({ ...s, ...data.status }));
			}
		} else if (data.type === 'message') {
			const msg: Message = {
				role: 'assistant',
				content: data.content,
				widget: data.widget,
				ts: new Date().toISOString(),
			};
			chatStore.update(s => ({
				...s,
				messages: [...s.messages, msg],
				isWaiting: false,
			}));
		} else if (data.type === 'chat_saved') {
			chatStore.update(s => ({
				...s,
				chatId: data.chatId,
				chatTitle: data.title,
			}));
			fetchChatList();
		} else if (data.type === 'chat_loaded') {
			chatStore.update(s => ({
				...s,
				chatId: data.chatId,
				chatTitle: data.title,
				messages: data.messages || [],
			}));
		} else if (data.type === 'widget_data') {
			chatStore.update(s => {
				const messages = [...s.messages];
				const idx = data.messageIndex;
				if (idx != null && messages[idx]?.widget) {
					messages[idx] = {
						...messages[idx],
						widget: {
							...messages[idx].widget!,
							data: data.data,
							stale: undefined,
						},
					};
				}
				return { ...s, messages };
			});
		}
	};
}

export function sendMessage(content: string) {
	const msg: Message = {
		role: 'user',
		content,
		ts: new Date().toISOString(),
	};

	chatStore.update(s => ({
		...s,
		messages: [...s.messages, msg],
	}));

	if (!ws || ws.readyState !== WebSocket.OPEN) {
		console.warn('[ws] not connected, message queued locally only');
		return;
	}

	chatStore.update(s => ({ ...s, isWaiting: true }));
	ws.send(JSON.stringify({ type: 'message', content }));
}

export function toggleStatusBar() {
	statusBar.update(s => ({ ...s, visible: !s.visible }));
}

export function sendRawMessage(content: string) {
	if (!ws || ws.readyState !== WebSocket.OPEN) {
		console.warn('[ws] not connected');
		return;
	}
	ws.send(JSON.stringify({ type: 'message', content }));
}

export function rerunTool(tool: string, params: Record<string, unknown>, messageIndex: number) {
	if (!ws || ws.readyState !== WebSocket.OPEN) return;
	ws.send(JSON.stringify({ type: 'rerun_tool', tool, params, messageIndex }));
}

export function replaceFormWithCommand(messageIndex: number, commandText: string) {
	chatStore.update(s => {
		const messages = [...s.messages];
		if (messages[messageIndex]) {
			messages[messageIndex] = {
				role: 'user',
				content: commandText,
				ts: new Date().toISOString(),
			};
		}
		return { ...s, messages };
	});
}

export function loadChat(chatId: string) {
	if (!ws || ws.readyState !== WebSocket.OPEN) return;
	ws.send(JSON.stringify({ type: 'load_chat', chatId }));
}

export function newChat() {
	chatStore.set({ ...initialState, connected: true, isWaiting: false });
}

export async function fetchChatList() {
	try {
		const res = await fetch('/api/chats');
		if (res.ok) {
			const chats = await res.json();
			chatList.set(chats);
		}
	} catch (e) {
		console.warn('[chat] failed to fetch chat list:', e);
	}
}

export async function deleteChat(chatId: string) {
	try {
		await fetch(`/api/chats/${chatId}`, { method: 'DELETE' });
		chatStore.update(s => {
			if (s.chatId === chatId) {
				return { ...initialState, connected: s.connected };
			}
			return s;
		});
		await fetchChatList();
	} catch (e) {
		console.warn('[chat] failed to delete chat:', e);
	}
}
