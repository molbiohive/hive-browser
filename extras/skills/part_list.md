# Part List

## When
List all parts/features on a specific sequence: "what features does pX have", "show parts on pX".

## Workflow
1. If name given, search() to resolve SID
2. parts(sid=...)

## Report
```python
report["parts"] = [
    {"name": f["name"], "type": f["type"],
     "position": f"{f['start']}-{f['end']}",
     "strand": "+" if f["strand"] == 1 else "-",
     "length": f["length"]}
    for f in pt["parts"]
]
```

## Red Flags
- parts(sid=N) lists features on a sequence — different from parts(pid=N)

## Rules
- 1-2 Python calls, 1 table
