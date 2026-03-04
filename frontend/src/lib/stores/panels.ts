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

export const leftPanelOpen = persistedBool('panel_left', true);
export const rightPanelOpen = persistedBool('panel_right', false);
