# Transcribe

## When
Transcribe DNA to mRNA: "transcribe pX", "get the mRNA".

## Tools
- search
- transcribe

## Workflow
1. transcribe(sequence=...) — accepts sid:N or raw sequence

## Report
```python
report["transcription"] = [
    {"property": "RNA", "value": t["rna"]},
    {"property": "Length", "value": f"{t['length']} nt"},
]
```

## Red Flags
- Transcription is simple T->U replacement — not translation

## Rules
- 1 Python call, property-value table
