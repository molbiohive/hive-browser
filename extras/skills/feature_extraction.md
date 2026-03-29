# Feature Extraction

## When
Extract a subsequence by feature name or region: "get the GFP sequence from pX", "extract region 100-500".

## Workflow
1. If name given, search() to resolve SID
2. extract(sid=..., feature_name=...) or extract(sid=..., region="start:end")

## Report
```python
report["extracted"] = [
    {"property": "Name", "value": e["name"]},
    {"property": "Length", "value": f"{e['length']} bp"},
    {"property": "Position", "value": f"{e['start']}-{e['end']}"},
    {"property": "Strand", "value": "+" if e["strand"] == 1 else "-"},
    {"property": "Sequence", "value": e["sequence"]},
]
```

## Red Flags
- extract() needs SID + feature_name or region, not just a name
- Region is 1-based inclusive: "100:500"
- Never trim sequence data — frontend handles display

## Rules
- 1-2 Python calls, property-value table
