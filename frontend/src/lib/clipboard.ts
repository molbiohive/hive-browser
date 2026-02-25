/**
 * Copy text to clipboard with fallback for non-secure contexts (HTTP, RDP).
 * Returns true on success.
 */
export async function copyToClipboard(text: string): Promise<boolean> {
	try {
		await navigator.clipboard.writeText(text);
		return true;
	} catch {
		// Fallback: hidden textarea + execCommand (works in HTTP/iframe/RDP)
		const ta = document.createElement('textarea');
		ta.value = text;
		ta.style.position = 'fixed';
		ta.style.opacity = '0';
		document.body.appendChild(ta);
		ta.select();
		let ok = false;
		try {
			ok = document.execCommand('copy');
		} catch {
			// ignore
		}
		document.body.removeChild(ta);
		return ok;
	}
}
