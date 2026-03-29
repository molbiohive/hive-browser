/**
 * Panel visibility stores for sidebar and search panel.
 * State is persisted in localStorage.
 */

import { writable } from 'svelte/store';

function persistedBool(key: string, fallback: boolean) {
	const stored = typeof localStorage !== 'undefined' ? localStorage.getItem(key) : null;
	const initial = stored !== null ? stored === 'true' : fallback;
	const store = writable(initial);
	store.subscribe(v => {
		if (typeof localStorage !== 'undefined') {
			localStorage.setItem(key, String(v));
		}
	});
	return store;
}

function persistedNum(key: string, fallback: number) {
	const stored = typeof localStorage !== 'undefined' ? localStorage.getItem(key) : null;
	const initial = stored !== null ? Number(stored) : fallback;
	const store = writable(initial);
	store.subscribe(v => {
		if (typeof localStorage !== 'undefined') {
			localStorage.setItem(key, String(v));
		}
	});
	return store;
}

export const leftPanelOpen = persistedBool('panel_left', true);
export const rightPanelOpen = persistedBool('panel_right', false);

export const sidebarWidth = persistedNum('panel_sidebar_width', 240);
export const searchPanelWidth = persistedNum('panel_search_width', 450);
