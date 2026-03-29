# Translate

## When
Translate DNA/RNA to protein: "translate this sequence", "what protein does pX encode".

## Tools
- search
- translate

## Workflow
1. translate(sequence=...) — accepts sid:N or raw sequence

## Report
```python
report["translation"] = [
    {"property": "Protein", "value": t["protein"]},
    {"property": "Protein length", "value": f"{t['protein_length']} aa"},
    {"property": "Nucleotide length", "value": f"{t['nucleotide_length']} bp"},
    {"property": "Complete ORF", "value": str(t["complete"])},
    {"property": "Stop codons", "value": str(t["stop_codons"])},
]
```

## Red Flags
- For a specific CDS, extract() it first, then translate the extracted sequence

## Rules
- 1 Python call, property-value table
