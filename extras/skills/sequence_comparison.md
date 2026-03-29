# Sequence Comparison

## When
Compare two specific sequences: "compare pX and pY", "what's different between these two".

## Workflow
1. search() to resolve both names to SIDs
2. Fetch profiles for both, then blast one against the other

## Report
```python
report["comparison"] = [
    {"property": "Name", "seq_a": a["name"], "seq_b": b["name"]},
    {"property": "Size", "seq_a": f"{a['size_bp']} bp", "seq_b": f"{b['size_bp']} bp"},
    {"property": "Topology", "seq_a": a["topology"], "seq_b": b["topology"]},
    {"property": "Features", "seq_a": str(len(fa)), "seq_b": str(len(fb))},
]
```

## Red Flags
- Use BLAST for sequence-level similarity, not search()
- Two different sequences may share the same name in different directories

## Rules
- 2-3 Python calls max
- Side-by-side comparison table
