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
			parts.push({
				id: f.pid != null ? `f-${f.pid}` : `f-idx-${i}`,
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
		for (let i = 0; i < primers.length; i++) {
			const p = primers[i];
			parts.push({
				id: p.pid != null ? `p-${p.pid}` : `p-idx-${i}`,
				name: p.name || '',
				type: 'primer_bind',
				start: p.start,
				end: p.end,
				strand: p.strand > 0 ? 1 : -1,
				color: FEATURE_COLORS.primer_bind,
				tm: p.tm,
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
