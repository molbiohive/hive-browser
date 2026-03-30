# Restriction Sites

## When
Find restriction enzymes that cut a sequence: "what enzymes cut pX", "find unique cutters".

## Tools
- search
- sites

## Workflow
1. sites(sequence=..., max_cuts=N) — use max_cuts=1 for unique cutters

## Report
```python
report["cutters"] = [
    {"enzyme": c["name"], "cuts": c["num_cuts"],
     "positions": ", ".join(str(p) for p in c["positions"])}
    for c in s["cutters"]
]
```

## Rules
- sites() scans hundreds of enzymes — filter by max_cuts for useful results
- Single cutters (num_cuts=1) are most useful for cloning
- 1 Python call, 1 table
- Default to unique cutters unless user asks for all
