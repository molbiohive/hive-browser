/**
 * User store — manages authentication, user switching, and preferences.
 */

import { writable, derived } from 'svelte/store';

export interface User {
	id: number;
	username: string;
	slug: string;
	preferences: Record<string, unknown>;
}

export const currentUser = writable<User | null>(null);
export const userList = writable<User[]>([]);
export const needsAuth = derived(currentUser, ($u) => $u === null);

// ── Cookie helpers ──────────────────────────────────────

export function getToken(): string | null {
	const match = document.cookie.match(/(?:^|;\s*)hive_token=([^;]*)/);
	return match ? decodeURIComponent(match[1]) : null;
}

export function setToken(token: string) {
	document.cookie = `hive_token=${encodeURIComponent(token)}; path=/; max-age=${365 * 86400}; SameSite=Lax`;
}

export function clearToken() {
	document.cookie = 'hive_token=; path=/; max-age=0';
}

// ── localStorage token vault (multi-user switching) ─────

export function saveUserToken(slug: string, token: string) {
	localStorage.setItem(`hive_token_${slug}`, token);
}

export function getUserToken(slug: string): string | null {
	return localStorage.getItem(`hive_token_${slug}`);
}

// ── API calls ───────────────────────────────────────────

export async function createUser(username: string): Promise<User> {
	const res = await fetch('/api/users', {
		method: 'POST',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify({ username }),
	});
	if (!res.ok) {
		const err = await res.json();
		throw new Error(err.error || 'Failed to create user');
	}
	const data = await res.json();
	setToken(data.token);
	saveUserToken(data.slug, data.token);
	currentUser.set({ id: data.id, username: data.username, slug: data.slug, preferences: {} });
	return data;
}

export async function fetchUsers() {
	try {
		const res = await fetch('/api/users');
		if (res.ok) {
			userList.set(await res.json());
		}
	} catch (e) {
		console.warn('[user] failed to fetch users:', e);
	}
}

export async function loginUser(slug: string): Promise<User> {
	const res = await fetch('/api/users/login', {
		method: 'POST',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify({ slug }),
	});
	if (!res.ok) {
		const err = await res.json();
		throw new Error(err.error || 'Login failed');
	}
	const data = await res.json();
	setToken(data.token);
	saveUserToken(data.slug, data.token);
	currentUser.set({
		id: data.id, username: data.username,
		slug: data.slug, preferences: {},
	});
	return data;
}

export function switchUser(slug: string): boolean {
	const token = getUserToken(slug);
	if (!token) return false;
	setToken(token);
	return true; // caller should reconnect WS
}
