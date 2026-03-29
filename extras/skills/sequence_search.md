# Sequence Search

## When
Find sequences by name, keyword, feature, or resistance marker.

## Workflow
1. search(query=...) — supports && (AND), || (OR), * (all)
2. Build report from results

## Report
```python
report["sequences"] = [
    {"name": r["name"], "size_bp": r["size_bp"],
     "topology": r["topology"], "features": ", ".join(r["features"][:5])}
    for r in r["results"]
]
```

## Red Flags
- BLAST is for sequence similarity, not keyword search
- Do not profile each result
- tags param filters by directory, not biological tags

## Rules
- 1 tool call, 1 table, 1 Python call
