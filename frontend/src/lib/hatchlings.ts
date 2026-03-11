/**
 * Shared helpers for mapping backend data to @molbiohive/hatchlings types.
 */

import type { Part, CutSite } from '@molbiohive/hatchlings';

/** Default feature colors by annotation type */
const FEATURE_COLORS: Record<string, string> = {
	CDS: '#4C9BE8',
	gene: '#4C9BE8',
	promoter: '#31A354',
	terminator: '#E6550D',
	rep_origin: '#9467BD',
	misc_feature: '#8C8C8C',
	primer_bind: '#E377C2',
	primer_predicted: '#C49BD9',
	RBS: '#17BECF',
	regulatory: '#31A354',
};

/**
 * Map backend features + primers to Hatchlings Part[].
 */
export function mapToParts(
	features: Array<Record<string, any>> | undefined,
	primers: Array<Record<string, any>> | undefined,
): Part[] {
	const parts: Part[] = [];

	if (features) {
		for (let i = 0; i < features.length; i++) {
			const f = features[i];
			if (f.start == null || f.end == null) continue;
			parts.push({
				id: `f-${i}`,
				name: f.name || '',
				type: f.type || 'misc_feature',
				start: f.start,
				end: f.end,
				strand: f.strand > 0 ? 1 : -1,
				color: FEATURE_COLORS[f.type] || FEATURE_COLORS.misc_feature,
			});
		}
	}

	if (primers) {
		// Deduplicate: hatchlings keys primers by (name + start), so if a
		// file-native and predicted primer share name+start, keep file-native.
		const seen = new Set<string>();
		for (let i = 0; i < primers.length; i++) {
			const p = primers[i];
			if (p.start == null || p.end == null) continue;
			const key = `${p.name || ''}\0${p.start}`;
			if (seen.has(key)) continue;
			seen.add(key);
			const predicted = p.source === 'predicted';
			parts.push({
				id: `p-${i}`,
				name: p.name || '',
				type: 'primer_bind',
				start: p.start,
				end: p.end,
				strand: p.strand > 0 ? 1 : -1,
				color: predicted ? FEATURE_COLORS.primer_predicted : FEATURE_COLORS.primer_bind,
				note: predicted ? 'predicted' : undefined,
				tm: p.tm,
				sequence: p.sequence,
				bindingStart: p.bindingStart,
				bindingEnd: p.bindingEnd,
			});
		}
	}

	return parts;
}

/**
 * Map backend cut_sites to Hatchlings CutSite[].
 * Backend already produces a compatible shape; this adds type safety.
 */
export function mapToCutSites(
	cutSites: Array<Record<string, any>> | undefined,
): CutSite[] {
	if (!cutSites) return [];
	return cutSites.map((cs, i) => ({
		id: `cs-${i}`,
		enzyme: cs.enzyme,
		position: cs.position,
		end: cs.end,
		strand: cs.strand > 0 ? 1 : -1 as 1 | -1,
		overhang: cs.overhang,
		cutPosition: cs.cutPosition,
		complementCutPosition: cs.complementCutPosition,
	}));
}
