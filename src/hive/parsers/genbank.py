"""GenBank .gb/.gbk parser -- native implementation, no Biopython."""

import re
from pathlib import Path

from hive.parsers.base import ParsedFeature, ParseResult


def parse_genbank(filepath: Path, extract: list[str] | None = None) -> ParseResult:
    """Parse a GenBank file and return structured data."""
    text = filepath.read_text()

    # -- LOCUS line --
    locus_m = re.match(
        r"LOCUS\s+(\S+)\s+(\d+)\s+bp\s+(\S+)?\s*(circular|linear)?\s*",
        text,
    )
    name = locus_m.group(1) if locus_m else filepath.stem
    mol_raw = locus_m.group(3).strip() if locus_m and locus_m.group(3) else ""
    topology = (locus_m.group(4) or "linear").lower() if locus_m else "linear"

    # -- DEFINITION --
    def_m = re.search(r"^DEFINITION\s+(.+?)(?=\n\S)", text, re.MULTILINE | re.DOTALL)
    description = None
    if def_m:
        desc = " ".join(def_m.group(1).split())
        if desc and desc != ".":
            description = desc

    # -- Molecule type --
    if "protein" in mol_raw.lower():
        molecule = "protein"
    elif "rna" in mol_raw.lower():
        molecule = "RNA"
    else:
        molecule = "DNA"

    # -- ORIGIN section (sequence) --
    origin_m = re.search(r"^ORIGIN\s*\n(.*?)^//", text, re.MULTILINE | re.DOTALL)
    sequence = ""
    if origin_m:
        # Strip line numbers and spaces, keep only letters
        sequence = re.sub(r"[^a-zA-Z]", "", origin_m.group(1))

    size_bp = len(sequence)

    # -- FEATURES table --
    features = []
    if extract is None or "features" in extract:
        feat_m = re.search(
            r"^FEATURES\s+Location/Qualifiers\s*\n(.*?)(?=^ORIGIN|^CONTIG|^\Z)",
            text,
            re.MULTILINE | re.DOTALL,
        )
        if feat_m:
            features = _parse_features(feat_m.group(1))

    return ParseResult(
        name=name,
        sequence=sequence,
        size_bp=size_bp,
        topology=topology,
        molecule=molecule,
        description=description,
        features=features,
        meta={},
    )


def _parse_features(block: str) -> list[ParsedFeature]:
    """Parse the FEATURES block into ParsedFeature objects."""
    features = []

    # Split into individual feature entries.
    # Each feature starts with a type name at column 5 (indented 5 spaces)
    # followed by a location, then qualifier lines indented 21 spaces.
    entries = re.split(r"\n(?=     \S)", block)

    for entry in entries:
        entry = entry.strip()
        if not entry:
            continue

        # First line: type + location
        header_m = re.match(r"(\S+)\s+(.*)", entry)
        if not header_m:
            continue
        feat_type = header_m.group(1)
        rest = header_m.group(2)

        # Skip source features
        if feat_type == "source":
            continue

        # Collect the full location (may span multiple lines before qualifiers)
        lines = entry.split("\n")
        location_parts = [rest.strip()]
        i = 1
        while i < len(lines) and not lines[i].strip().startswith("/"):
            location_parts.append(lines[i].strip())
            i += 1
        location_str = "".join(location_parts)

        # Parse location
        start, end, strand = _parse_location(location_str)

        # Parse qualifiers
        qualifiers = _parse_qualifiers(lines[i:])

        feat_name = (
            qualifiers.get("label")
            or qualifiers.get("gene")
            or feat_type
        )

        features.append(ParsedFeature(
            name=feat_name,
            type=feat_type,
            start=start,
            end=end,
            strand=strand,
            qualifiers=qualifiers,
        ))

    return features


def _parse_location(loc: str) -> tuple[int, int, int]:
    """Parse a GenBank location string to (start, end, strand).

    Returns 0-based start, exclusive end (matching Biopython convention).
    Handles: N..M, complement(N..M), join(...), complement(join(...)).
    """
    strand = 1
    inner = loc

    # Peel complement()
    comp_m = re.match(r"complement\((.+)\)", inner)
    if comp_m:
        strand = -1
        inner = comp_m.group(1)

    # Peel join() or order() -- simplify to overall span
    join_m = re.match(r"(?:join|order)\((.+)\)", inner)
    if join_m:
        inner = join_m.group(1)

    # Extract all numeric positions
    positions = [int(x) for x in re.findall(r"\d+", inner)]
    if not positions:
        return 0, 0, strand

    # GenBank is 1-based inclusive -> convert to 0-based exclusive end
    start = min(positions) - 1
    end = max(positions)
    return start, end, strand


def _parse_qualifiers(lines: list[str]) -> dict[str, str]:
    """Parse qualifier lines into a dict."""
    qualifiers: dict[str, str] = {}
    current_key = None
    current_val = ""

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        if stripped.startswith("/"):
            # Save previous qualifier
            if current_key is not None:
                qualifiers[current_key] = current_val.strip('"')

            # Parse new qualifier
            if "=" in stripped:
                key, _, val = stripped[1:].partition("=")
                current_key = key
                current_val = val.strip('"')
            else:
                # Flag qualifier (e.g. /pseudo)
                current_key = stripped[1:]
                current_val = ""
        elif current_key is not None:
            # Continuation line
            current_val += " " + stripped.strip('"')

    # Save last qualifier
    if current_key is not None:
        qualifiers[current_key] = current_val.strip('"')

    return qualifiers
