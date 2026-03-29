# Enzyme Selection

## When
Choose restriction enzymes for cloning: "which enzymes can I use", "find enzymes that cut once outside the insert".

## Workflow
1. sites(sequence=..., max_cuts=1) to find unique cutters
2. If user specifies a region to avoid, filter by position

## Report
```python
report["candidates"] = [
    {"enzyme": c["name"], "position": c["positions"][0]}
    for c in s["cutters"] if c["num_cuts"] == 1
]
```

## Red Flags
- Unique cutters only (num_cuts == 1) — multi-cutters destroy the insert
- Check if enzyme cuts inside vs outside the region of interest

## Rules
- 1 Python call, 1 table
