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
		summary?: string;
		data?: unknown;
	};
	ts: string;
}

interface ChatMeta {
	id: string;
	title: string | null;
	created: string;
	message_count: number;
}

interface ChatState {
	messages: Message[];
	connected: boolean;
	chatId: string | null;
	chatTitle: string | null;
}

const initialState: ChatState = {
	messages: [],
	connected: false,
	chatId: null,
	chatTitle: null,
};

export const chatStore = writable<ChatState>(initialState);
export const chatList = writable<ChatMeta[]>([]);

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
		chatStore.update(s => ({ ...s, connected: false }));
		reconnectTimer = setTimeout(connect, 3000);
	};

	ws.onerror = (e) => {
		console.error('[ws] error:', e);
	};

	ws.onmessage = (event) => {
		const data = JSON.parse(event.data);
		console.log('[ws] received:', data);

		if (data.type === 'message') {
			const msg: Message = {
				role: 'assistant',
				content: data.content,
				widget: data.widget,
				ts: new Date().toISOString(),
			};
			chatStore.update(s => ({
				...s,
				messages: [...s.messages, msg],
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

	ws.send(JSON.stringify({ type: 'message', content }));
}

export function loadChat(chatId: string) {
	if (!ws || ws.readyState !== WebSocket.OPEN) return;
	ws.send(JSON.stringify({ type: 'load_chat', chatId }));
}

export function newChat() {
	chatStore.set({ ...initialState, connected: true });
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
