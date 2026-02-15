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

interface ChatState {
	messages: Message[];
	connected: boolean;
	chatId: string | null;
}

const initialState: ChatState = {
	messages: [],
	connected: false,
	chatId: null,
};

export const chatStore = writable<ChatState>(initialState);

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
