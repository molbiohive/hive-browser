# Cloning History

## When
Show how a sequence was assembled: "how was pX built", "cloning history of pX", "construction steps".

## Tools
- search
- history

## Workflow
1. If name given, search() to resolve SID
2. history(sid=...)

## Report
```python
report["history"] = h
```

history() returns widget-ready data — pass through as-is.

## Red Flags
- history() result is a nested tree structure — do not flatten or reformat
- Not all sequences have cloning history (only SnapGene files with assembly info)

## Rules
- 1-2 Python calls
- Pass history result through untampered
