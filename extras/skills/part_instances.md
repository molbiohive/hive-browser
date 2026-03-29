# Part Instances

## When
Find where a specific part is used across sequences: "which plasmids have GFP", "where is ori used".

## Workflow
1. search() to find the part and get PID
2. parts(pid=...) to get all instances

## Report
```python
report["instances"] = [
    {"sequence": i["sequence_name"], "type": i["annotation_type"],
     "position": f"{i['start']}-{i['end']}",
     "strand": "+" if i["strand"] == 1 else "-"}
    for i in p["instances"]
]
```

## Red Flags
- Need PID, not SID. Get PID from search results parts field.

## Rules
- 1-2 Python calls, 1 table
