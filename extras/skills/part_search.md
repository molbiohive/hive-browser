# Part Search

## When
Find parts by name or type: "find all GFP parts", "show promoters".

## Workflow
1. search(query=...) — parts are in the response alongside sequences

## Report
```python
report["parts"] = [
    {"name": ", ".join(p["names"]), "type": ", ".join(p["types"]),
     "length": p["length"], "used_in": f"{p['instance_count']} sequences"}
    for p in r["parts"]
]
```

## Red Flags
- search() returns both sequences and parts — use the parts field
- Part names and types are lists (same part can have multiple annotations)

## Rules
- 1 tool call, 1 table, 1 Python call
