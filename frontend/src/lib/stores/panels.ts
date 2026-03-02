/**
 * Panel visibility stores for sidebar and search panel.
 */

import { writable } from 'svelte/store';

export const leftPanelOpen = writable(true);
export const rightPanelOpen = writable(false);
