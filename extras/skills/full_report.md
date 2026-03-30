# Full Report

## When
Comprehensive report on a sequence: "give me full report on pX", "everything about pX".

## Tools
- search
- profile
- parts
- sites
- history
- orf_find
- protparam

## Workflow
1. search() to resolve name to SID
2. In ONE Python call: profile(), parts(sid=...), sites(sequence=sid:N, max_cuts=1), history(sid=...)

## Report
```python
seq = p["sequence"]
report["overview"] = [
    {"property": "Name", "value": seq["name"]},
    {"property": "Size", "value": f"{seq['size_bp']} bp"},
    {"property": "Topology", "value": seq["topology"]},
    {"property": "Features", "value": str(pt["total"])},
    {"property": "Unique cutters", "value": str(st["cutters_found"])},
    {"property": "Assembly steps", "value": str(h.get("steps", 0))},
]
report["features"] = [
    {"name": f["name"], "type": f["type"],
     "position": f"{f['start']}-{f['end']}",
     "strand": "+" if f["strand"] == 1 else "-",
     "length": f["length"]}
    for f in pt["parts"]
]
report["unique_sites"] = [
    {"enzyme": c["name"], "position": c["positions"][0]}
    for c in st["cutters"] if c["num_cuts"] == 1
]
report["history"] = h
```

## Rules
- Batch all tool calls in ONE Python call — do not call one-by-one
- history() returns widget-ready data — pass through to report as-is
- Do not put sequence_data in report
- For DNA sequences, include orf_find() and protparam() for the main CDS if relevant
- 2 Python calls max: resolve name + fetch all & build report
- If user says "concise", skip history and sites sections
