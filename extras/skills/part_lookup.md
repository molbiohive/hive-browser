# Part Lookup

## When
Look up a specific part by PID: "what is part 42", "show part details".

## Tools
- search
- parts

## Workflow
1. parts(pid=...)

## Report
```python
report["part"] = [
    {"property": "Names", "value": ", ".join(p["part"]["names"])},
    {"property": "Length", "value": f"{p['part']['length']} bp"},
    {"property": "Molecule", "value": p["part"]["molecule"]},
    {"property": "Used in", "value": f"{p['instances_count']} sequences"},
]
report["instances"] = [
    {"sequence": i["sequence_name"], "type": i["annotation_type"],
     "position": f"{i['start']}-{i['end']}",
     "strand": "+" if i["strand"] == 1 else "-"}
    for i in p["instances"]
]
```

## Red Flags
- parts(pid=N) returns single part detail, parts(sid=N) returns list on a sequence

## Rules
- 1 Python call, 2 tables (part info + instances)
