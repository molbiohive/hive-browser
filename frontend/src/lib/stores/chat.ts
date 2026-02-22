/**
 * Chat store — manages WebSocket connection, messages, and chat state.
 */

import { writable } from 'svelte/store';
import { getToken, clearToken, currentUser } from './user.ts';

interface Message {
	role: 'user' | 'assistant';
	content: string;
	widget?: {
		type: string;
		tool: string;
		params: Record<string, unknown>;
		data?: unknown;
		stale?: boolean;
		chain?: Array<{
			tool: string;
			params: Record<string, unknown>;
			summary: string;
			widget: string;
		}>;
	};
	ts: string;
	model?: string;
}

export interface ModelInfo {
	id: string;
	provider: string;
	model: string;
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
	widget: string;
	tags: string[];
}

interface Progress {
	phase: string;
	tool?: string;
	tools_used: number;
	tokens: { in: number; out: number };
}

interface ChatState {
	messages: Message[];
	connected: boolean;
	isWaiting: boolean;
	progress: Progress | null;
	chatId: string | null;
	chatTitle: string | null;
}

const initialState: ChatState = {
	messages: [],
	connected: false,
	isWaiting: false,
	progress: null,
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
	features: number;
	db_connected: boolean;
	llm_available: boolean;
	last_updated: string | null;
}

export const chatStore = writable<ChatState>(initialState);
export const chatList = writable<ChatMeta[]>([]);
export const appConfig = writable<AppConfig>(defaultConfig);
export const toolList = writable<ToolMeta[]>([]);
export const statusBar = writable<StatusBar>({
	indexed_files: 0,
	sequences: 0,
	features: 0,
	db_connected: false,
	llm_available: false,
	last_updated: null,
});
export const modelList = writable<ModelInfo[]>([]);
export const currentModel = writable<string | null>(null);

let ws: WebSocket | null = null;
let reconnectTimer: ReturnType<typeof setTimeout> | null = null;

export function connect() {
	if (reconnectTimer) {
		clearTimeout(reconnectTimer);
		reconnectTimer = null;
	}

	// Close any existing connection to prevent orphaned sockets
	if (ws) {
		ws.onclose = null;
		ws.close();
		ws = null;
	}

	const token = getToken();
	if (!token) {
		// No token — trigger auth flow
		currentUser.set(null);
		return;
	}

	const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
	ws = new WebSocket(`${protocol}//${location.host}/ws?token=${encodeURIComponent(token)}`);

	ws.onopen = () => {
		console.log('[ws] connected');
		chatStore.update(s => ({ ...s, connected: true }));
	};

	ws.onclose = (event) => {
		chatStore.update(s => ({ ...s, connected: false, isWaiting: false }));
		if (event.code === 4001) {
			// Auth failed — clear cookie + state, show welcome modal
			console.log('[ws] auth failed, clearing token');
			clearToken();
			currentUser.set(null);
			return;
		}
		console.log('[ws] disconnected, reconnecting in 3s...');
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
			if (data.models) {
				modelList.set(data.models);
			}
			if (data.currentModel) {
				currentModel.set(data.currentModel);
			}
			if (data.user) {
				currentUser.set(data.user);
			}
		} else if (data.type === 'status_update') {
			if (data.status) {
				statusBar.update(s => ({ ...s, ...data.status }));
			}
		} else if (data.type === 'progress') {
			chatStore.update(s => ({
				...s,
				progress: {
					phase: data.phase,
					tool: data.tool,
					tools_used: data.tools_used,
					tokens: data.tokens,
				},
			}));
		} else if (data.type === 'model_changed') {
			currentModel.set(data.modelId);
		} else if (data.type === 'preferences_updated') {
			currentUser.update(u => u ? { ...u, preferences: data.preferences } : u);
		} else if (data.type === 'message') {
			const msg: Message = {
				role: 'assistant',
				content: data.content,
				widget: data.widget,
				ts: new Date().toISOString(),
				model: data.model,
			};
			const isForm = data.widget?.type === 'form';
			chatStore.update(s => ({
				...s,
				messages: [...s.messages, msg],
				isWaiting: isForm,  // keep waiting during form display
				progress: null,
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
			if (data.model) {
				currentModel.set(data.model);
			}
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

export function reconnect() {
	if (ws) {
		ws.onclose = null; // prevent auto-reconnect from old socket
		ws.close();
		ws = null;
	}
	chatStore.set({ ...initialState });
	chatList.set([]);
	connect();
}

export function setPreference(key: string, value: unknown) {
	if (!ws || ws.readyState !== WebSocket.OPEN) return;
	ws.send(JSON.stringify({ type: 'set_preference', key, value }));
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

export function setModel(modelId: string) {
	if (!ws || ws.readyState !== WebSocket.OPEN) return;
	ws.send(JSON.stringify({ type: 'set_model', modelId }));
}


export function sendRawMessage(content: string) {
	if (!ws || ws.readyState !== WebSocket.OPEN) {
		console.warn('[ws] not connected');
		return;
	}
	ws.send(JSON.stringify({ type: 'message', content }));
}

export function cancelRequest() {
	// Check if there's an active form — cancel locally without WS
	let cancelled = false;
	chatStore.update(s => {
		const last = s.messages[s.messages.length - 1];
		if (last?.widget?.type === 'form') {
			const messages = [...s.messages];
			messages.pop(); // remove form
			// remove triggering user message
			if (messages.length > 0 && messages[messages.length - 1]?.role === 'user') {
				messages.pop();
			}
			cancelled = true;
			return { ...s, messages, isWaiting: false, progress: null };
		}
		return s;
	});
	if (cancelled) return;
	// Otherwise cancel the LLM request via WebSocket
	if (!ws || ws.readyState !== WebSocket.OPEN) return;
	ws.send(JSON.stringify({ type: 'cancel' }));
}

export function rerunTool(tool: string, params: Record<string, unknown>, messageIndex: number) {
	if (!ws || ws.readyState !== WebSocket.OPEN) return;
	ws.send(JSON.stringify({ type: 'rerun_tool', tool, params, messageIndex }));
}

export function submitForm(formIndex: number, commandText: string) {
	chatStore.update(s => {
		const messages = [...s.messages];
		// Update the triggering user message with the actual command
		if (formIndex > 0 && messages[formIndex - 1]?.role === 'user') {
			messages[formIndex - 1] = {
				...messages[formIndex - 1],
				content: commandText,
			};
		}
		// Remove the form message
		messages.splice(formIndex, 1);
		return { ...s, messages, isWaiting: true };
	});
}

export function cancelForm(formIndex: number) {
	chatStore.update(s => {
		const messages = [...s.messages];
		if (formIndex < 0 || formIndex >= messages.length) return s;
		// Remove the form message
		messages.splice(formIndex, 1);
		// Remove the triggering user message (e.g. "//blast")
		if (formIndex > 0 && messages[formIndex - 1]?.role === 'user') {
			messages.splice(formIndex - 1, 1);
		}
		return { ...s, messages, isWaiting: false, progress: null };
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
