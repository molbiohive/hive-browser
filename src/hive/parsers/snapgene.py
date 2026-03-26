"""SnapGene file parser using sgffp (.dna, .rna, .prot)."""

from pathlib import Path

from hive.cloning.primers import find_primer_sites
from hive.parsers.base import ParsedFeature, ParsedPrimer, ParseResult

# sgffp block IDs → molecule type
_BLOCK_MOLECULE_TYPE = {0: "DNA", 1: "DNA", 21: "protein", 32: "RNA"}

# sgffp strand strings → integer (DB stores SmallInteger)
_STRAND_MAP = {"+": 1, "-": -1, ".": 0, "1": 1, "-1": -1}


def _parse_strand(strand) -> int:
    if isinstance(strand, int):
        return strand
    return _STRAND_MAP.get(str(strand), 0)


def _serialize_history_tree(node, history) -> list[dict]:
    """Flatten history tree to list of node dicts for DB ingestion."""
    result = []

    def _walk(n, parent_id=None):
        enzymes = []
        for s in getattr(n, "input_summaries", []):
            for name, count in getattr(s, "enzymes", []):
                enzymes.append({"name": name, "site_count": count})

        # Use block 11 content for properly parsed SgffFeature objects.
        # Tree node .features is raw XML dicts — not usable directly.
        features = []
        content = history.get_node(n.id)
        if content:
            for f in content.features:
                features.append(
                    {
                        "name": getattr(f, "name", ""),
                        "type": getattr(f, "type", "misc_feature"),
                        "start": getattr(f, "start", 0),
                        "end": getattr(f, "end", 0),
                        "strand": _parse_strand(getattr(f, "strand", ".")),
                        "qualifiers": dict(f.qualifiers) if hasattr(f, "qualifiers") else {},
                    }
                )

        result.append(
            {
                "node_id": n.id,
                "parent_node_id": parent_id,
                "name": getattr(n, "name", ""),
                "operation": getattr(n, "operation", "invalid"),
                "seq_len": getattr(n, "seq_len", 0),
                "circular": getattr(n, "circular", False),
                "molecule_type": getattr(n, "type", "DNA"),
                "oligos": [
                    {
                        "name": o.name,
                        "sequence": o.sequence,
                        "phosphorylated": getattr(o, "phosphorylated", False),
                    }
                    for o in getattr(n, "oligos", [])
                ],
                "enzymes": enzymes,
                "features": features,
                "parameters": getattr(n, "parameters", {}),
            }
        )
        for child in getattr(n, "children", []):
            _walk(child, n.id)

    _walk(node)
    return result


def _history_keywords(steps: list[dict]) -> str:
    """Build searchable keyword string from history steps."""
    words = set()
    for s in steps:
        if s.get("name"):
            words.add(s["name"])
        if s.get("operation"):
            words.add(s["operation"])
        for o in s.get("oligos", []):
            if o.get("name"):
                words.add(o["name"])
        for e in s.get("enzymes", []):
            if e.get("name"):
                words.add(e["name"])
        for f in s.get("features", []):
            if f.get("name"):
                words.add(f["name"])
    return " ".join(sorted(words))


def parse_snapgene(filepath: Path, extract: list[str] | None = None) -> ParseResult:
    """Parse a SnapGene file (.dna, .rna, .prot) and return structured data."""
    from sgffp import SgffReader

    sgff = SgffReader.from_file(filepath)

    features = []
    if extract is None or "features" in extract:
        for f in sgff.features:
            quals = dict(f.qualifiers) if hasattr(f, "qualifiers") else {}
            segments = getattr(f, "segments", [])
            if segments and any(getattr(s, "translated", False) for s in segments):
                quals["translated"] = True
            rf = getattr(f, "reading_frame", None)
            if rf is not None:
                quals["reading_frame"] = rf
            features.append(
                ParsedFeature(
                    name=f.name,
                    type=f.type,
                    start=f.start,
                    end=f.end,
                    strand=_parse_strand(f.strand),
                    qualifiers=quals,
                )
            )

    primers = []
    if extract is None or "primers" in extract:
        seq_len = len(sgff.sequence.value)
        seen_sites: set[tuple] = set()
        for p in sgff.primers:
            sites = getattr(p, "binding_sites", [])
            if sites:
                for bs in sites:
                    key = (p.name, bs.start, bs.end)
                    if key in seen_sites:
                        continue
                    seen_sites.add(key)
                    primers.append(
                        ParsedPrimer(
                            name=p.name,
                            sequence=p.sequence,
                            tm=getattr(bs, "melting_temperature", None),
                            start=bs.start,
                            end=bs.end,
                            strand=_parse_strand(getattr(bs, "bound_strand", ".")),
                            length=bs.length(seq_len),
                        )
                    )
            else:
                primers.append(ParsedPrimer(name=p.name, sequence=p.sequence))

        # Map primers with null locations via 3' anchor scanning
        unmapped = [
            {"id": i, "name": pr.name, "sequence": pr.sequence}
            for i, pr in enumerate(primers)
            if pr.start is None and pr.sequence
        ]
        if unmapped:
            parent_seq = sgff.sequence.value
            is_circular = sgff.sequence.topology == "circular"
            hits = find_primer_sites(parent_seq, unmapped, circular=is_circular)
            for hit in hits:
                idx = hit["primer_id"]
                primers[idx] = ParsedPrimer(
                    name=primers[idx].name,
                    sequence=primers[idx].sequence,
                    tm=primers[idx].tm,
                    start=hit["start"],
                    end=hit["end"],
                    strand=hit["strand"],
                )

    meta = {}
    if (
        (extract is None or "notes" in extract)
        and hasattr(sgff, "notes")
        and sgff.notes
        and sgff.notes.exists
    ):
        meta["notes"] = sgff.notes.data

    molecule_type = _BLOCK_MOLECULE_TYPE.get(sgff.sequence.block_id, "DNA")
    meta["molecule_type"] = molecule_type

    # Extract cloning history tree
    if extract is None or "history" in extract:
        if hasattr(sgff, "has_history") and sgff.has_history and sgff.history.tree:
            meta["history"] = _serialize_history_tree(sgff.history.tree.root, sgff.history)
            # Build searchable keywords for BM25 matching
            meta["history_keywords"] = _history_keywords(meta["history"])

    description = None
    if hasattr(sgff, "notes") and sgff.notes and sgff.notes.exists:
        desc = sgff.notes.description
        if desc:
            description = desc

    return ParseResult(
        name=filepath.stem,
        sequence=sgff.sequence.value,
        size_bp=len(sgff.sequence.value),
        topology=sgff.sequence.topology,
        molecule=molecule_type,
        description=description,
        features=features,
        primers=primers,
        meta=meta,
    )
