# Reverse Complement

## When
Get reverse complement: "reverse complement of this sequence", "revcomp pX".

## Tools
- search
- revcomp

## Workflow
1. revcomp(sequence=...) — accepts sid:N or raw sequence

## Report
```python
report["revcomp"] = [
    {"property": "Sequence", "value": r["sequence"]},
    {"property": "Length", "value": f"{r['length']} bp"},
]
```

## Rules
- 1 Python call, property-value table
