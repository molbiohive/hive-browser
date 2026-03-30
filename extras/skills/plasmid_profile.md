# Plasmid Profile

## When
Show details of a specific sequence: "tell me about pX", "what is pX".

## Tools
- search
- profile

## Workflow
1. If name given, search() to resolve SID
2. profile(sid=...)

## Report
```python
seq = p["sequence"]
report["profile"] = [
    {"property": "Name", "value": seq["name"]},
    {"property": "Size", "value": f"{seq['size_bp']} bp"},
    {"property": "Topology", "value": seq["topology"]},
    {"property": "Molecule", "value": seq.get("molecule", "DNA")},
    {"property": "Features", "value": str(len(p["features"]))},
    {"property": "Primers", "value": str(len(p["primers"]))},
]
```

## Rules
- Do not put sequence_data in the report
- Do not list all features — use part_list skill for that
- 1-2 Python calls, property-value table
