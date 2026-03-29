# Primer Analysis

## When
Show primer binding sites on a sequence: "show primers on pX", "where do primers bind".

## Tools
- search
- primers

## Workflow
1. primers(sequence=...) — accepts sid:N

## Report
```python
report["primers"] = [
    {"name": p["name"], "position": f"{p['start']}-{p['end']}",
     "strand": "+" if p["strand"] == 1 else "-",
     "length": p["length"], "tm": f"{p['tm']:.1f}" if p.get("tm") else ""}
    for p in pr["primers"]
]
```

## Red Flags
- Not all sequences have annotated primers
- Predicted primers may differ from file-annotated ones

## Rules
- 1 Python call, 1 table
