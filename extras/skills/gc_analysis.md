# GC Analysis

## When
Calculate GC content of a sequence: "what's the GC content of pX".

## Workflow
1. gc(sequence=...) — accepts sid:N or raw sequence

## Report
```python
report["composition"] = [
    {"metric": "GC Content", "value": f"{g['gc_percent']:.1f}%"},
    {"metric": "AT Content", "value": f"{g['at_percent']:.1f}%"},
    {"metric": "Length", "value": f"{g['length']} bp"},
    {"metric": "G", "value": g["g"]},
    {"metric": "C", "value": g["c"]},
    {"metric": "A", "value": g["a"]},
    {"metric": "T", "value": g["t"]},
]
```

## Red Flags
- gc() accepts sid:N directly — no need to resolve name first if SID known

## Rules
- 1 Python call, 1 table
